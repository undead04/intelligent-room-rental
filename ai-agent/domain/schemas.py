"""Pydantic schemas cho AI Agent: chuẩn hoá dữ liệu vào/ra, khớp frontend Tim-Kiem-AI và backend Smart Housing.

Các đặc điểm chính:
  - Tiện ích / loại phòng là enum (domain.enums), UserPreferenceState tự chuẩn hoá khi gán (validate_assignment).
  - room_type_id là property chỉ đọc, suy ra từ room_type.
  - UserPreferenceState.set_location(): đổi vị trí => xoá toạ độ/ID cũ ở MỘT chỗ.
  - RoomItem: chuẩn hoá diện tích (area_m2), điểm phù hợp %, phân biệt thẻ xác thực và thẻ suy đoán ML (inferred_tags).
  - GroundingReport: báo cáo kiểm định 2 tầng (Context Grounding & Answer Grounding) kèm vết retry.
  - MarketContext: phản ánh khoảng trống thị trường khi 0 phòng và đề xuất ngân sách nới lỏng.
"""

from __future__ import annotations

import re
import zlib
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from domain.enums import (
    Amenity,
    RoomType,
    normalize_amenities,
    normalize_room_type,
    normalize_room_types,
)
from utils.geo import haversine_km


def format_vnd_million(val_vnd: Optional[float]) -> str:
    """Format số tiền VND sang chuỗi triệu/tháng chuẩn hoá (ví dụ: '3.5 triệu/tháng')."""
    if val_vnd is None or val_vnd <= 0:
        return "Thỏa thuận"
    if val_vnd >= 1_000_000:
        val = val_vnd / 1_000_000.0
        formatted = f"{val:.2f}".rstrip("0").rstrip(".")
        return f"{formatted} triệu/tháng"
    return f"{val_vnd:,.0f} đ/tháng"


_FACTOR_TAGS = {
    "price": "Giá tốt",
    "location": "Vị trí gần",
    "amenity": "Đủ tiện nghi",
    "safety": "An ninh cao",
    "semantic": "Khớp mô tả",
}

# concept_scores của backend là điểm ML (suy đoán) -> KHÔNG coi là sự thật đã xác thực
_CONCEPT_TAGS = {
    "aircon": "Có máy lạnh",
    "mezzanine": "Có gác lửng",
    "private_wc": "WC riêng",
    "free_hours": "Giờ tự do",
    "pet_allowed": "Nuôi thú cưng",
    "window_balcony": "Có ban công",
    "kitchen": "Có bếp",
    "furniture": "Có nội thất",
    "fridge": "Có tủ lạnh",
    "elevator": "Có thang máy",
    "parking": "Có chỗ đỗ xe",
    "washing_machine": "Có máy giặt",
    "no_shared_landlord": "Không chung chủ",
    "fingerprint_lock": "Khóa vân tay",
    "camera": "Camera an ninh",
    "guard": "Bảo vệ 24/7",
    "safe_area": "Khu an ninh",
}
_CONCEPT_THRESHOLD = 0.75

_RANK_TEXTS = {1: "Top 1 - Tối ưu nhất", 2: "Top 2 - Đề xuất", 3: "Top 3 - Lựa chọn tốt"}


def rank_text(rank: int) -> str:
    return _RANK_TEXTS.get(rank, f"Top {rank}")


def _room_type_from_listing(obj: Any) -> Optional[RoomType]:
    """Backend có thể trả room_type dạng dict (id/code/name) hoặc chuỗi/số. Không nhận ra -> None."""
    if isinstance(obj, dict):
        for key in ("id", "code", "name"):
            rt = normalize_room_type(obj.get(key))
            if rt is not None:
                return rt
        return None
    return normalize_room_type(obj)


