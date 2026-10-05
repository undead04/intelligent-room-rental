from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Query, Session, joinedload

from app.models.listing import Listing


class ListingRepository:
    def __init__(self, db: Session):
        self.db = db

    def base_query(self) -> Query:
        return self.db.query(Listing).options(
            joinedload(Listing.city),
            joinedload(Listing.district),
            joinedload(Listing.ward),
            joinedload(Listing.room_type),
        )

    def filtered_query(
        self,
        *,
        search: Optional[str],
        city_id: Optional[int],
        district_id: Optional[int],
        ward_id: Optional[int],
        room_type_id: Optional[int],
        min_price: Optional[float],
        max_price: Optional[float],
        min_area: Optional[float],
        max_area: Optional[float],
    ) -> Query:
        query = self.base_query()
        if search:
            pattern = f"%{search}%"
            query = query.filter(or_(Listing.title.ilike(pattern), Listing.address_raw.ilike(pattern)))
        for column, value in (
            (Listing.region_id, city_id),
            (Listing.district_id, district_id),
            (Listing.ward_id, ward_id),
            (Listing.room_type_id, room_type_id),
        ):
            if value is not None:
                query = query.filter(column == value)
        if min_price is not None:
            query = query.filter(Listing.price_vnd >= min_price)
        if max_price is not None:
            query = query.filter(Listing.price_vnd <= max_price)
        if min_area is not None:
            query = query.filter(Listing.area_m2 >= min_area)
        if max_area is not None:
            query = query.filter(Listing.area_m2 <= max_area)
        return query

    def search(
        self,
        *,
        search: Optional[str],
        city_id: Optional[int],
        district_id: Optional[int],
        ward_id: Optional[int],
        room_type_id: Optional[int],
        min_price: Optional[float],
        max_price: Optional[float],
        min_area: Optional[float],
        max_area: Optional[float],
        order_by: str,
        sort_desc: bool,
        limit: int,
        offset: int,
    ) -> list[Listing]:
        query = self.filtered_query(
            search=search,
            city_id=city_id,
            district_id=district_id,
            ward_id=ward_id,
            room_type_id=room_type_id,
            min_price=min_price,
            max_price=max_price,
            min_area=min_area,
            max_area=max_area,
        )
        sort_column = getattr(Listing, order_by)
        query = query.order_by(sort_column.desc() if sort_desc else sort_column)
        return query.offset(offset).limit(limit).all()

    def count(
        self,
        *,
        search: Optional[str],
        city_id: Optional[int],
        district_id: Optional[int],
        ward_id: Optional[int],
        room_type_id: Optional[int],
        min_price: Optional[float],
        max_price: Optional[float],
        min_area: Optional[float],
        max_area: Optional[float],
    ) -> int:
        query = self.filtered_query(
            search=search,
            city_id=city_id,
            district_id=district_id,
            ward_id=ward_id,
            room_type_id=room_type_id,
            min_price=min_price,
            max_price=max_price,
            min_area=min_area,
            max_area=max_area,
        )
        return query.order_by(None).count()

    def get_by_id(self, listing_id: str) -> Optional[Listing]:
        return (
            self.base_query()
            .options(joinedload(Listing.poster))
            .filter(Listing.id == listing_id)
            .one_or_none()
        )

    def count_and_average(self, filters: list) -> tuple[int, Optional[float]]:
        return self.db.query(
            func.count(Listing.id),
            func.avg(Listing.price_vnd),
        ).filter(*filters).one()
