from app.schemas.listing import AmenityCode
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.listing import Listing
from app.models.location import District, Ward
from app.repositories.listing_repository import ListingRepository
from app.schemas.analytics import PriceStatsByArea, PriceStatsGeneral, PriceStatsResponse
from app.schemas.listing import ListingResponse, VectorSearchResult
from app.services.reranker import _haversine_km, explain_match, rerank
from app.services.embedding import EmbeddingModel


def month_boundaries(reference: Optional[datetime] = None) -> tuple[datetime, datetime]:
    current = reference or datetime.now(timezone.utc)
    current_start = datetime(current.year, current.month, 1, tzinfo=current.tzinfo)
    previous_start = (
        datetime(current.year - 1, 12, 1, tzinfo=current.tzinfo)
        if current.month == 1
        else datetime(current.year, current.month - 1, 1, tzinfo=current.tzinfo)
    )
    return current_start, previous_start


class ListingService:
    def __init__(self, db: Session, repository: Optional[ListingRepository] = None):
        self.db: Session = db
        self.repository: ListingRepository = repository or ListingRepository(db)

    def list_listings(self, **filters: object) -> list[Listing]:
        order_by = str(filters.get("order_by", "posted_date"))
        if order_by not in Listing.__table__.columns.keys():
            raise BadRequestException(f"Invalid order_by field: {order_by}", {"field": order_by})
        return self.repository.search(
            search=filters.get("search"), # type: ignore
            city_id=filters.get("city_id"), # type: ignore
            district_id=filters.get("district_id"), # type: ignore
            ward_id=filters.get("ward_id"), # type: ignore
            room_type_id=filters.get("room_type_id"), # type: ignore
            min_price=filters.get("min_price"), # type: ignore
            max_price=filters.get("max_price"), # type: ignore
            min_area=filters.get("min_area"), # type: ignore
            max_area=filters.get("max_area"), # type: ignore
            min_bedrooms=filters.get("min_bedrooms"), # type: ignore
            min_bathrooms=filters.get("min_bathrooms"), # type: ignore
            order_by=order_by,
            sort_desc=bool(filters.get("sort_desc", True)),
            limit=int(filters.get("limit", 20)), # type: ignore
            offset=int(filters.get("offset", 0)), # type: ignore
        )

    def count_listings(self, **filters: object) -> int:
        return self.repository.count(
            search=filters.get("search"), # type: ignore
            city_id=filters.get("city_id"), # type: ignore
            district_id=filters.get("district_id"), # type: ignore
            ward_id=filters.get("ward_id"), # type: ignore
            room_type_id=filters.get("room_type_id"), # type: ignore
            min_price=filters.get("min_price"), # type: ignore
            max_price=filters.get("max_price"), # type: ignore
            min_area=filters.get("min_area"), # type: ignore
            max_area=filters.get("max_area"), # type: ignore
            min_bedrooms=filters.get("min_bedrooms"), # type: ignore
            min_bathrooms=filters.get("min_bathrooms"), # type: ignore
        )

    def get_listing(self, listing_id: str) -> Listing:
        listing = self.repository.get_by_id(listing_id)
        if listing is None:
            raise NotFoundException(f"Listing with id '{listing_id}' not found")
        return listing

    def get_price_stats(
        self,
        city_id: int,
        district_id: Optional[int],
        room_type_id: Optional[int],
        last_d: Optional[int] = None,
    ) -> PriceStatsResponse:
        now = datetime.now(timezone.utc)
        current_month, prev_month = month_boundaries(now)
        since_date = (now - timedelta(days=last_d)) if (last_d is not None and last_d > 0) else None

        base_filters = [
            Listing.region_id == city_id,
            Listing.price_vnd.isnot(None),
            Listing.price_vnd > 0,
            Listing.is_active == True,
        ]
        if district_id is not None:
            base_filters.append(Listing.district_id == district_id)
        if room_type_id is not None:
            base_filters.append(Listing.room_type_id == room_type_id)

        # 1. Thống kê tổng quan: nếu có last_d thì lọc theo N ngày gần nhất, ngược lại lấy tất cả
        eff_filters = list(base_filters) + ([Listing.posted_date >= since_date] if since_date else [])
        total_count, overall_avg, overall_min, overall_max = self.repository.price_aggregates(eff_filters)

        # 2. Thống kê biến động giá & tăng trưởng tin theo chu kỳ tháng
        cur_filters = list(base_filters) + [Listing.posted_date >= current_month]
        prev_filters = list(base_filters) + [Listing.posted_date >= prev_month, Listing.posted_date < current_month]
        _, cur_avg = self.repository.count_and_average(cur_filters)
        _, prev_avg = self.repository.count_and_average(prev_filters)

        def _calc_growth(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
            if cur is None or prev is None or prev == 0:
                return None
            return round(((cur - prev) / prev) * 100, 2)

        by_area_records: list[PriceStatsByArea] = []
        area_hotspot: Optional[str] = None
        hotspot_posting_growth: Optional[float] = None

        if since_date:
            total_col = func.count(case((Listing.posted_date >= since_date, Listing.id)))
            avg_col = func.avg(case((Listing.posted_date >= since_date, Listing.price_vnd)))
            min_col = func.min(case((Listing.posted_date >= since_date, Listing.price_vnd)))
            max_col = func.max(case((Listing.posted_date >= since_date, Listing.price_vnd)))
            area_filters = list(base_filters) + [Listing.posted_date >= prev_month]
        else:
            total_col = func.count(Listing.id)
            avg_col = func.avg(Listing.price_vnd)
            min_col = func.min(Listing.price_vnd)
            max_col = func.max(Listing.price_vnd)
            area_filters = list(base_filters)

        if district_id is not None:
            query = (
                self.db.query(
                    Ward.id,
                    Ward.name,
                    total_col.label("total_listings"),
                    avg_col.label("average_price_vnd"),
                    min_col.label("minimum_price_vnd"),
                    max_col.label("maximum_price_vnd"),
                    func.avg(case((Listing.posted_date >= current_month, Listing.price_vnd))).label("current_average"),
                    func.avg(case(((Listing.posted_date >= prev_month) & (Listing.posted_date < current_month), Listing.price_vnd))).label("previous_average"),
                    func.count(case((Listing.posted_date >= current_month, Listing.id))).label("current_count"),
                    func.count(case(((Listing.posted_date >= prev_month) & (Listing.posted_date < current_month), Listing.id))).label("previous_count"),
                )
                .join(Listing, Listing.ward_id == Ward.id)
                .filter(*area_filters)
                .group_by(Ward.id, Ward.name)
            )
            if room_type_id is not None:
                query = query.filter(Listing.room_type_id == room_type_id)
            if since_date:
                query = query.having(total_col > 0)
            query = query.order_by(total_col.desc())

            rows = query.all()
            for r in rows:
                cur_avg_area = getattr(r, "current_average", None)
                prev_avg_area = getattr(r, "previous_average", None)
                fluctuation = _calc_growth(
                    float(cur_avg_area) if cur_avg_area is not None else None,
                    float(prev_avg_area) if prev_avg_area is not None else None,
                )
                by_area_records.append(
                    PriceStatsByArea(
                        area_id=r.id,
                        area=str(r.name),
                        total_listings=int(r.total_listings),
                        fluctuation_month=fluctuation,
                        average_price_vnd=round(float(r.average_price_vnd), 2) if r.average_price_vnd else 0.0,
                        minimum_price_vnd=round(float(r.minimum_price_vnd), 2) if r.minimum_price_vnd else None,
                        maximum_price_vnd=round(float(r.maximum_price_vnd), 2) if r.maximum_price_vnd else None,
                    )
                )

            if rows:
                area_hotspot = str(rows[0].name) if rows[0].name is not None else None
                cur_c = getattr(rows[0], "current_count", None)
                prev_c = getattr(rows[0], "previous_count", None)
                hotspot_posting_growth = _calc_growth(
                    float(cur_c) if cur_c is not None else None,
                    float(prev_c) if prev_c is not None else None,
                )
        else:
            query = (
                self.db.query(
                    District.id,
                    District.name,
                    total_col.label("total_listings"),
                    avg_col.label("average_price_vnd"),
                    min_col.label("minimum_price_vnd"),
                    max_col.label("maximum_price_vnd"),
                    func.avg(case((Listing.posted_date >= current_month, Listing.price_vnd))).label("current_average"),
                    func.avg(case(((Listing.posted_date >= prev_month) & (Listing.posted_date < current_month), Listing.price_vnd))).label("previous_average"),
                    func.count(case((Listing.posted_date >= current_month, Listing.id))).label("current_count"),
                    func.count(case(((Listing.posted_date >= prev_month) & (Listing.posted_date < current_month), Listing.id))).label("previous_count"),
                )
                .join(Listing, Listing.district_id == District.id)
                .filter(*area_filters)
                .group_by(District.id, District.name)
            )
            if room_type_id is not None:
                query = query.filter(Listing.room_type_id == room_type_id)
            if since_date:
                query = query.having(total_col > 0)
            query = query.order_by(total_col.desc())

            rows = query.all()
            for r in rows:
                cur_avg_area = getattr(r, "current_average", None)
                prev_avg_area = getattr(r, "previous_average", None)
                fluctuation = _calc_growth(
                    float(cur_avg_area) if cur_avg_area is not None else None,
                    float(prev_avg_area) if prev_avg_area is not None else None,
                )
                by_area_records.append(
                    PriceStatsByArea(
                        area_id=r.id,
                        area=str(r.name),
                        total_listings=int(r.total_listings),
                        fluctuation_month=fluctuation,
                        average_price_vnd=round(float(r.average_price_vnd), 2) if r.average_price_vnd else 0.0,
                        minimum_price_vnd=round(float(r.minimum_price_vnd), 2) if r.minimum_price_vnd else None,
                        maximum_price_vnd=round(float(r.maximum_price_vnd), 2) if r.maximum_price_vnd else None,
                    )
                )

            if rows:
                area_hotspot = str(rows[0].name) if rows[0].name is not None else None
                cur_c = getattr(rows[0], "current_count", None)
                prev_c = getattr(rows[0], "previous_count", None)
                hotspot_posting_growth = _calc_growth(
                    float(cur_c) if cur_c is not None else None,
                    float(prev_c) if prev_c is not None else None,
                )

        general = PriceStatsGeneral(
            total_listings=total_count,
            average_price_vnd=round(overall_avg, 2) if overall_avg else None,
            minimum_price_vnd=round(overall_min, 2) if overall_min else None,
            maximum_price_vnd=round(overall_max, 2) if overall_max else None,
            price_fluctuation_month=_calc_growth(cur_avg, prev_avg),
            area_hotspot=area_hotspot,
            hotspot_posting_growth_month=hotspot_posting_growth,
        )

        return PriceStatsResponse(
            price_stats_general=general,
            price_stats_by_area=by_area_records if by_area_records else None,
        )

    def get_by_ids(self, ids: list[str], preserve_order: bool = True) -> list[Listing]:
        """
        Lấy danh sách tin đăng theo danh sách IDs.
        """
        cleaned_ids = [str(item).strip() for item in ids if str(item).strip()]
        if not cleaned_ids:
            return []
        return self.repository.get_by_ids(cleaned_ids, preserve_order=preserve_order)

    def vector_search(
        self,
        query: str,
        model_embedding: EmbeddingModel,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        amenities: Optional[list[AmenityCode]] = None,
        preferred_amenities: Optional[list[AmenityCode]] = None,
        weights: Optional[dict[str, float]] = None,
        city_id: Optional[int] = None,
        district_id: Optional[int] = None,
        ward_id: Optional[int] = None,
        room_type: Optional[str | int | list[str | int]] = None,
        excluded_room_types: Optional[list[Any]] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_area: Optional[float] = None,
        max_area: Optional[float] = None,
        min_bedrooms: Optional[int] = None,
        min_bathrooms: Optional[int] = None,
        max_distance_km: Optional[float] = 8.0,
        limit: int = 5,
        offset: int = 0,
    ) -> list[VectorSearchResult]:
        raw_vector = model_embedding.encode_query(query)
        query_vector: list[float] = raw_vector.tolist() # type: ignore

        candidate_limit = max(limit * 4, 100) if (lat is not None and lng is not None) else max(limit * 2, 50)

        repo_kwargs: dict[str, object] = {
            "query_vector": query_vector,
            "query_text": query,
            "city_id": city_id,
            "district_id": district_id,
            "ward_id": ward_id,
            "room_type": room_type,
            "min_price": min_price,
            "max_price": max_price,
            "min_area": min_area,
            "max_area": max_area,
            "lat": lat,
            "lng": lng,
            "max_distance_km": max_distance_km,
            "amenities": amenities,
            "excluded_room_types": excluded_room_types,
            "limit": candidate_limit,
        }
        if min_bedrooms is not None:
            repo_kwargs["min_bedrooms"] = min_bedrooms
        if min_bathrooms is not None:
            repo_kwargs["min_bathrooms"] = min_bathrooms
        model_name = model_embedding.model_name.strip()
        repo_kwargs["model_name"] = model_name

        candidates = self.repository.vector_search(**repo_kwargs) # type: ignore

        if not candidates:
            return []

        # Kiểm chứng kép an toàn: loại bỏ triệt để các ứng viên vượt max_distance_km
        if lat is not None and lng is not None and max_distance_km:
            valid_candidates = []
            for cand in candidates:
                cand_obj = cand.get("listing", cand) if isinstance(cand, dict) else cand
                c_lat = getattr(cand_obj, "lat", None)
                c_lng = getattr(cand_obj, "lng", None)
                if c_lat is None and isinstance(cand_obj, dict):
                    c_lat = cand_obj.get("lat")
                if c_lng is None and isinstance(cand_obj, dict):
                    c_lng = cand_obj.get("lng")
                try:
                    if c_lat is not None and c_lng is not None:
                        d_km = _haversine_km(lat, lng, float(c_lat), float(c_lng))
                        if d_km <= float(max_distance_km):
                            valid_candidates.append(cand)
                except (ValueError, TypeError):
                    continue
            candidates = valid_candidates

        if not candidates:
            return []

        user_pref: dict[str, object] = {
            "lat": lat,
            "lng": lng,
            "max_distance_km": max_distance_km,
            "amenities": amenities,
            "preferred_amenities": preferred_amenities,
            "min_price": min_price,
            "max_price": max_price,
            "query": query,
        }

        reranked = rerank(
            candidates=candidates, # type: ignore
            user_pref=user_pref,
            base_weights=weights,
            limit=limit,
            offset=offset,
        )

        def _unwrap(candidate: object) -> object:
            """Candidate từ repository có thể là dict {'listing': ORM, ...scores} hoặc ORM thuần."""
            if isinstance(candidate, dict) and "listing" in candidate:
                return candidate["listing"]
            return candidate

        return [
            VectorSearchResult(
                listing=ListingResponse.model_validate(_unwrap(listing)),
                match_score=float(breakdown["score"]), # type: ignore
                explain_match=explain_match(breakdown), # type: ignore
            )
            for breakdown, listing in reranked
        ]
