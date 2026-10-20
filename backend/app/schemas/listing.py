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
    name: Optional[str] = None
    room_type: Optional[str] = None
    code: Optional[str] = None
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
    images: Optional[list[str]] = None
    price_string: Optional[str] = None
    price_score: Optional[float] = None
    safety_score: Optional[float] = None
    amenity_overall: Optional[float] = None
    concept_scores: Optional[dict] = None
    city: Optional[CityReference] = None
    district: Optional[DistrictReference] = None
    ward: Optional[WardReference] = None
    room_type: Optional[RoomTypeReference] = None
    posted_date: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class ListingDetailResponse(ListingResponse):
    """Chi tiết tin đăng mở rộng từ ListingResponse."""
    description: Optional[str] = None
    price_million_per_m2: Optional[float] = None
    deposit: Optional[float] = None
    furnishing_code: Optional[int] = None
    crawled_at: Optional[datetime] = None
    poster: Optional[UserResponse] = None


class ListingFilterParams(BaseModel):
    """Gom nhóm các bộ lọc tìm kiếm tin đăng."""
    search: Optional[str] = Field(None, description="Từ khóa tìm kiếm trong tiêu đề hoặc địa chỉ")
    city_id: Optional[int] = Field(None, ge=1, description="ID Tỉnh/Thành phố")
    district_id: Optional[int] = Field(None, ge=1, description="ID Quận/Huyện")
    ward_id: Optional[int] = Field(None, ge=1, description="ID Phường/Xã")
    room_type_id: Optional[int] = Field(None, ge=1, description="ID loại phòng")
    min_price: Optional[float] = Field(None, ge=0, description="Giá thấp nhất (VND)")
    max_price: Optional[float] = Field(None, ge=0, description="Giá cao nhất (VND)")
    min_area: Optional[float] = Field(None, ge=0, description="Diện tích nhỏ nhất (m2)")
    max_area: Optional[float] = Field(None, ge=0, description="Diện tích lớn nhất (m2)")

    @model_validator(mode="after")
    def validate_ranges(self) -> "ListingFilterParams":
        if self.min_price is not None and self.max_price is not None:
            if self.min_price > self.max_price:
                raise ValueError("min_price không được lớn hơn max_price")
        if self.min_area is not None and self.max_area is not None:
            if self.min_area > self.max_area:
                raise ValueError("min_area không được lớn hơn max_area")
        return self


class ListingPaginationParams(BaseModel):
    """Gom nhóm các tham số phân trang và sắp xếp."""
    limit: int = Field(20, ge=1, le=100, description="Số lượng kết quả mỗi trang")
    offset: int = Field(0, ge=0, description="Số lượng kết quả bỏ qua")
    order_by: str = Field("posted_date", description="Trường cần sắp xếp")
    sort_desc: bool = Field(True, description="Sắp xếp giảm dần nếu True")


class ListingQueryParams(ListingFilterParams, ListingPaginationParams):
    """Tổng hợp cả lọc và phân trang cho danh sách tin đăng."""
    pass


class ListingIdsRequest(BaseModel):
    """Request lấy danh sách phòng theo ID."""
    ids: list[str] = Field(
        ...,
        min_length=1,
        description="Danh sách ID bài đăng cần truy vấn",
        examples=[["nhatot_12345", "nhatot_67890"]],
    )


class VectorSearchBody(BaseModel):
    """Request Body cho tìm kiếm Vector Embedding."""
    query: str = Field(..., description="Câu truy vấn tự nhiên của người dùng")
    amenities: Optional[list[str]] = Field(default=None, description="Danh sách tiện ích yêu cầu")
    weights: Optional[dict[str, float]] = Field(
        default=None,
        description="Trọng số MCDM tùy chỉnh (vd: {'price': 0.35, 'location': 0.35, ...})",
    )
    # Tùy chọn truyền filters trực tiếp trong JSON body (thay vì URL query)
    lat: Optional[float] = Field(None, description="Vĩ độ người dùng")
    lng: Optional[float] = Field(None, description="Kinh độ người dùng")
    city_id: Optional[int] = Field(None, ge=1)
    district_id: Optional[int] = Field(None, ge=1)
    ward_id: Optional[int] = Field(None, ge=1)
    min_price: Optional[float] = Field(None, ge=0)
    max_price: Optional[float] = Field(None, ge=0)
    min_area: Optional[float] = Field(None, ge=0)
    max_area: Optional[float] = Field(None, ge=0)
    limit: Optional[int] = Field(None, ge=1, le=100)
    offset: Optional[int] = Field(None, ge=0)


class VectorSearchQueryFilters(BaseModel):
    """Filters nhận từ Query Params cho Vector Search (tương thích ngược với ai-agent)."""
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

    @model_validator(mode="after")
    def validate_ranges(self) -> "VectorSearchQueryFilters":
        if self.min_price is not None and self.max_price is not None:
            if self.min_price > self.max_price:
                raise ValueError("min_price không được lớn hơn max_price")
        if self.min_area is not None and self.max_area is not None:
            if self.min_area > self.max_area:
                raise ValueError("min_area không được lớn hơn max_area")
        return self


# Alias cho tương thích ngược
VectorSearchRequest = VectorSearchQueryFilters


class VectorSearchResult(BaseModel):
    listing: ListingResponse
    match_score: float
    explain_match: Optional[dict] = None
    model_config = ConfigDict(from_attributes=True)