class RoomItem(BaseModel):
    """Thông tin 1 phòng trọ chuẩn hoá trả về cho Frontend hiển thị trên Danh sách và Bản đồ.

    Vai trò trong hệ thống Homigo AI Agent:
    - Node Retrieval: Nhận kết quả từ `/listings/vector-search` và chuyển đổi qua `from_backend_result()`.
    - Node Decision: Cung cấp thông tin giá, vị trí, tiện ích để LLM phân tích Trade-offs và viết checklist xem phòng.
    - Node Verify: Đối soát giá tiền và mã phòng chống ảo giác dữ liệu (Self-RAG Grounding Check).
    - Frontend (/tim-kiem-ai): Render danh sách thẻ bài đăng (Cột 2) và ghim toạ độ lên Mapbox/Leaflet (Cột 3).
    """

    id: str = Field(..., description="ID định danh tin đăng")
    rank: int = Field(1, description="Thứ tự xếp hạng (1, 2, 3,...)")
    rankText: str = Field("Phù hợp nhất", description="Nhãn xếp hạng (Top 1, Top 2,...)")
    matchScore: float = Field(0.0, description="Điểm phù hợp tổng thể từ hệ thống rerank (0.0 - 1.0)")
    title: str = Field(..., description="Tiêu đề tin đăng")
    price: str = Field(..., description="Giá hiển thị (ví dụ: '2.8 triệu/tháng')")
    priceNum: float = Field(0.0, description="Giá số nguyên/thực (VNĐ)")
    area_m2: Optional[float] = Field(None, description="Diện tích (m²)")
    room_type: Optional[RoomType] = Field(None, description="Loại phòng (None nếu backend không cho biết)")
    address: str = Field("", description="Địa chỉ phòng (rỗng nếu backend không có)")
    distance: str = Field("", description="Khoảng cách tới điểm tìm kiếm (rỗng nếu không xác định được)")
    photoCount: int = Field(0, description="Số lượng ảnh")
    image: str = Field("", description="URL ảnh đại diện")
    tags: list[str] = Field(default_factory=list, description="Thẻ đã xác thực (diện tích, loại phòng, yếu tố rerank)")
    inferred_tags: list[str] = Field(default_factory=list, description="Thẻ SUY ĐOÁN từ mô hình ML, chưa xác thực")
    lat: Optional[float] = Field(None, description="Vĩ độ thực tế")
    lng: Optional[float] = Field(None, description="Kinh độ thực tế")
    latPercent: float = Field(50.0, description="Toạ độ % tương đối để render pin lên map mock nếu cần")
    lngPercent: float = Field(50.0, description="Toạ độ % tương đối để render pin lên map mock nếu cần")
    source_url: Optional[str] = Field(None, description="Link gốc bài đăng")
    concept_scores: dict[str, float] = Field(default_factory=dict, description="Điểm concept ML cho từng tiện ích")
    explain_match: Optional[dict[str, Any]] = Field(None, description="Chi tiết giải thích từ rerank backend")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def match_percent(self) -> int:
        """Điểm phù hợp dạng % (LLM chỉ việc chép, không tự đổi thang 0-1)."""
        s = self.matchScore
        return round(s * 100) if s <= 1.0 else round(s)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def room_type_id(self) -> Optional[int]:
        """ID số của loại phòng (1: Phòng trọ, 2: Studio, 3: Căn hộ, 4: Sleepbox/KTX, 5: Nhà nguyên căn)."""
        return self.room_type.type_id if self.room_type else None

    @classmethod
    def from_backend_result(
        cls,
        item: dict,
        rank: int = 1,
        target_lat: Optional[float] = None,
        target_lng: Optional[float] = None,
    ) -> "RoomItem":
        """Chuyển đổi từ VectorSearchResult của Backend sang RoomItem của Agent."""
        listing = item.get("listing") if isinstance(item.get("listing"), dict) else item
        explain = item.get("explain_match") or {}
        score = float(item.get("match_score") or 0.0)

        price_vnd = float(listing.get("price_vnd") or 0.0)
        price_str = format_vnd_million(price_vnd) if price_vnd > 0 else (listing.get("price_string") or "Thỏa thuận")

        area = listing.get("area_m2")
        try:
            area_f: Optional[float] = float(area) if area else None
        except (TypeError, ValueError):
            area_f = None

        tags: list[str] = []
        if area_f:
            tags.append(f"{area_f:g} m²")
        for factor in (explain.get("top_factors") or [])[:2]:
            label = _FACTOR_TAGS.get(factor.get("name"))
            if label and label not in tags:
                tags.append(label)
        room_type_obj = listing.get("room_type")
        if isinstance(room_type_obj, dict) and room_type_obj.get("name") and room_type_obj["name"] not in tags:
            tags.insert(0, room_type_obj["name"])

        inferred: list[str] = []
        concept_scores = listing.get("concept_scores")
        if isinstance(concept_scores, dict):
            for key, label in _CONCEPT_TAGS.items():
                val = concept_scores.get(key)
                if isinstance(val, (int, float)) and val >= _CONCEPT_THRESHOLD and label not in inferred:
                    inferred.append(label)

        main_image = listing.get("main_image") or ""
        images = listing.get("images")
        if isinstance(images, list) and images:
            photo_count = len(images)
        else:
            photo_count = 1 if main_image else 0

        room_lat, room_lng = listing.get("lat"), listing.get("lng")
        dist_val = listing.get("distance_km") or listing.get("distance")
        if (
            not isinstance(dist_val, (int, float))
            and None not in (room_lat, room_lng, target_lat, target_lng)
        ):
            try:
                dist_val = haversine_km(room_lat, room_lng, target_lat, target_lng)
            except (TypeError, ValueError):
                dist_val = None

        if isinstance(dist_val, (int, float)):
            if dist_val < 1.0:
                dist_str = f"{max(50, int(round(dist_val * 1000, -1)))}m"
            else:
                dist_str = f"{dist_val:.1f} km"
        elif isinstance(dist_val, str) and dist_val.strip():
            dist_str = dist_val.strip().lstrip("~").strip()
        else:
            dist_str = ""  # không bịa: để UI tự xử lý

        # Pin giả cho map mock: dùng crc32 (ổn định), KHÔNG dùng hash() (đổi mỗi lần chạy)
        room_hash = zlib.crc32(str(listing.get("id", rank)).encode("utf-8")) % 100
        lat_pct = 40.0 + ((rank * 13 + room_hash) % 25)
        lng_pct = 35.0 + ((rank * 17 + room_hash * 2) % 35)

        resolved_rt = _room_type_from_listing(room_type_obj)
        if resolved_rt is None and listing.get("room_type_id") is not None:
            resolved_rt = normalize_room_type(listing.get("room_type_id"))

        return cls(
            id=str(listing.get("id", f"room-{rank}")),
            rank=rank,
            rankText=rank_text(rank),
            matchScore=round(score, 3),
            title=listing.get("title") or "Phòng trọ",
            price=price_str,
            priceNum=price_vnd,
            area_m2=area_f,
            room_type=resolved_rt,
            address=listing.get("address_raw") or "",
            distance=dist_str,
            photoCount=photo_count,
            image=main_image or "/property-placeholder.svg",
            tags=tags,
            inferred_tags=inferred,
            lat=room_lat,
            lng=room_lng,
            latPercent=round(lat_pct, 1),
            lngPercent=round(lng_pct, 1),
            source_url=listing.get("url"),
            concept_scores=concept_scores if isinstance(concept_scores, dict) else {},
            explain_match=explain,
        )


