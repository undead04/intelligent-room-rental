from crawler.schema.enum import RoomType
import re
from typing import Literal, Optional, List, Any, Union
from pydantic import BaseModel, Field, model_validator

STATE_SCORE = {"yes": 1.0, "no": 0.0, "unknown": 0.0}

Tri = Literal["yes", "no", "unknown"]

class Signal(BaseModel):
    """Một tiện ích/quy định: có / không / chưa rõ, kèm câu trích dẫn làm bằng chứng."""
    value: Tri = Field("unknown", description="yes/no chỉ khi tin nói rõ; không suy đoán.")
    evidence: Optional[str] = Field(
        None, description="Đoạn trích NGUYÊN VĂN từ tin làm căn cứ. null nếu value=unknown."
    )

    @model_validator(mode="after")
    def _unknown_has_no_evidence(self):
        if self.value == "unknown":
            self.evidence = None
        return self

    def score(self) -> float:
        return STATE_SCORE[self.value]

def _unknown() -> Signal:
    return Signal()

def _norm(s: str) -> str:
    """Chuẩn hóa để so khớp evidence: thường hóa + gộp khoảng trắng."""
    return re.sub(r"\s+", " ", s).strip().lower()


class Amenities(BaseModel):
    """Tiện ích phòng -> dùng cho amenity_fit và amenity_overall_score."""

    private_wc: Signal = Field(
        default_factory=_unknown,
        description="yes: WC riêng/khép kín; WC chung -> no."
    )
    aircon: Signal = Field(
        default_factory=_unknown,
        description="Máy lạnh/điều hòa. 'chưa có máy lạnh' -> no."
    )
    mezzanine: Signal = Field(
        default_factory=_unknown,
        description="Có gác lửng/gác xép."
    )
    kitchen: Signal = Field(
        default_factory=_unknown,
        description="Có bếp/khu vực nấu ăn."
    )
    fridge: Signal = Field(
        default_factory=_unknown,
        description="Có tủ lạnh."
    )
    washing_machine: Signal = Field(
        default_factory=_unknown,
        description="Có máy giặt (riêng hoặc chung)."
    )
    window_balcony: Signal = Field(
        default_factory=_unknown,
        description="Có cửa sổ/ban công thoáng mát; 'phòng kín/không cửa sổ' -> no."
    )
    furniture: Signal = Field(
        default_factory=_unknown,
        description="Có nội thất (giường, tủ, bàn ghế...)."
    )
    parking: Signal = Field(
        default_factory=_unknown,
        description="Có chỗ để xe / nhà xe / hầm xe."
    )
    elevator: Signal = Field(
        default_factory=_unknown,
        description="Có thang máy."
    )


class Rules(BaseModel):
    """Quy định & lối sống -> dùng cho amenity_fit / filter."""

    free_hours: Signal = Field(
        default_factory=_unknown,
        description="Giờ giấc tự do, không giới hạn ra vào."
    )
    no_shared_landlord: Signal = Field(
        default_factory=_unknown,
        description="Không chung chủ."
    )
    pet_allowed: Signal = Field(
        default_factory=_unknown,
        description="yes: Cho phép nuôi thú cưng (chó, mèo); cấm nuôi -> no."
    )


class Safety(BaseModel):
    """An toàn & An ninh -> dùng cho safety_fit."""

    camera: Signal = Field(
        default_factory=_unknown,
        description="Có camera an ninh."
    )
    guard: Signal = Field(
        default_factory=_unknown,
        description="Có bảo vệ trực cổng/24/7."
    )
    fingerprint_lock: Signal = Field(
        default_factory=_unknown,
        description="Khóa vân tay/cổng thẻ từ/khóa thông minh."
    )
    safe_area: Signal = Field(
        default_factory=_unknown,
        description="Nói rõ khu vực an ninh tốt, trật tự."
    )

    def score(self) -> float:
        # Trọng số an toàn: camera 0.30, guard 0.30, fingerprint_lock 0.25, safe_area 0.15
        weights = {
            "camera": 0.30,
            "guard": 0.30,
            "fingerprint_lock": 0.25,
            "safe_area": 0.15,
        }

        return sum(
            weights[name] * getattr(self, name).score()
            for name in weights
        )

