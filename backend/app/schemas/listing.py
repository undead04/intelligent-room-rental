from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.user import UserResponse


class ListingBase(BaseModel):
    listing_id: str = Field(..., description="ID duy nhất của tin đăng")
    title: str = Field(..., description="Tiêu đề tin đăng")
    price_vnd: Optional[float] = Field(None, description="Giá thuê VNĐ/tháng")
    area_m2: Optional[float] = Field(None, description="Diện tích (m²)")
    address_raw: Optional[str] = Field(None, description="Địa chỉ thô")
    lat: Optional[float] = Field(None, description="Vĩ độ")
    lng: Optional[float] = Field(None, description="Kinh độ")
    main_image: Optional[str] = Field(None, description="Ảnh đại diện bài đăng")
    room_type: Optional[str] = Field(None, description="Loại hình phòng trọ/chung cư")


class ListingCreate(ListingBase):
    ad_id: Optional[str] = None
    list_id: Optional[str] = None
    source: Optional[str] = "nhatot"
    url: Optional[str] = None
    description: Optional[str] = None
    images: Optional[List[str]] = []
    price_string: Optional[str] = None
    price_million_per_m2: Optional[float] = None
    deposit: Optional[float] = None
    furnishing: Optional[str] = None
    furnishing_code: Optional[int] = None
    category_id: Optional[int] = None
    street_name: Optional[str] = None
    ward: Optional[str] = None
    district: Optional[str] = None
    city: Optional[str] = None
    ward_id: Optional[int] = None
    district_id: Optional[int] = None
    region_id: Optional[int] = None
    poster_id: Optional[str] = None
    posted_date: Optional[datetime] = None
    crawled_at: Optional[datetime] = None


class ListingResponse(ListingBase):
    price_string: Optional[str] = None
    price_million_per_m2: Optional[float] = None
    deposit: Optional[float] = None
    furnishing: Optional[str] = None
    room_type: Optional[str] = None
    district: Optional[str] = None
    city: Optional[str] = None
    poster_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ListingDetailResponse(ListingResponse):
    ad_id: Optional[str] = None
    list_id: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    images: Optional[List[str]] = []
    furnishing_code: Optional[int] = None
    category_id: Optional[int] = None
    street_name: Optional[str] = None
    ward: Optional[str] = None
    ward_id: Optional[int] = None
    district_id: Optional[int] = None
    region_id: Optional[int] = None
    posted_date: Optional[datetime] = None
    crawled_at: Optional[datetime] = None
    
    # Nested relationship to poster
    poster: Optional[UserResponse] = None

    model_config = ConfigDict(from_attributes=True)
