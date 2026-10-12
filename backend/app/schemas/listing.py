from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    images: Optional[list[str]] = None
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


class VectorSearchResult(BaseModel):
    listing: ListingResponse
    match_score: float
    explain_match: Optional[dict] = None
    model_config = ConfigDict(from_attributes=True)

class VectorSearchRequest(BaseModel):
    lat: Optional[float] = Field(None, description="Vĩ độ người dùng")
    lng: Optional[float] = Field(None, description="Kinh độ người dùng")
    city_id: Optional[int] = Field(None, ge=1)
    district_id: Optional[int] = Field(None, ge=1)
    ward_id: Optional[int] = Field(None, ge=1)
    min_price: Optional[float] = Field(None, ge=0)
    max_price: Optional[float] = Field(None, ge=0)
    min_area: Optional[float] = Field(None, ge=0)
    max_area: Optional[float] = Field(None, ge=0)
    limit: int = Field(5, ge=1, le=100)
    offset: int = Field(0, ge=0)

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def validate_ranges(self) -> "VectorSearchRequest":
        if self.min_price is not None and self.max_price is not None:
            if self.min_price > self.max_price:
                raise ValueError("min_price không được lớn hơn max_price")
        if self.min_area is not None and self.max_area is not None:
            if self.min_area > self.max_area:
                raise ValueError("min_area không được lớn hơn max_area")
        return self