class Numeric(BaseModel):
    """Số liệu: chỉ điền khi tin ghi rõ, không thì null."""

    bedrooms: Optional[int] = Field(
        None,
        description="Số phòng ngủ. Chỉ điền khi tin ghi rõ."
    )

    bathrooms: Optional[int] = Field(
        None,
        description="Số phòng tắm. Chỉ điền khi tin ghi rõ."
    )

    electricity_vnd_per_kwh: Optional[int] = Field(
        None,
        description="Giá điện (đồng/kWh). Chỉ điền khi tin ghi rõ."
    )

    water_vnd: Optional[int] = Field(
        None,
        description="Giá nước (đồng/người hoặc /m³). Chỉ điền khi tin ghi rõ."
    )

EXTRA_TO_AMENITY_MAP: list[tuple[str, list[str]]] = [
    ("private_wc", ["wc riêng", "vệ sinh riêng", "toilet riêng", "toilet trong phòng", "nvs riêng", "khép kín"]),
    ("aircon", ["máy lạnh", "may lanh", "điều hòa", "dieu hoa", "ml"]),
    ("mezzanine", ["gác", "gác lửng", "gác xép", "gac"]),
    ("kitchen", ["bếp", "kệ bếp", "chỗ nấu ăn", "nấu ăn"]),
    ("fridge", ["tủ lạnh", "tu lanh"]),
    ("washing_machine", ["máy giặt", "may giat"]),
    ("window_balcony", ["ban công", "cửa sổ", "ánh sáng tự nhiên", "thoáng mát"]),
    ("furniture", ["nội thất", "giường", "nệm", "tủ quần áo", "bàn ghế"]),
    ("parking", ["chỗ để xe", "giữ xe", "hầm xe", "sân để xe", "nhà xe"]),
    ("elevator", ["thang máy", "thang may"]),
    ("free_hours", ["giờ giấc tự do", "giờ tự do", "ra vào tự do"]),
    ("no_shared_landlord", ["không chung chủ", "k chung chủ", "ko chung chủ", "riêng tư"]),
    ("pet_allowed", ["thú cưng", "nuôi pet", "nuôi mèo", "nuôi chó", "cho nuôi"]),
    ("camera", ["camera", "cam an ninh"]),
    ("guard", ["bảo vệ", "bao ve"]),
    ("fingerprint_lock", ["vân tay", "thẻ từ", "khóa thông minh", "smart lock"]),
    ("safe_area", ["khu an ninh", "an ninh tốt", "an ninh đảm bảo", "khu vực an ninh"]),
]

