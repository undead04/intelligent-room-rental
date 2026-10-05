from datetime import datetime
from typing import Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.listing import Listing
from app.models.location import City, District, Ward
from app.repositories.listing_repository import ListingRepository
from app.schemas.analytics import PriceStatsByArea, PriceStatsGeneral, PriceStatsResponse


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
        room_type_id: Optional[int],
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
        if district_id is None:
            area_model, area_column, area_name = District, Listing.district_id, District.name
            area_filter = District.id == Listing.district_id
        else:
            area_model, area_column, area_name = Ward, Listing.ward_id, Ward.name
            area_filter = Ward.id == Listing.ward_id

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
        return PriceStatsResponse(
            price_stats_general=PriceStatsGeneral(
                total_listings=total or 0,
                average_price_vnd=round(average, 2) if average is not None else None,
                area_hotspot=areas[0].area if areas else None,
            ),
            price_stats_by_area=areas,
        )
