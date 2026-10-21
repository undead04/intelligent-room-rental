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

    def nearby_locations(
        self,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        district_id: Optional[int] = None,
        ward_id: Optional[int] = None,
        city_id: Optional[int] = None,
        radius_km: float = 12.0,
        limit: int = 4,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        room_type: Optional[str] = None,
        amenities: Optional[list[str]] = None,
    ):
        return self.repository.nearby_locations(
            lat=lat,
            lng=lng,
            district_id=district_id,
            ward_id=ward_id,
            city_id=city_id,
            radius_km=radius_km,
            limit=limit,
            min_price=min_price,
            max_price=max_price,
            room_type=room_type,
            amenities=amenities,
        )
