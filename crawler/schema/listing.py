import re
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator
STATE_SCORE = {"yes": 1.0, "no": 0.0, "unknown": 0.4}

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
    """Tiện ích -> dùng cho amenity_fit."""

    private_wc: Signal = Field(
        default_factory=_unknown,
        description="yes: WC riêng/khép kín; WC chung -> no."
    )
    aircon: Signal = Field(
        default_factory=_unknown,
        description="Máy lạnh/điều hòa. 'chưa có máy lạnh' -> no."
    )
    furniture: Signal = Field(
        default_factory=_unknown,
        description="Có nội thất (giường, tủ, bàn...)."
    )
    window_balcony: Signal = Field(
        default_factory=_unknown,
        description="Có cửa sổ/ban công/thoáng; 'không cửa sổ' -> no."
    )
    kitchen: Signal = Field(
        default_factory=_unknown,
        description="Có bếp/chỗ nấu ăn."
    )
    mezzanine: Signal = Field(
        default_factory=_unknown,
        description="Có gác lửng/gác xép."
    )
    washing_machine: Signal = Field(
        default_factory=_unknown,
        description="Có máy giặt (riêng hoặc chung)."
    )
    water_heater: Signal = Field(
        default_factory=_unknown,
        description="Có máy nước nóng."
    )
    wifi: Signal = Field(
        default_factory=_unknown,
        description="Có wifi/internet."
    )
    parking: Signal = Field(
        default_factory=_unknown,
        description="Có chỗ để xe."
    )


class Rules(BaseModel):
    """Quy định -> cũng đưa vào amenity_fit."""

    free_hours: Signal = Field(
        default_factory=_unknown,
        description="Giờ giấc tự do, không giới hạn ra vào."
    )
    no_shared_landlord: Signal = Field(
        default_factory=_unknown,
        description="Không chung chủ."
    )


class Safety(BaseModel):
    """An toàn -> dùng cho safety_fit."""

    camera: Signal = Field(
        default_factory=_unknown,
        description="Có camera an ninh."
    )
    guard: Signal = Field(
        default_factory=_unknown,
        description="Có bảo vệ."
    )
    fingerprint_lock: Signal = Field(
        default_factory=_unknown,
        description="Khóa vân tay/khóa thông minh."
    )
    safe_area: Signal = Field(
        default_factory=_unknown,
        description="Nói rõ khu vực an ninh tốt."
    )

    def score(self) -> float:
        weights = {
            "camera": 0.25,
            "guard": 0.20,
            "fingerprint_lock": 0.15,
            "safe_area": 0.40,
        }

        return sum(
            weights[name] * getattr(self, name).score()
            for name in weights
        )

class Numeric(BaseModel):
    """Số liệu: chỉ điền khi tin ghi rõ, không thì null."""

    area_m2: Optional[float] = Field(
        None,
        description="Diện tích phòng (m²). Chỉ điền khi tin ghi rõ."
    )

    electricity_vnd_per_kwh: Optional[int] = Field(
        None,
        description="Giá điện (đồng/kWh). Chỉ điền khi tin ghi rõ."
    )

    water_vnd: Optional[int] = Field(
        None,
        description="Giá nước (đồng/người hoặc /m³). Chỉ điền khi tin ghi rõ."
    )

class ListingExtraction(BaseModel):
    amenities: Amenities = Field(default_factory=Amenities)
    rules: Rules = Field(default_factory=Rules)
    safety: Safety = Field(default_factory=Safety)
    numeric: Numeric = Field(default_factory=Numeric)

    # ---- Kiểm tra LLM có bịa không ----
    def verify_evidence(self, source_text: str) -> "ListingExtraction":
        """Signal nào có evidence KHÔNG nằm trong text gốc -> hạ về unknown. Trả bản mới."""
        src = _norm(source_text)
        data = self.model_copy(deep=True)
        for group in (data.amenities, data.rules, data.safety):
            for name in type(group).model_fields:
                sig: Signal = getattr(group, name)
                if sig.value != "unknown" and (not sig.evidence or _norm(sig.evidence) not in src):
                    setattr(group, name, Signal(value="unknown"))
        return data

    # ---- Chuyển sang đầu vào của match_score ----
    def to_concept_scores(self) -> dict[str, float]:
        """amenities + rules -> dict {concept: điểm [0,1]} cho amenity_fit."""
        scores = {}
        for group in (self.amenities, self.rules):
            for name in type(group).model_fields:
                scores[name] = getattr(group, name).score()
        return scores

    def safety_score(self) -> float:
        """Trung bình điểm các tín hiệu an toàn -> safety_fit. Có thể đổi sang trung bình có trọng số."""
        return round(self.safety.score(),2)

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