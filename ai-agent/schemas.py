"""Pydantic schemas cho AI Agent: Chuẩn hoá dữ liệu đầu vào / đầu ra
khớp hoàn toàn với frontend Tim-Kiem-AI và backend Smart Housing.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class RoomItem(BaseModel):
    """Thông tin phòng trọ được trả về cho Frontend hiển thị trên Danh sách và Bản đồ."""

    id: str = Field(..., description="ID định danh tin đăng")
    rank: int = Field(1, description="Thứ tự xếp hạng (1, 2, 3,...)")
    rankText: str = Field("Phù hợp nhất", description="Nhãn xếp hạng (Top 1, Top 2,...)")
    matchScore: float = Field(0.0, description="Điểm phù hợp tổng thể từ hệ thống rerank (0.0 - 1.0)")
    title: str = Field(..., description="Tiêu đề tin đăng")
    price: str = Field(..., description="Giá hiển thị (ví dụ: '2.8 triệu/tháng')")
    priceNum: float = Field(0.0, description="Giá số nguyên/thực (VNĐ)")
    address: str = Field("", description="Địa chỉ phòng")
    distance: str = Field("Gần điểm tìm kiếm", description="Khoảng cách ước tính")
    photoCount: int = Field(1, description="Số lượng ảnh")
    image: str = Field("", description="URL ảnh đại diện")
    tags: list[str] = Field(default_factory=list, description="Thẻ nổi bật (ví dụ: ['Có gác lửng', 'Cho nuôi pet'])")
    lat: Optional[float] = Field(None, description="Vĩ độ thực tế")
    lng: Optional[float] = Field(None, description="Kinh độ thực tế")
    latPercent: float = Field(50.0, description="Toạ độ % tương đối để render pin lên map mock nếu cần")
    lngPercent: float = Field(50.0, description="Toạ độ % tương đối để render pin lên map mock nếu cần")
    source_url: Optional[str] = Field(None, description="Link gốc bài đăng")
    explain_match: Optional[dict[str, Any]] = Field(None, description="Chi tiết giải thích từ rerank backend")

    @classmethod
    def from_backend_result(cls, item: dict, rank: int = 1) -> "RoomItem":
        """Chuyển đổi từ VectorSearchResult của Backend sang RoomItem của Agent."""
        listing = item.get("listing", {}) or {}
        explain = item.get("explain_match", {}) or {}
        score = item.get("match_score", 0.0)

        price_vnd = listing.get("price_vnd") or 0.0
        if price_vnd >= 1_000_000:
            price_str = f"{price_vnd / 1_000_000:.1f} triệu/tháng".replace(".0", "")
        elif price_vnd > 0:
            price_str = f"{price_vnd:,.0f} đ/tháng"
        else:
            price_str = listing.get("price_string") or "Thỏa thuận"

        # Trích xuất tags từ tiện ích hoặc explain
        tags = []
        if listing.get("area_m2"):
            tags.append(f"{listing['area_m2']} m²")
        if explain.get("top_factors"):
            factor_names = {
                "price": "Giá tốt",
                "location": "Vị trí gần",
                "amenity": "Đủ tiện nghi",
                "safety": "An ninh cao",
                "semantic": "Khớp mô tả",
            }
            for factor in explain["top_factors"][:2]:
                name = factor.get("name")
                if name in factor_names:
                    tags.append(factor_names[name])

        img = listing.get("main_image") or "/property-placeholder.svg"

        rank_texts = {1: "Top 1 - Tối ưu nhất", 2: "Top 2 - Đề xuất", 3: "Top 3 - Lựa chọn tốt"}
        rank_text = rank_texts.get(rank, f"Top {rank}")

        return cls(
            id=str(listing.get("id", f"room-{rank}")),
            rank=rank,
            rankText=rank_text,
            matchScore=round(score, 3),
            title=listing.get("title", "Phòng trọ"),
            price=price_str,
            priceNum=price_vnd,
            address=listing.get("address_raw") or "Hồ Chí Minh",
            distance="Vị trí thuận tiện",
            photoCount=4,
            image=img,
            tags=tags,
            lat=listing.get("lat"),
            lng=listing.get("lng"),
            latPercent=45.0 + (rank * 5.0) % 20,
            lngPercent=40.0 + (rank * 7.0) % 30,
            source_url=listing.get("url"),
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
    trade_offs: list[TradeOffAnalysis] = Field(default_factory=list, description="Phân tích so sánh đánh đổi với các lựa chọn khác")
    verification_checklist: list[str] = Field(
        default_factory=list,
        description="Các điểm yếu hoặc thông tin cần kiểm tra thực tế (tiền điện nước, giờ giấc, ngập nước,...)",
    )


class UserPreferenceState(BaseModel):
    """Trạng thái nhu cầu người dùng được tích lũy xuyên suốt nhiều lượt chat (Memory & State Management)."""

    location_text: Optional[str] = Field(None, description="Địa điểm hoặc khu vực (ví dụ: 'Linh Xuân, Thủ Đức')")
    lat: Optional[float] = Field(None, description="Vĩ độ mục tiêu")
    lng: Optional[float] = Field(None, description="Kinh độ mục tiêu")
    min_price: Optional[float] = Field(None, description="Ngân sách tối thiểu (VNĐ)")
    max_price: Optional[float] = Field(None, description="Ngân sách tối đa (VNĐ)")
    min_area: Optional[float] = Field(None, description="Diện tích tối thiểu (m2)")
    max_area: Optional[float] = Field(None, description="Diện tích tối đa (m2)")
    amenities: list[str] = Field(default_factory=list, description="Danh sách tiện ích yêu cầu")
    special_requirements: list[str] = Field(default_factory=list, description="Nhu cầu mềm (yên tĩnh, nuôi thú cưng, ban công...)")

    def to_context_string(self) -> str:
        parts = []
        if self.location_text:
            coords = f" (Toạ độ: {self.lat:.4f}, {self.lng:.4f})" if self.lat and self.lng else ""
            parts.append(f"- Vị trí mục tiêu: {self.location_text}{coords}")
        if self.max_price:
            price_str = f"{self.max_price / 1_000_000:.1f} tr/tháng".replace(".0", "")
            parts.append(f"- Ngân sách tối đa: {price_str} ({self.max_price:,.0f} VNĐ)")
        if self.min_price:
            price_str = f"{self.min_price / 1_000_000:.1f} tr/tháng".replace(".0", "")
            parts.append(f"- Ngân sách tối thiểu: {price_str} ({self.min_price:,.0f} VNĐ)")
        if self.amenities:
            parts.append(f"- Tiện ích mong muốn: {', '.join(self.amenities)}")
        if self.special_requirements:
            parts.append(f"- Yêu cầu đặc thù: {', '.join(self.special_requirements)}")
        return "\n".join(parts) if parts else "Chưa có tiêu chí nào được thiết lập."


class AgentResponse(BaseModel):
    """Toàn bộ phản hồi chuẩn hoá của AI Agent gửi về cho Client/UI."""

    text_reply: str = Field(..., description="Văn bản tư vấn bằng ngôn ngữ tự nhiên gửi người dùng")
    rooms: list[RoomItem] = Field(default_factory=list, description="Danh sách các phòng phù hợp nhất")
    insights: Optional[DecisionInsight] = Field(None, description="Bảng phân tích hỗ trợ ra quyết định")
    current_preferences: Optional[UserPreferenceState] = Field(None, description="Trạng thái tiêu chí đã ghi nhận hiện tại")
    need_clarification: bool = Field(False, description="True nếu yêu cầu của người dùng quá mơ hồ cần hỏi lại")
    follow_up_questions: list[str] = Field(default_factory=list, description="Gợi ý 1-2 câu hỏi làm rõ tiếp theo")
    grounding_report: Optional[dict[str, Any]] = Field(
        None,
        description="Báo cáo kiểm định RAG Grounding (Context & Answer Groundedness + số lần Corrective Retry)",
    )