class TradeOffAnalysis(BaseModel):
    """Phân tích so sánh đánh đổi đối kháng (Trade-off Matrix) giữa các phòng được gợi ý.

    Vai trò trong hệ thống Homigo AI Agent:
    - Do `decision_node` khởi tạo dựa trên dữ liệu so sánh giữa Top 1 với Top 2 hoặc Top 3.
    - Giúp người thuê nhìn thấy rõ ràng: chọn phòng này thì được gì (advantage) và phải đánh đổi gì (disadvantage),
      đảm bảo tính minh bạch và khách quan trong việc hỗ trợ ra quyết định.
    """

    compared_with: str = Field(..., description="Tên hoặc thứ hạng phòng đem ra so sánh (Top 2 / Top 3)")
    advantage: str = Field(..., description="Ưu điểm vượt trội hơn (ví dụ: Rẻ hơn 400k, gần trường hơn 800m)")
    disadvantage: str = Field(..., description="Điểm hạn chế hơn (ví dụ: Diện tích hẹp hơn 4m2, chưa có máy lạnh)")


class DecisionInsight(BaseModel):
    """Bảng dữ liệu cố vấn hỗ trợ ra quyết định toàn diện (Decision Support Package).

    Vai trò trong hệ thống Homigo AI Agent:
    - Được sinh ra từ `decision_node` bằng mô hình LLM chuyên trách tư vấn hoặc template phân tích an toàn.
    - Chứa lý do thuyết phục tại sao chọn Top 1 (`top_1_reason`), các tiêu chí quan trọng nhất (`key_factors`),
      bảng so sánh đánh đổi (`trade_offs`), và danh sách kiểm tra khi đi xem phòng thực tế (`verification_checklist`).
    - Frontend hiển thị khối này nổi bật ở đầu khung chat hoặc khu vực phân tích thông minh.
    """

    selected_top_1_id: str = Field(..., description="ID của căn phòng được xếp hạng Top 1")
    top_1_reason: str = Field(..., description="Giải thích lý do cốt lõi chọn Top 1 dựa trên rerank explain_match")
    key_factors: list[str] = Field(default_factory=list, description="Các tiêu chí quyết định lớn nhất")
    trade_offs: list[TradeOffAnalysis] = Field(default_factory=list, description="So sánh đánh đổi với các lựa chọn khác")
    verification_checklist: list[str] = Field(
        default_factory=list,
        description="Các điểm yếu hoặc thông tin cần kiểm tra thực tế (tiền điện nước, giờ giấc, ngập nước,...)",
    )


