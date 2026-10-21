from app.schemas.listing import AmenityCode
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.listing import Listing
from app.models.location import District, Ward
from app.repositories.listing_repository import ListingRepository
from app.schemas.analytics import PriceStatsByArea, PriceStatsGeneral, PriceStatsResponse
from app.schemas.listing import ListingResponse, VectorSearchResult
from app.schemas.room_type import ROOM_TYPE_CODE_TO_ID
from app.services.reranker import explain_match, rerank
from app.services.embedding import EmbeddingModel


def month_boundaries(reference: Optional[datetime] = None) -> tuple[datetime, datetime]:
    current = reference or datetime.now()
    current_start = datetime(current.year, current.month, 1)
    previous_start = datetime(current.year - 1, 12, 1) if current.month == 1 else datetime(current.year, current.month - 1, 1)
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
        room_type_id: Optional[int]
    ) -> PriceStatsResponse:
        current_month, prev_month = month_boundaries()

        base_filters = [
            Listing.region_id == city_id,
            Listing.price_vnd.isnot(None),
            Listing.price_vnd > 0,
        ]
        if district_id is not None:
            base_filters.append(Listing.district_id == district_id)
        if room_type_id is not None:
            base_filters.append(Listing.room_type_id == room_type_id)

        total_count, overall_avg, overall_min, overall_max = self.repository.price_aggregates(base_filters)

        cur_filters = list(base_filters) + [Listing.posted_date >= current_month]
        prev_filters = list(base_filters) + [Listing.posted_date >= prev_month, Listing.posted_date < current_month]
        _, cur_avg = self.repository.count_and_average(cur_filters)
        _, prev_avg = self.repository.count_and_average(prev_filters)

        def _calc_growth(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
            if cur is None or prev is None or prev == 0:
                return None
            return round(((cur - prev) / prev) * 100, 2)

        effective_avg = cur_avg if (cur_avg and cur_avg > 0) else overall_avg

        general = PriceStatsGeneral(
            total_listings=total_count,
            average_price_vnd=round(effective_avg, 2) if effective_avg else None,
            minimum_price_vnd=round(overall_min, 2) if overall_min else None,
            maximum_price_vnd=round(overall_max, 2) if overall_max else None,
            price_fluctuation_month=_calc_growth(cur_avg, prev_avg),
        )

        by_area_records = []
        if district_id is not None:
            query = (
                self.db.query(
                    Ward.id,
                    Ward.name,
                    func.count(Listing.id).label("total_listings"),
                    func.avg(Listing.price_vnd).label("average_price_vnd"),
                    func.min(Listing.price_vnd).label("minimum_price_vnd"),
                    func.max(Listing.price_vnd).label("maximum_price_vnd"),
                )
                .join(Listing, Listing.ward_id == Ward.id)
                .filter(
                    Listing.district_id == district_id,
                    Listing.price_vnd.isnot(None),
                    Listing.price_vnd > 0,
                )
                .group_by(Ward.id, Ward.name)
            )
            if room_type_id is not None:
                query = query.filter(Listing.room_type_id == room_type_id)

            rows = query.all()
            for r in rows:
                by_area_records.append(
                    PriceStatsByArea(
                        area_id=r.id,
                        area=r.name,
                        total_listings=r.total_listings,
                        average_price_vnd=round(r.average_price_vnd, 2) if r.average_price_vnd else 0.0,
                        minimum_price_vnd=round(r.minimum_price_vnd, 2) if r.minimum_price_vnd else None,
                        maximum_price_vnd=round(r.maximum_price_vnd, 2) if r.maximum_price_vnd else None,
                    )
                )
        else:
            query = (
                self.db.query(
                    District.id,
                    District.name,
                    func.count(Listing.id).label("total_listings"),
                    func.avg(Listing.price_vnd).label("average_price_vnd"),
                    func.min(Listing.price_vnd).label("minimum_price_vnd"),
                    func.max(Listing.price_vnd).label("maximum_price_vnd"),
                )
                .join(Listing, Listing.district_id == District.id)
                .filter(
                    Listing.region_id == city_id,
                    Listing.price_vnd.isnot(None),
                    Listing.price_vnd > 0,
                )
                .group_by(District.id, District.name)
            )
            if room_type_id is not None:
                query = query.filter(Listing.room_type_id == room_type_id)

            rows = query.all()
            for r in rows:
                by_area_records.append(
                    PriceStatsByArea(
                        area_id=r.id,
                        area=r.name,
                        total_listings=r.total_listings,
                        average_price_vnd=round(r.average_price_vnd, 2) if r.average_price_vnd else 0.0,
                        minimum_price_vnd=round(r.minimum_price_vnd, 2) if r.minimum_price_vnd else None,
                        maximum_price_vnd=round(r.maximum_price_vnd, 2) if r.maximum_price_vnd else None,
                    )
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
        room_type_id: Optional[int] = None,
        room_type: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_area: Optional[float] = None,
        max_area: Optional[float] = None,
        max_distance_km: Optional[float] = 8.0,
        limit: int = 5,
        offset: int = 0,
    ) -> list[VectorSearchResult]:
        raw_vector = model_embedding.encode_query(query)
        query_vector: list[float] = raw_vector.tolist() # type: ignore

        # Tự động chuyển đổi room_type (chuỗi như 'ROOM', 'STUDIO') thành room_type_id nếu cần
        resolved_room_type_id = room_type_id
        if resolved_room_type_id is None and room_type:
            resolved_room_type_id = ROOM_TYPE_CODE_TO_ID.get(room_type.strip().upper())

        repo_kwargs: dict[str, object] = {
            "query_vector": query_vector,
            "query_text": query,
            "city_id": city_id,
            "district_id": district_id,
            "ward_id": ward_id,
            "room_type_id": resolved_room_type_id,
            "min_price": min_price,
            "max_price": max_price,
            "min_area": min_area,
            "max_area": max_area,
            "lat": lat,
            "lng": lng,
            "max_distance_km": max_distance_km,
            "amenities": amenities,
            "limit": 50,
        }
        model_name = model_embedding.model_name.strip()
        repo_kwargs["model_name"] = model_name

        candidates = self.repository.vector_search(**repo_kwargs) # type: ignore

        if not candidates:
            return []

        user_pref: dict[str, object] = {
            "lat": lat,
            "lng": lng,
            "amenities": amenities,
            "preferred_amenities": preferred_amenities,
            "min_price": min_price,
            "max_price": max_price,
            "query": query,
            "room_type_id": resolved_room_type_id,
            "room_type": room_type,
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
