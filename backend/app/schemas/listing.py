from datetime import datetime
from typing import Optional
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.user import UserResponse
from app.schemas.location import CityResponse, DistrictResponse, WardResponse
from app.schemas.room_type import RoomType, RoomTypeResponse, RoomTypeReference, ROOM_TYPE_CODE_TO_ID


class AmenityCode(str, Enum):
    """Danh mục tiện ích, quy định và an ninh chuẩn hóa (Canonical Taxonomy).
    Giá trị dạng snake_case khớp 1-1 với field name trong ListingExtraction.
    Dùng cho UI Checkbox, Filter cứng và công thức tính trọng số Rerank.
    """
    def __str__(self) -> str:
        return str(self.value)

    # 1. Tiện ích phòng cốt lõi (Core Amenities)
    PRIVATE_WC = "private_wc"              # WC riêng, khép kín
    AIRCON = "aircon"                      # Máy lạnh, điều hòa
    MEZZANINE = "mezzanine"                # Gác lửng, gác xép
    KITCHEN = "kitchen"                    # Kệ bếp, khu nấu ăn riêng
    FRIDGE = "fridge"                      # Tủ lạnh
    WASHING_MACHINE = "washing_machine"    # Máy giặt (chung hoặc riêng)
    WINDOW_BALCONY = "window_balcony"      # Ban công hoặc cửa sổ thoáng
    FURNITURE = "furniture"                # Đầy đủ nội thất (giường, tủ, bàn học...)
    PARKING = "parking"                    # Chỗ để xe trong nhà / hầm xe
    ELEVATOR = "elevator"                  # Thang máy

    # 2. Quy định & Lối sống (Rules & Lifestyle)
    FREE_HOURS = "free_hours"              # Giờ giấc tự do (không khóa cổng)
    NO_SHARED_LANDLORD = "no_shared_landlord"  # Không chung chủ
    PET_ALLOWED = "pet_allowed"            # Cho phép nuôi thú cưng (chó, mèo)

    # 3. An toàn & An ninh (Safety)
    FINGERPRINT_LOCK = "fingerprint_lock"  # Khóa vân tay, cổng thẻ từ
    CAMERA = "camera"                      # Camera an ninh 24/7
    GUARD = "guard"                        # Bảo vệ trực cổng 24/7
    SAFE_AREA = "safe_area"                # Khu vực an ninh, yên tĩnh


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
    concept_scores: Optional[dict[str, float]] = None
    city: Optional[CityResponse] = None
    district: Optional[DistrictResponse] = None
    ward: Optional[WardResponse] = None
    room_type: Optional[RoomTypeResponse] = None
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
    """Request Body cho tìm kiếm Vector Embedding kèm Rerank đa tiêu chí.
    Toàn bộ tham số được truyền trực tiếp qua JSON Body.
    """
    query: str = Field(..., min_length=1, description="Câu truy vấn tự nhiên của người dùng")
    amenities: Optional[list[AmenityCode]] = Field(default=None, description="Danh sách tiện ích bắt buộc theo định dạng AmenityCode")
    preferred_amenities: Optional[list[AmenityCode]] = Field(default=None, description="Danh sách tiện ích ưu tiên mềm (có càng tốt)")
    weights: Optional[dict[str, float]] = Field(
        default=None,
        description="Trọng số MCDM tùy chỉnh (vd: {'price': 0.35, 'location': 0.35, ...})",
    )
    lat: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Vĩ độ mục tiêu người dùng")
    lng: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Kinh độ mục tiêu người dùng")
    max_distance_km: Optional[float] = Field(default=8.0, ge=0.5, le=50.0, description="Bán kính tìm kiếm tối đa quanh toạ độ (km)")
    city_id: Optional[int] = Field(None, ge=1, description="ID Tỉnh/Thành phố")
    district_id: Optional[int] = Field(None, ge=1, description="ID Quận/Huyện")
    ward_id: Optional[int] = Field(None, ge=1, description="ID Phường/Xã")
    room_type_id: Optional[int] = Field(None, ge=1, le=5, description="ID loại phòng (1..5)")
    room_type: Optional[str] = Field(None, description="Mã loại phòng (ROOM, STUDIO, APARTMENT, SLEEPBOX, WHOLE_HOUSE)")
    min_price: Optional[float] = Field(None, ge=0, description="Giá tối thiểu (VNĐ)")
    max_price: Optional[float] = Field(None, ge=0, description="Giá tối đa (VNĐ)")
    min_area: Optional[float] = Field(None, ge=0, description="Diện tích tối thiểu (m2)")
    max_area: Optional[float] = Field(None, ge=0, description="Diện tích tối đa (m2)")
    limit: int = Field(default=5, ge=1, le=100, description="Số lượng kết quả trả về")
    offset: int = Field(default=0, ge=0, description="Số lượng kết quả bỏ qua")

    @field_validator("query")
    @classmethod
    def validate_query_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("query không được để trống")
        return v.strip()

    @field_validator("room_type")
    @classmethod
    def validate_room_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.value if hasattr(v, "value") else str(v).strip().upper()
            if clean not in ROOM_TYPE_CODE_TO_ID:
                valid_codes = list(ROOM_TYPE_CODE_TO_ID.keys())
                raise ValueError(f"room_type '{v}' không hợp lệ. Phải là một trong: {valid_codes}")
            return clean
        return v

    @model_validator(mode="after")
    def validate_ranges_and_constraints(self) -> "VectorSearchBody":
        if self.min_price is not None and self.max_price is not None:
            if self.min_price > self.max_price:
                raise ValueError("min_price không được lớn hơn max_price")
        if self.min_area is not None and self.max_area is not None:
            if self.min_area > self.max_area:
                raise ValueError("min_area không được lớn hơn max_area")
        # Cách 1: Tự động đồng bộ room_type_id nếu có room_type
        if self.room_type_id is None and self.room_type is not None:
            clean = self.room_type.value if hasattr(self.room_type, "value") else str(self.room_type).strip().upper()
            self.room_type_id = ROOM_TYPE_CODE_TO_ID.get(clean)
        return self


VectorSearchQueryFilters = VectorSearchBody
VectorSearchRequest = VectorSearchBody


class VectorSearchResult(BaseModel):
    listing: ListingResponse
    match_score: float
    explain_match: Optional[dict[str, object]] = None

    model_config = ConfigDict(from_attributes=True)


class ListingCountResponse(BaseModel):
    total_listings: int
