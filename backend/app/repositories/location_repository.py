from typing import Optional

from sqlalchemy.orm import Session

from app.models.location import City, District, Ward
from app.models.room_type import RoomType


class LocationRepository:
    def __init__(self, db: Session):
        self.db = db

    def cities(self, search: Optional[str]) -> list[City]:
        query = self.db.query(City)
        if search:
            query = query.filter(City.name.ilike(f"%{search}%"))
        return query.order_by(City.name).all()

    def districts(self, city_id: Optional[int], search: Optional[str]) -> list[District]:
        query = self.db.query(District)
        if city_id is not None:
            query = query.filter(District.city_id == city_id)
        if search:
            query = query.filter(District.name.ilike(f"%{search}%"))
        return query.order_by(District.name).all()

    def wards(self, district_id: Optional[int], search: Optional[str]) -> list[Ward]:
        query = self.db.query(Ward)
        if district_id is not None:
            query = query.filter(Ward.district_id == district_id)
        if search:
            query = query.filter(Ward.name.ilike(f"%{search}%"))
        return query.order_by(Ward.name).all()

    def room_types(self, search: Optional[str]) -> list[RoomType]:
        query = self.db.query(RoomType)
        if search:
            query = query.filter(RoomType.room_type.ilike(f"%{search}%"))
        return query.order_by(RoomType.room_type).all()
