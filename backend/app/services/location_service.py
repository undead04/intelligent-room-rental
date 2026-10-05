from typing import Optional

from sqlalchemy.orm import Session

from app.repositories.location_repository import LocationRepository


class LocationService:
    def __init__(self, db: Session):
        self.repository = LocationRepository(db)

    def cities(self, search: Optional[str] = None):
        return self.repository.cities(search)

    def districts(self, city_id: Optional[int] = None, search: Optional[str] = None):
        return self.repository.districts(city_id, search)

    def wards(self, district_id: Optional[int] = None, search: Optional[str] = None):
        return self.repository.wards(district_id, search)

    def room_types(self, search: Optional[str] = None):
        return self.repository.room_types(search)