_LOCATION_KEYS = ("lat", "lng", "city_id", "district_id", "ward_id")


class UserPreferenceState(BaseModel):
    """Trạng thái nhu cầu người dùng tích lũy qua các lượt chat (Session Multi-turn Memory).

    Vai trò trong hệ thống Homigo AI Agent:
    - Bộ nhớ phiên (State Tracking): Được cập nhật ở `understand_node` từ kết quả bóc tách NLU qua từng lượt chat.
    - Tự động chuẩn hoá: `validate_assignment=True` giúp các tiện ích (amenities), loại phòng (room_type),
      và địa điểm (location_text) luôn được chuẩn hoá về enum canonical khi gán.
    - Cung cấp tiêu chí cho `retrieval_node` để xây dựng bộ lọc và vector trọng số MCDM truy vấn backend.
    """

    model_config = ConfigDict(validate_assignment=True, extra="ignore")

    location_text: Optional[str] = Field(None, description="Địa điểm hoặc khu vực (ví dụ: 'Linh Xuân, Thủ Đức')")
    location_kind: Optional[Literal["admin", "place"]] = Field(
        None, description="admin = đơn vị hành chính (tỉnh/quận/phường); place = địa điểm cụ thể (trường, KTX, đường...); None = chưa rõ"
    )
    lat: Optional[float] = Field(None, description="Vĩ độ mục tiêu")
    lng: Optional[float] = Field(None, description="Kinh độ mục tiêu")
    city_id: Optional[int] = Field(None, description="ID Tỉnh/Thành phố")
    district_id: Optional[int] = Field(None, description="ID Quận/Huyện")
    ward_id: Optional[int] = Field(None, description="ID Phường/Xã")
    max_distance_km: Optional[float] = Field(default=None, description="Bán kính tìm kiếm tối đa (km) do người dùng yêu cầu")
    min_price: Optional[float] = Field(None, description="Ngân sách tối thiểu (VNĐ)")
    max_price: Optional[float] = Field(None, description="Ngân sách tối đa (VNĐ)")
    min_area: Optional[float] = Field(None, description="Diện tích tối thiểu (m2)")
    max_area: Optional[float] = Field(None, description="Diện tích tối đa (m2)")
    room_type: Optional[RoomType] = Field(None, description="Loại phòng muốn tìm")
    allowed_room_types: list[RoomType] = Field(
        default_factory=list,
        description="Tập các loại phòng được phép (khi người dùng chấp nhận nhiều loại, vd: ['ROOM', 'STUDIO'])",
    )
    excluded_room_types: list[RoomType] = Field(
        default_factory=list, description="Loại phòng người dùng đã loại trừ ('không lấy ktx')"
    )
    amenities: list[Amenity] = Field(default_factory=list, description="Tiện ích BẮT BUỘC phải có (mã canonical)")
    preferred_amenities: list[Amenity] = Field(default_factory=list, description="Tiện ích ƯU TIÊN mềm (có càng tốt)")
    special_requirements: list[str] = Field(default_factory=list, description="Nhu cầu mềm (yên tĩnh, rộng rãi...)")

    # -- chuẩn hoá khi gán ---------------------------------------------------
    @field_validator("location_text", mode="before")
    @classmethod
    def _clean_location(cls, v: Any) -> Optional[str]:
        if not v or not isinstance(v, str):
            return None
        v = re.sub(r"\s*\((?:ví dụ|vd|vd:)[^)]*\)", "", v, flags=re.IGNORECASE)
        v = re.sub(r"^(?:khu vực\s+)?(?:lân cận|quanh)\s+", "", v.strip(), flags=re.IGNORECASE)
        v = v.strip(" ,.-")
        return v or None

    @field_validator("room_type", mode="before")
    @classmethod
    def _clean_room_type(cls, v: Any) -> Optional[RoomType]:
        return normalize_room_type(v)

    @field_validator("excluded_room_types", "allowed_room_types", mode="before")
    @classmethod
    def _clean_excluded(cls, v: Any) -> list[RoomType]:
        return normalize_room_types(v)

    @field_validator("amenities", "preferred_amenities", mode="before")
    @classmethod
    def _clean_amenities(cls, v: Any) -> list[Amenity]:
        return normalize_amenities(v)

    # -- thuộc tính suy ra ---------------------------------------------------
    @computed_field  # type: ignore[prop-decorator]
    @property
    def room_type_id(self) -> Optional[int]:
        return self.room_type.type_id if self.room_type else None

    @property
    def has_point(self) -> bool:
        """Có toạ độ điểm mốc (đo được khoảng cách)."""
        return self.lat is not None and self.lng is not None

    @property
    def has_admin(self) -> bool:
        """Có ID hành chính (tỉnh/quận/phường)."""
        return any(x is not None for x in (self.city_id, self.district_id, self.ward_id))

    # -- thao tác có bất biến ------------------------------------------------
    def set_location(self, text: Optional[str], kind: Optional[str] = None, **resolved: Any) -> None:
        """Đổi vị trí => xoá MỌI thứ cũ liên quan vị trí, chỉ giữ giá trị truyền vào.

        Ví dụ: pref.set_location("Quận 7", city_id=79, district_id=778)
        """
        unknown = set(resolved) - set(_LOCATION_KEYS)
        if unknown:
            raise TypeError(f"set_location nhận khoá lạ: {sorted(unknown)}")
        self.location_text = text
        self.location_kind = kind if text else None
        for k in _LOCATION_KEYS:
            setattr(self, k, resolved.get(k))

    def clear_location(self) -> None:
        self.set_location(None)

    def to_context_string(self) -> str:
        parts = []
        if self.location_text:
            coords = f" (Toạ độ: {self.lat:.4f}, {self.lng:.4f})" if self.has_point else ""
            parts.append(f"- Vị trí mục tiêu: {self.location_text}{coords}")
        if self.max_distance_km:
            parts.append(f"- Bán kính tối đa: {self.max_distance_km:g} km")
        if self.room_type:
            parts.append(f"- Loại phòng: {self.room_type.label_vi}")
        if self.allowed_room_types and (not self.room_type or self.allowed_room_types != [self.room_type]):
            parts.append(f"- Loại phòng cho phép: {', '.join(r.label_vi for r in self.allowed_room_types)}")
        if self.excluded_room_types:
            parts.append(f"- Không lấy loại: {', '.join(r.label_vi for r in self.excluded_room_types)}")
        if self.max_price:
            price_str = f"{self.max_price / 1_000_000:.1f} tr/tháng".replace(".0", "")
            parts.append(f"- Ngân sách tối đa: {price_str} ({self.max_price:,.0f} VNĐ)")
        if self.min_price:
            price_str = f"{self.min_price / 1_000_000:.1f} tr/tháng".replace(".0", "")
            parts.append(f"- Ngân sách tối thiểu: {price_str} ({self.min_price:,.0f} VNĐ)")
        if self.min_area or self.max_area:
            lo = f"{self.min_area:g}" if self.min_area else "?"
            hi = f"{self.max_area:g}" if self.max_area else "?"
            parts.append(f"- Diện tích: {lo}–{hi} m²")
        if self.amenities:
            parts.append(f"- Tiện ích BẮT BUỘC: {', '.join(f'{a.label_vi} ({a.value})' for a in self.amenities)}")
        if self.preferred_amenities:
            parts.append(f"- Tiện ích ƯU TIÊN (có càng tốt): {', '.join(f'{a.label_vi} ({a.value})' for a in self.preferred_amenities)}")
        if self.special_requirements:
            parts.append(f"- Yêu cầu đặc thù: {', '.join(self.special_requirements)}")
        return "\n".join(parts) if parts else "Chưa có tiêu chí nào được thiết lập."


