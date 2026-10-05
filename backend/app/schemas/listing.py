from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.user import UserResponse


class CityReference(BaseModel):
    id: int
    name: str
    region_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class DistrictReference(BaseModel):
    id: int
    name: str
    district_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class WardReference(BaseModel):
    id: int
    name: str
    ward_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class RoomTypeReference(BaseModel):
    id: int
    room_type: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class ListingResponse(BaseModel):
    id: str
    title: str
    source: Optional[str] = None
    url: Optional[str] = None
    price_vnd: Optional[float] = None
    area_m2: Optional[float] = None
    address_raw: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    main_image: Optional[str] = None
    price_string: Optional[str] = None
    city: Optional[CityReference] = None
    district: Optional[DistrictReference] = None
    ward: Optional[WardReference] = None
    room_type: Optional[RoomTypeReference] = None
    posted_date: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class ListingDetailResponse(ListingResponse):
    description: Optional[str] = None
    images: Optional[List[str]] = None
    price_million_per_m2: Optional[float] = None
    deposit: Optional[float] = None
    furnishing_code: Optional[int] = None
    crawled_at: Optional[datetime] = None
    safety_score: Optional[float] = None
    concept_scores: Optional[dict] = None
    poster: Optional[UserResponse] = None


class ListingCreate(BaseModel):
    list_id: str
    title: str
    source: Optional[str] = "nhatot"
    url: Optional[str] = None
    description: Optional[str] = None
    price_vnd: Optional[float] = None
    area_m2: Optional[float] = None
    address_raw: Optional[str] = None
    city_id: Optional[int] = None
    district_id: Optional[int] = None
    ward_id: Optional[int] = None
    room_type_id: Optional[int] = None
