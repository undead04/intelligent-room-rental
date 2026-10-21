"""Pydantic schemas cho AI Agent: chuẩn hoá dữ liệu vào/ra, khớp frontend Tim-Kiem-AI và backend Smart Housing.

Thay đổi so với bản cũ (xem MIGRATION.md):
  - Tiện ích / loại phòng là enum (domain.enums), UserPreferenceState tự chuẩn hoá khi gán (validate_assignment).
  - room_type_id là property chỉ đọc, suy ra từ room_type.
  - UserPreferenceState.set_location(): đổi vị trí => xoá toạ độ/ID cũ ở MỘT chỗ.
  - RoomItem: thêm area_m2, match_percent; không còn tự bịa địa chỉ/số ảnh; pin map ổn định giữa các lần chạy;
    tag suy đoán từ ML tách riêng (inferred_tags).
  - HitlOption.action: frontend gửi lại HitlAction thay vì dò emoji trong action_text.
  - GroundingReport có kiểu (extra="allow" nên dict cũ vẫn nhận được).
"""

from __future__ import annotations

import re
import zlib
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from domain.enums import (  # noqa: F401  (re-export cho code cũ: from domain.schemas import CANONICAL_AMENITIES ...)
    CANONICAL_AMENITIES,
    CANONICAL_ROOM_TYPES,
    ROOM_TYPE_ID_TO_NAME,
    ROOM_TYPE_NAME_TO_ID,
    Amenity,
    HitlAction,
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
    "balcony": "Có ban công",  # khoá cũ backend có thể còn trả
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
    """Thông tin phòng trọ được trả về cho Frontend hiển thị trên Danh sách và Bản đồ."""

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

    @classmethod
    def from_backend_result(
        cls,
        item: dict,
        rank: int = 1,
        target_lat: Optional[float] = None,
        target_lng: Optional[float] = None,
    ) -> "RoomItem":
        """Chuyển đổi từ VectorSearchResult của Backend sang RoomItem của Agent."""
        listing = item.get("listing") or {}
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

        return cls(
            id=str(listing.get("id", f"room-{rank}")),
            rank=rank,
            rankText=rank_text(rank),
            matchScore=round(score, 3),
            title=listing.get("title") or "Phòng trọ",
            price=price_str,
            priceNum=price_vnd,
            area_m2=area_f,
            room_type=_room_type_from_listing(room_type_obj),
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
    """Phân tích đánh đổi giữa các lựa chọn phòng."""

    compared_with: str = Field(..., description="Tên hoặc thứ hạng phòng đem ra so sánh (Top 2 / Top 3)")
    advantage: str = Field(..., description="Ưu điểm vượt trội hơn (ví dụ: Rẻ hơn 400k, gần trường hơn 800m)")
    disadvantage: str = Field(..., description="Điểm hạn chế hơn (ví dụ: Diện tích hẹp hơn 4m2, chưa có máy lạnh)")


class DecisionInsight(BaseModel):
    """Bảng tổng hợp hỗ trợ ra quyết định dành cho người thuê."""

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
    """Trạng thái nhu cầu người dùng tích lũy xuyên suốt nhiều lượt chat.

    validate_assignment=True: `pref.amenities = ["máy lạnh", "xyz"]` -> tự thành [Amenity.AIRCON].
    """

    model_config = ConfigDict(validate_assignment=True)

    location_text: Optional[str] = Field(None, description="Địa điểm hoặc khu vực (ví dụ: 'Linh Xuân, Thủ Đức')")
    location_kind: Optional[Literal["admin", "place"]] = Field(
        None, description="admin = đơn vị hành chính (tỉnh/quận/phường); place = địa điểm cụ thể (trường, KTX, đường...); None = chưa rõ"
    )
    lat: Optional[float] = Field(None, description="Vĩ độ mục tiêu")
    lng: Optional[float] = Field(None, description="Kinh độ mục tiêu")
    city_id: Optional[int] = Field(None, description="ID Tỉnh/Thành phố")
    district_id: Optional[int] = Field(None, description="ID Quận/Huyện")
    ward_id: Optional[int] = Field(None, description="ID Phường/Xã")
    min_price: Optional[float] = Field(None, description="Ngân sách tối thiểu (VNĐ)")
    max_price: Optional[float] = Field(None, description="Ngân sách tối đa (VNĐ)")
    min_area: Optional[float] = Field(None, description="Diện tích tối thiểu (m2)")
    max_area: Optional[float] = Field(None, description="Diện tích tối đa (m2)")
    room_type: Optional[RoomType] = Field(None, description="Loại phòng muốn tìm")
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

    @field_validator("excluded_room_types", mode="before")
    @classmethod
    def _clean_excluded(cls, v: Any) -> list[RoomType]:
        return normalize_room_types(v)

    @field_validator("amenities", "preferred_amenities", mode="before")
    @classmethod
    def _clean_amenities(cls, v: Any) -> list[Amenity]:
        return normalize_amenities(v)

    # -- thuộc tính suy ra ---------------------------------------------------
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

    @property
    def has_location(self) -> bool:
        """Có toạ độ điểm mốc hoặc ID hành chính."""
        return self.has_point or self.has_admin

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
        if self.room_type:
            parts.append(f"- Loại phòng: {self.room_type.label_vi}")
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


class HitlOption(BaseModel):
    """Lựa chọn tương tác trong Human-in-the-Loop kiểu Claude."""

    id: str = Field(..., description="Mã định danh lựa chọn")
    action: Optional[HitlAction] = Field(None, description="Hành động có cấu trúc; frontend gửi lại giá trị này khi click")
    type: str = Field(..., description="Loại lựa chọn")
    title: str = Field(..., description="Tiêu đề hiển thị ngắn gọn, rõ ràng")
    description: str = Field(..., description="Mô tả cụ thể tác động của lựa chọn")
    badge: Optional[str] = Field(None, description="Nhãn nổi bật (Đề xuất tối ưu, Giữ ngân sách, Tiết kiệm...)")
    badge_color: Optional[str] = Field("emerald", description="Màu nhãn (emerald, blue, amber, purple, orange, slate)")
    action_text: str = Field("", description="Câu lệnh hiển thị/gửi lại (chỉ để tương thích ngược, ưu tiên dùng `action`)")
    highlight: bool = Field(False, description="Đánh dấu lựa chọn được AI khuyến nghị nhất")


class HitlProposal(BaseModel):
    """Khối đề xuất Human-in-the-Loop hoàn chỉnh dành cho giao diện chuyên nghiệp kiểu Claude."""

    needed: bool = Field(True, description="True khi cần hỏi ý kiến người dùng")
    title: Optional[str] = Field(None, description="Tiêu đề khối HITL")
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
    options: list[HitlOption] = Field(default_factory=list, description="Danh sách các thẻ lựa chọn tương tác")


class GroundingReport(BaseModel):
    """Báo cáo kiểm định grounding. extra='allow' để các khoá cũ (hitl_streak, ...) vẫn được giữ."""

    model_config = ConfigDict(extra="allow")

    is_grounded: Optional[bool] = None
    groundedness_score: Optional[float] = None
    context_grounded: Optional[bool] = None
    needs_user_consent: Optional[bool] = None
    proposed_budget: Optional[float] = None
    proposed_budget_str: Optional[str] = None
    context_retries: Optional[int] = None
    answer_retries: Optional[int] = None
    retry_notes: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    fallback_template_used: Optional[bool] = None
    checked: Optional[int] = None
    verified: Optional[int] = None
    enforced: Optional[bool] = None            # False: cấu hình ablation chỉ ĐO lỗi, không retry/thay thế
    hitl_streak: Optional[int] = None
    hitl_max_streak: Optional[int] = None
    hitl_limit_reached: Optional[bool] = None


class AgentResponse(BaseModel):
    """Toàn bộ phản hồi chuẩn hoá của AI Agent gửi về cho Client/UI."""

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
    hitl_proposal: Optional[HitlProposal] = Field(
        None, description="Đề xuất Human-in-the-Loop cấu trúc chuyên nghiệp kiểu Claude"
    )
    trace_events: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Các bước suy nghĩ và thực thi tool (model_request, model_response, tool_started, tool_finished)",
    )