class MarketContext(BaseModel):
    """Thông tin thị trường & khoảng chênh lệch ngân sách dùng cho tư vấn khi chưa có phòng khớp (Market Intelligence).

    Vai trò trong hệ thống Homigo AI Agent:
    - Được tính toán tại `verify_context_grounding` (khi kết quả tìm kiếm rỗng hoặc vi phạm ràng buộc cứng).
    - Cung cấp số liệu giá sàn thực tế (`market_min_price`), giá trung bình (`market_avg_price`), và khoảng chênh lệch
      giữa ngân sách người dùng với mặt bằng chung (`is_market_gap`).
    - Được `decision_node` dùng để sinh lời khuyên cố vấn khách quan (`ZeroResultAdvice`), hướng dẫn người thuê
      nới ngân sách hợp lý hoặc đổi sang khu vực lân cận phù hợp hơn.
    """

    area_name: Optional[str] = Field(None, description="Tên khu vực đang tìm kiếm")
    user_budget: Optional[float] = Field(None, description="Ngân sách người dùng đã đặt")
    user_budget_str: Optional[str] = Field(None, description="Chuỗi hiển thị ngân sách người dùng")
    market_min_price: Optional[float] = Field(None, description="Mức giá sàn thực tế tại khu vực")
    market_min_price_str: Optional[str] = Field(None, description="Chuỗi hiển thị giá sàn thực tế")
    market_avg_price: Optional[float] = Field(None, description="Mức giá trung bình thực tế tại khu vực")
    market_avg_price_str: Optional[str] = Field(None, description="Chuỗi hiển thị giá trung bình")
    proposed_budget: Optional[float] = Field(None, description="Mức ngân sách đề xuất điều chỉnh")
    proposed_budget_str: Optional[str] = Field(None, description="Chuỗi hiển thị ngân sách đề xuất")
    is_market_gap: bool = Field(False, description="True nếu ngân sách người dùng thấp xa so với giá sàn thực tế")
    message: Optional[str] = Field(None, description="Thông điệp phân tích thị trường giải thích lý do cần điều chỉnh")