class ListingExtraction(BaseModel):
    amenities: Amenities = Field(default_factory=Amenities)
    rules: Rules = Field(default_factory=Rules)
    safety: Safety = Field(default_factory=Safety)
    numeric: Numeric = Field(default_factory=Numeric)
    room_type: RoomType = Field(
        default=RoomType.ROOM,
        description="Phân loại loại hình phòng trọ/nhà ở"
    )
    landmarks_nearby: List[str] = Field(
        default_factory=list,
        description="Các trường đại học, bệnh viện, chợ, trạm metro lân cận được nhắc đến hoặc suy luận được từ vị trí."
    )
    rules_and_lifestyle: List[str] = Field(
        default_factory=list,
        description="Quy định và môi trường sống: giờ giấc tự do, không chung chủ, cho nấu ăn, yên tĩnh, an ninh..."
    )
    extra_amenities: List[str] = Field(
        default_factory=list,
        description="Các tiện nghi/đặc điểm khác không nằm trong enum chuẩn (ví dụ: view Landmark 81, cửa sổ trời, hồ bơi). TUYỆT ĐỐI không điền các tiện ích đã có trong enum chuẩn vào đây."
    )
    # ---- Kiểm tra LLM có bịa không ----
    def verify_evidence(self, source_text: str) -> "ListingExtraction":
        """Signal nào có evidence KHÔNG nằm trong text gốc -> hạ về unknown.
        Đồng thời đối soát extra_amenities để thu hồi các tiện ích chuẩn mà LLM vô tình bỏ quên vào extra_amenities.
        """
        src = _norm(source_text)
        data = self.model_copy(deep=True)
        for group in (data.amenities, data.rules, data.safety):
            for name in type(group).model_fields:
                sig: Signal = getattr(group, name)
                if sig.value != "unknown" and (not sig.evidence or _norm(sig.evidence) not in src):
                    setattr(group, name, Signal(value="unknown"))

        # Thu hồi các tiện ích chuẩn bị LLM nhầm lẫn đưa vào extra_amenities
        cleaned_extra: List[str] = []
        for extra_item in (data.extra_amenities or []):
            extra_norm = _norm(extra_item)
            matched = False
            for target_field, keywords in EXTRA_TO_AMENITY_MAP:
                if any(kw in extra_norm for kw in keywords):
                    for grp in (data.amenities, data.rules, data.safety):
                        if hasattr(grp, target_field):
                            current_sig: Signal = getattr(grp, target_field)
                            if current_sig.value == "unknown" and extra_norm in src:
                                setattr(grp, target_field, Signal(value="yes", evidence=extra_item))
                            matched = True
                            break
                    if matched:
                        break
            if not matched:
                cleaned_extra.append(extra_item)

        data.extra_amenities = cleaned_extra
        return data

    def amenity_overall_score(self) -> float:
        """Tính điểm tổng thể tiện nghi phòng theo thang tích lũy 100 điểm (0.0 - 1.0).
        Chỉ những tiện ích xác nhận 'yes' mới được cộng điểm, giải quyết triệt để Score Flattening.
        """
        weights = {
            "private_wc": 20,
            "aircon": 20,
            "mezzanine": 15,
            "kitchen": 15,
            "fridge": 10,
            "washing_machine": 10,
            "window_balcony": 10,
            "furniture": 5,
            "parking": 5,
            "elevator": 5,
        }
        earned = sum(
            weights[name]
            for name, w in weights.items()
            if getattr(self.amenities, name).value == "yes"
        )
        return round(min(1.0, earned / 100.0), 2)

    def safety_score(self) -> float:
        """Điểm an ninh tổng thể [0, 1]."""
        return round(self.safety.score(), 2)

    # ---- Chuyển sang đầu vào của match_score ----
    def to_concept_scores(self) -> dict[str, float]:
        """Xuất dict concept_scores cho cơ sở dữ liệu và thuật toán rerank."""
        scores = {}
        for group in (self.amenities, self.rules, self.safety):
            for name in type(group).model_fields:
                scores[name] = getattr(group, name).score()
        scores["amenity_overall"] = self.amenity_overall_score()
        scores["safety_overall"] = self.safety_score()
        return scores

class SingleListingExtraction(BaseModel):
    id: str = Field(description="ID bài đăng, bắt buộc khớp chính xác với ID đầu vào")
    report: Optional[ListingExtraction] = Field(
        default=None,
        description="Báo cáo về trích xuất thông tin tiện ích"
    )
class ChunkExtractionWrapper(BaseModel):
    reports: list[SingleListingExtraction] = Field(
        default_factory=list,
        description="Danh sách bóc tách về tiện ích trong chunk"
    )


class ExtractedRoomData(BaseModel):
    """Mô hình dữ liệu phòng trọ tổng hợp dùng để sinh văn bản giàu ngữ cảnh cho mô hình Embedding."""
    street: Optional[str] = Field(None, description="Tên đường hoặc địa chỉ cụ thể")
    ward: Optional[str] = Field(None, description="Phường / Xã")
    district: Optional[str] = Field(None, description="Quận / Huyện")
    city: Optional[str] = Field(None, description="Tỉnh / Thành phố")
    landmarks_nearby: List[str] = Field(default_factory=list, description="Tiện ích ngoại khu, địa danh gần đó")
    room_type: Union[RoomType, str] = Field(default=RoomType.ROOM, description="Loại hình phòng trọ")
    area: Optional[float] = Field(None, description="Diện tích (m2)")
    price: Optional[float] = Field(None, description="Giá thuê phòng (VNĐ/tháng)")
    standard_amenities: List[Any] = Field(default_factory=list, description="Tiện ích nội khu chuẩn hóa")
    extra_amenities: List[str] = Field(default_factory=list, description="Tiện ích bổ sung ngoài danh mục chuẩn")
    rules_and_lifestyle: List[str] = Field(default_factory=list, description="Quy định và môi trường sống")
    is_pet_allowed: Optional[bool] = Field(None, description="Cho phép nuôi thú cưng (True: có, False: không, None: chưa rõ)")