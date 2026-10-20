from crawler.schema.enums import RoomType
import re
import unicodedata
from typing import Literal, Optional, List, Union, Dict
from pydantic import BaseModel, Field, model_validator

STATE_SCORE = {"yes": 1.0, "no": 0.0, "unknown": 0.0}

Tri = Literal["yes", "no", "unknown"]

PUNCT_REGEX = re.compile(r"[\t\r\n\u2022\u2023\u25e6\u2043\u2219\u2705\u274c\u2714\u2713•*+\-–—_\"'“”‘’`~|/\\:;,\(\)\[\]\{\}]+")

def _remove_accents(input_str: str) -> str:
    """Loại bỏ dấu tiếng Việt để đối soát linh hoạt khi người dùng gõ không dấu hoặc lệch kiểu gõ dấu."""
    s = unicodedata.normalize('NFD', input_str)
    s = re.sub(r'[\u0300-\u036f]', '', s)
    s = s.replace('đ', 'd').replace('Đ', 'D')
    return s

def _norm(s: str) -> str:
    """Chuẩn hóa để so khớp evidence: Unicode NFC + thường hóa + làm sạch ký tự phân cách/bullet."""
    if not s:
        return ""
    s = unicodedata.normalize("NFC", s).lower()
    s = PUNCT_REGEX.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()

def extract_listing_full_text(a: Dict[str, object]) -> str:
    """Hợp nhất tiêu đề và mô tả bài đăng để không bỏ sót ngữ cảnh tiện ích."""
    title = str(a.get("title") or "").strip()
    desc = str(a.get("description") or a.get("text") or "").strip()
    if title and desc:
        return desc if title in desc else f"{title}\n{desc}"
    return title or desc

def is_evidence_valid(evidence: str, source_text: str, field_keywords: Optional[List[str]] = None) -> bool:
    """Kiểm tra evidence trích xuất từ LLM có thực sự nằm trong văn bản gốc hay không.
    Hỗ trợ đối soát chống hallucination nhưng không đánh rơi tiện ích vì lệch dấu câu/dấu thanh.
    """
    if not evidence or not source_text:
        return False

    norm_ev = _norm(evidence)
    norm_src = _norm(source_text)
    if not norm_ev or not norm_src:
        return False

    # 1. Khớp chính xác chuỗi con sau chuẩn hóa
    if norm_ev in norm_src:
        return True

    # 2. Khớp không dấu (xử lý lệch vị trí dấu thanh hoà/hòa, hoặc tin viết không dấu)
    unacc_ev = _remove_accents(norm_ev)
    unacc_src = _remove_accents(norm_src)
    if unacc_ev in unacc_src:
        return True

    # 3. Khớp từ khóa cốt lõi (nếu LLM trích dư chữ 'có', 'phòng', 'trang bị')
    # Bắt buộc từ khóa phải xuất hiện trong CẢ evidence VÀ source_text
    if field_keywords:
        for kw in field_keywords:
            kw_norm = _norm(kw)
            kw_unacc = _remove_accents(kw_norm)
            if (kw_norm in norm_ev or kw_unacc in unacc_ev) and (kw_norm in norm_src or kw_unacc in unacc_src):
                return True

    return False


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
        max_length=5,
        description="Các trường đại học, bệnh viện, chợ, trạm metro lân cận được nhắc đến hoặc suy luận được từ vị trí (tối đa 5 mục)."
    )
    extra_amenities: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="Các tiện nghi/đặc điểm khác không nằm trong amenities chuẩn (ví dụ: view Landmark 81, cửa sổ trời, hồ bơi). TUYỆT ĐỐI không điền các tiện ích đã có trong enum chuẩn vào đây (tối đa 5 mục)."
    )
    # ---- Kiểm tra LLM có bịa không ----
    def verify_evidence(self, source_text: str) -> "ListingExtraction":
        """Signal nào có evidence KHÔNG nằm trong text gốc -> hạ về unknown.
        Đồng thời đối soát extra_amenities để thu hồi các tiện ích chuẩn mà LLM vô tình bỏ quên vào extra_amenities.
        """
        data = self.model_copy(deep=True)
        field_kw_map = dict(EXTRA_TO_AMENITY_MAP)

        for group in (data.amenities, data.rules, data.safety):
            for name in type(group).model_fields:
                sig: Signal = getattr(group, name)
                if sig.value != "unknown":
                    kws = field_kw_map.get(name, [])
                    if not sig.evidence or not is_evidence_valid(sig.evidence, source_text, kws):
                        setattr(group, name, Signal(value="unknown"))

        # Thu hồi các tiện ích chuẩn bị LLM nhầm lẫn đưa vào extra_amenities
        cleaned_extra: List[str] = []
        for extra_item in (data.extra_amenities or []):
            reconciled = False
            extra_norm = _norm(extra_item)
            extra_unacc = _remove_accents(extra_norm)
            for target_field, keywords in EXTRA_TO_AMENITY_MAP:
                if any(kw in extra_norm or _remove_accents(kw) in extra_unacc for kw in keywords):
                    # Kiểm tra xem tiện ích này có thực sự xuất hiện trong source_text không
                    if is_evidence_valid(extra_item, source_text, keywords):
                        for grp in (data.amenities, data.rules, data.safety):
                            if hasattr(grp, target_field):
                                current_sig: Signal = getattr(grp, target_field)
                                if current_sig.value == "unknown":
                                    setattr(grp, target_field, Signal(value="yes", evidence=extra_item))
                                reconciled = True
                                break
                    else:
                        # extra_item không nằm trong text gốc -> hallucination, loại bỏ
                        reconciled = True
                    break
            if not reconciled:
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
        """Xuất dict concept_scores cho cơ sở dữ liệu và thuật toán rerank (chỉ chứa các concept nguyên tử)."""
        scores = {}
        for group in (self.amenities, self.rules, self.safety):
            for name in type(group).model_fields:
                scores[name] = getattr(group, name).score()
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
    standard_amenities: List[str] = Field(default_factory=list, description="Tiện ích nội khu chuẩn hóa")
    extra_amenities: List[str] = Field(default_factory=list, description="Tiện ích bổ sung ngoài danh mục chuẩn")
    rules_and_lifestyle: List[str] = Field(default_factory=list, description="Quy định và môi trường sống")
    is_pet_allowed: Optional[bool] = Field(None, description="Cho phép nuôi thú cưng (True: có, False: không, None: chưa rõ)")
    bedrooms: Optional[int] = Field(None, description="Số phòng ngủ")
    bathrooms: Optional[int] = Field(None, description="Số phòng tắm / WC")