class GroundingReport(BaseModel):
    """Báo cáo chi tiết kiểm định RAG Grounding & Chống ảo giác (Self-RAG Verification Report).

    Phản ánh đầy đủ các chỉ số của cơ chế Self-RAG Grounding & Self-Correction Loop trong bài toán Smart Housing:
    - Context Grounding: Kiểm định tính xác thực của tập kết quả phòng tìm kiếm (Hard Constraints, Market Gap).
    - Answer Grounding: Đối soát các thực thể (giá, mã phòng, thông số) trong câu trả lời tự nhiên với dữ liệu DB.
    - Self-Correction Retries: Số lượt tự sửa sai và ghi chú lỗi (retry_notes, issues).
    """

    model_config = ConfigDict(extra="allow")

    # --- Kiểm định tầng Câu trả lời (Answer Grounding) ---
    is_grounded: Optional[bool] = Field(
        None,
        description="True nếu câu trả lời hoàn toàn xác thực (không bị ảo giác về giá, mã phòng, thông số) hoặc đã fallback an toàn",
    )
    groundedness_score: Optional[float] = Field(
        None,
        description="Điểm tỷ lệ xác thực từ 0.0 đến 1.0 (verified / checked). 1.0 nghĩa là 100% số liệu nêu ra đều khớp dữ liệu thật",
    )
    checked: Optional[int] = Field(
        None,
        description="Tổng số phát biểu / thực thể số liệu (số tiền, mã phòng, diện tích) được trích xuất từ câu trả lời để kiểm tra",
    )
    verified: Optional[int] = Field(
        None,
        description="Số lượng thực thể số liệu đã được xác minh thành công khớp với bằng chứng thực tế",
    )

    # --- Kiểm định tầng Context (Context Grounding & Đề xuất ngân sách) ---
    context_grounded: Optional[bool] = Field(
        None,
        description="True nếu tập ngữ cảnh phòng tìm kiếm được thỏa mãn các ràng buộc cứng của người dùng",
    )
    proposed_budget: Optional[float] = Field(
        None,
        description="Mức ngân sách mới được hệ thống tính toán đề xuất dựa trên giá sàn thực tế của thị trường (VNĐ)",
    )
    proposed_budget_str: Optional[str] = Field(
        None,
        description="Chuỗi định dạng hiển thị trực quan của ngân sách đề xuất (ví dụ: '3.5 triệu/tháng')",
    )

    # --- Cơ chế tự sửa sai (Self-Correction Retry Loop) & Fallback ---
    context_retries: Optional[int] = Field(
        None,
        description="Số lần đã thử lại ở tầng Retrieval (giữ cho tương thích ngược schema)",
    )
    answer_retries: Optional[int] = Field(
        None,
        description="Số lần đã bắt LLM viết lại câu trả lời (Self-Correction) do phát hiện ảo giác dữ liệu",
    )
    retry_notes: list[str] = Field(
        default_factory=list,
        description="Nhật ký các ghi chú phản hồi lỗi chuyển lại cho Decision Node trong các lượt retry",
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Danh sách các vi phạm ảo giác cụ thể được phát hiện (ví dụ: mã phòng lạ, giá sai lệch so với DB)",
    )
    fallback_template_used: Optional[bool] = Field(
        None,
        description="True nếu LLM đã vượt quá số lần retry cho phép và hệ thống buộc phải dùng văn bản mẫu (code template) để đảm bảo an toàn tuyệt đối",
    )

    # --- Cấu hình đo lường & Thí nghiệm (Ablation Study) ---
    enforced: Optional[bool] = Field(
        None,
        description="Cờ thực thi: True = bắt buộc retry/fallback khi có lỗi; False = chế độ ablation chỉ đo đạc tỷ lệ lỗi mà không ngắt luồng",
    )


