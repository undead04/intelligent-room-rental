from datetime import datetime
from typing import Optional, Any

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.listing import Listing
from app.models.location import District, Ward
from app.repositories.listing_repository import ListingRepository
from app.schemas.analytics import PriceStatsByArea, PriceStatsGeneral, PriceStatsResponse
from app.schemas.listing import ListingResponse, VectorSearchResult
from app.services.reranker import DEFAULT_WEIGHTS, explain_match, rerank
from app.services.embedding import EmbeddingModel


def month_boundaries(reference: Optional[datetime] = None) -> tuple[datetime, datetime]:
    current = reference or datetime.now()
    current_start = datetime(current.year, current.month, 1)
    previous_start = datetime(current.year - 1, 12, 1) if current.month == 1 else datetime(current.year, current.month - 1, 1)
    return current_start, previous_start


class ListingService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = ListingRepository(db)

    def list_listings(self, **filters) -> list[Listing]:
        order_by = filters["order_by"]
        if order_by not in Listing.__table__.columns.keys():
            raise BadRequestException(f"Invalid order_by field: {order_by}", {"field": order_by})
        return self.repository.search(**filters)

    def count_listings(self, **filters) -> int:
        return self.repository.count(**filters)

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
        if district_id is not None:
            district = self.db.query(District).filter(District.id == district_id).one_or_none()
            if district is None:
                raise NotFoundException("District not found", {"district_id": district_id})
            if district.city_id != city_id:
                raise BadRequestException("district_id does not belong to city_id")

        filters = [Listing.region_id == city_id, Listing.price_vnd.isnot(None)]
        if district_id is not None:
            filters.append(Listing.district_id == district_id)
        if room_type_id is not None:
            filters.append(Listing.room_type_id == room_type_id)

        total, average = self.repository.count_and_average(filters)
        current_start, previous_start = month_boundaries()
        date_column = func.coalesce(Listing.posted_date, Listing.crawled_at)

        # 1. Tính biến động tăng/giảm giá trung bình của toàn thành phố / phạm vi query
        general_month_stats = self.db.query(
            func.avg(case((date_column >= current_start, Listing.price_vnd))).label("current_average"),
            func.avg(case(((date_column >= previous_start) & (date_column < current_start), Listing.price_vnd))).label("previous_average"),
        ).filter(*filters).one()

        price_fluctuation_month = None
        if general_month_stats.current_average is not None and general_month_stats.previous_average not in (None, 0):
            price_fluctuation_month = round(
                (general_month_stats.current_average - general_month_stats.previous_average)
                / general_month_stats.previous_average * 100,
                2
            )

        if district_id is None:
            area_model, area_column, area_name = District, Listing.district_id, District.name
            area_filter = District.id == Listing.district_id
        else:
            area_model, area_column, area_name = Ward, Listing.ward_id, Ward.name
            area_filter = Ward.id == Listing.ward_id

        # 2. Thống kê theo từng khu vực con, đồng thời đếm số lượng tin đăng tháng này và tháng trước
        area_query = (
            self.db.query(
                area_model.id.label("area_id"),
                area_name.label("area_name"),
                func.count(Listing.id).label("total_listings"),
                func.avg(Listing.price_vnd).label("average_price"),
                func.min(Listing.price_vnd).label("minimum_price"),
                func.max(Listing.price_vnd).label("maximum_price"),
                func.avg(case((date_column >= current_start, Listing.price_vnd))).label("current_average"),
                func.avg(case(((date_column >= previous_start) & (date_column < current_start), Listing.price_vnd))).label("previous_average"),
                func.count(case((date_column >= current_start, Listing.id))).label("current_listings_count"),
                func.count(case(((date_column >= previous_start) & (date_column < current_start), Listing.id))).label("previous_listings_count"),
            )
            .join(area_model, area_filter)
            .filter(*filters)
            .filter(area_column.isnot(None))
        )
        if district_id is not None:
            area_query = area_query.filter(Ward.district_id == district_id)
        rows = area_query.group_by(area_model.id, area_name).order_by(func.count(Listing.id).desc()).all()

        areas = []
        for row in rows:
            fluctuation = None
            if row.current_average is not None and row.previous_average not in (None, 0):
                fluctuation = round((row.current_average - row.previous_average) / row.previous_average * 100, 2)
            areas.append(PriceStatsByArea(
                area_id=row.area_id,
                area=row.area_name,
                total_listings=row.total_listings or 0,
                fluctuation_month=fluctuation,
                average_price_vnd=round(row.average_price, 2) if row.average_price is not None else None,
                minimum_price_vnd=round(row.minimum_price, 2) if row.minimum_price is not None else None,
                maximum_price_vnd=round(row.maximum_price, 2) if row.maximum_price is not None else None,
            ))

        # 3. Tính tỉ lệ phần trăm số tin đăng tuyển của khu vực hot nhất tăng so với tháng trước
        hotspot_posting_growth = None
        if rows:
            hotspot_row = rows[0]
            cur_count = hotspot_row.current_listings_count or 0
            prev_count = hotspot_row.previous_listings_count or 0
            if prev_count > 0:
                hotspot_posting_growth = round((cur_count - prev_count) / prev_count * 100, 2)
            elif cur_count > 0:
                hotspot_posting_growth = 100.0

        return PriceStatsResponse(
            price_stats_general=PriceStatsGeneral(
                total_listings=total or 0,
                average_price_vnd=round(average, 2) if average is not None else None,
                price_fluctuation_month=price_fluctuation_month,
                area_hotspot=areas[0].area if areas else None,
                hotspot_posting_growth_month=hotspot_posting_growth,
            ),
            price_stats_by_area=areas,
        )

    def get_listings_by_ids(self, ids: list[str], preserve_order: bool = True) -> list[Listing]:
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
        model_embedding: Any,
        lat: float | None = None,
        lng: float | None = None,
        amenities: list[str] | None = None,
        weights: dict[str, float] | None = None,
        city_id: int | None = None,
        district_id: int | None = None,
        ward_id: int | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        min_area: float | None = None,
        max_area: float | None = None,
        limit: int = 5,
        offset: int = 0,
    ) -> list[VectorSearchResult]:
        if hasattr(model_embedding, "encode_query"):
            raw_vector = model_embedding.encode_query(query)
        else:
            raw_vector = model_embedding.encode([query])[0]
        query_vector = raw_vector.tolist() if hasattr(raw_vector, "tolist") else list(raw_vector)

        repo_kwargs: dict[str, Any] = {
            "query_vector": query_vector,
            "query_text": query,
            "city_id": city_id,
            "district_id": district_id,
            "ward_id": ward_id,
            "min_price": min_price,
            "max_price": max_price,
            "min_area": min_area,
            "max_area": max_area,
            "limit": 50,
        }
        model_name = getattr(model_embedding, "model_name", None)
        if isinstance(model_name, str) and model_name.strip():
            import inspect
            try:
                sig = inspect.signature(self.repository.vector_search)
                if "model_name" in sig.parameters:
                    repo_kwargs["model_name"] = model_name.strip()
            except (ValueError, TypeError):
                pass

        candidates = self.repository.vector_search(**repo_kwargs)

        if not candidates:
            return []

        user_pref = {
            "lat": lat,
            "lng": lng,
            "amenities": amenities,
            "min_price": min_price,
            "max_price": max_price,
            "query": query,
        }

        reranked = rerank(
            candidates=candidates,
            user_pref=user_pref,
            base_weights=weights or DEFAULT_WEIGHTS,
            limit=limit,
            offset=offset,
        )
        def _unwrap(candidate):
            """Candidate từ repository có thể là dict {'listing': ORM, ...scores} hoặc ORM thuần."""
            return candidate["listing"] if isinstance(candidate, dict) and "listing" in candidate else candidate
        return [
            VectorSearchResult(
                listing=ListingResponse.model_validate(_unwrap(listing)),
                match_score=breakdown["score"],
                explain_match=explain_match(breakdown),
            )
            for breakdown, listing in reranked
        ]