class AgentResponse(BaseModel):
    """Cấu trúc phản hồi chuẩn hoá hoàn chỉnh của AI Agent gửi về cho Client/UI qua REST API / SSE.

    Vai trò trong hệ thống Homigo AI Agent:
    - Đầu ra cuối cùng tại `formatter_node` sau khi toàn bộ luồng LangGraph hoàn tất kiểm định an toàn và grounding.
    - Đóng gói trọn vẹn: câu trả lời văn bản (`text_reply`), danh sách phòng (`rooms`), thông tin cố vấn (`insights`),
      trạng thái tiêu chí hiện tại (`current_preferences`), và báo cáo kiểm định chống ảo giác (`grounding_report`).
    """

    session_id: Optional[str] = Field(None, description="Mã phiên làm việc để duy trì hội thoại đa lượt")
    text_reply: str = Field(..., description="Văn bản tư vấn bằng ngôn ngữ tự nhiên gửi người dùng")
    rooms: list[RoomItem] = Field(default_factory=list, description="Danh sách các phòng phù hợp nhất")
    insights: Optional[DecisionInsight] = Field(None, description="Bảng phân tích hỗ trợ ra quyết định")
    current_preferences: Optional[UserPreferenceState] = Field(None, description="Trạng thái tiêu chí đã ghi nhận hiện tại")
    need_clarification: bool = Field(False, description="True nếu yêu cầu của người dùng quá mơ hồ cần hỏi lại")
    follow_up_questions: list[str] = Field(default_factory=list, description="Gợi ý 1-2 câu hỏi làm rõ tiếp theo")
    grounding_report: Optional[GroundingReport] = Field(
        None, description="Báo cáo kiểm định RAG Grounding (Context & Answer Groundedness + số lần retry)"
    )
    trace_events: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Các bước suy nghĩ và thực thi tool (model_request, model_response, tool_started, tool_finished)",
    )
    searched: bool = Field(False, description="True nếu lượt này đã thực hiện tìm kiếm phòng")
