from crawler.schema.enums import CANONICAL_ROOM_TYPES, RoomType
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
    ("guard", ["bảo vệ", "bao ve", "lễ tân", "trực 24", "an ninh 24/24", "an ninh 24/7", "quản lý tòa nhà", "quản lý toà nhà"]),
    ("fingerprint_lock", ["vân tay", "thẻ từ", "khóa từ", "khoá từ", "khóa mã", "khoá mã", "mật mã", "passcode", "face id", "cửa từ", "khóa điện tử", "khoá điện tử", "khóa thông minh", "smart lock"]),
    ("safe_area", ["khu an ninh", "an ninh tốt", "an ninh đảm bảo", "khu vực an ninh", "dân trí cao", "hẻm cụt yên tĩnh", "khu dân cư yên tĩnh", "an toàn tuyệt đối", "khu vực yên tĩnh"]),
]

# Regex thu hồi bổ sung & điểm thưởng an toàn / tiện nghi v2 (chỉ bổ sung khi LLM trả unknown, không đè 'no')
P_PCCC = re.compile(r"\bpccc\b|phòng cháy|chữa cháy|báo cháy|lối thoát hiểm|thoát hiểm|bình chữa cháy", re.IGNORECASE)
P_SMART_LOCK = re.compile(
    r"vân tay|thẻ từ|khóa từ|khoá từ|khóa mã|khoá mã|mật mã|passcode|face\s*id|cửa từ|"
    r"khóa điện tử|khoá điện tử|khóa thông minh|khoá thông minh|smart\s*lock",
    re.IGNORECASE,
)
P_GUARD = re.compile(r"bảo vệ|bao ve|lễ tân|trực\s*24|an ninh\s*24/24|an ninh\s*24/7|quản lý tòa nhà|quản lý toà nhà", re.IGNORECASE)
P_GATE_LOCK = re.compile(r"cổng riêng|khóa riêng|khoá riêng|2 lớp cửa|hai lớp cửa|cổng rào|cửa sắt chắc|lối đi riêng|khóa cổng|khoá cổng", re.IGNORECASE)
P_SAFE_AREA = re.compile(
    r"an ninh tốt|khu an ninh|an ninh đảm bảo|khu vực an ninh|dân trí cao|hẻm cụt yên tĩnh|"
    r"khu dân cư yên tĩnh|an toàn tuyệt đối|khu vực yên tĩnh",
    re.IGNORECASE,
)
P_PREMIUM_EXTRA = re.compile(
    r"hồ bơi|bể bơi|phòng gym|\bgym\b|sân vườn|bbq|công viên nội khu|siêu thị dưới nhà|sảnh lễ tân|rooftop",
    re.IGNORECASE,
)
P_FULL_FURN_TEXT = re.compile(
    r"full\s*nội\s*thất|đầy\s*đủ\s*nội\s*thất|nội\s*thất\s*đầy\s*đủ|full\s*tiện\s*nghi|xách\s*vali",
    re.IGNORECASE,
)

ROOM_TYPE_ID_TO_CODE: dict[int, str] = {info[0]: code for code, info in CANONICAL_ROOM_TYPES.items()}

SAFETY_BASELINE_BY_ROOM_TYPE: dict[str, float] = {
    RoomType.SLEEPBOX.value: 0.26,
    RoomType.ROOM.value: 0.30,
    RoomType.STUDIO.value: 0.34,
    RoomType.WHOLE_HOUSE.value: 0.36,
    RoomType.APARTMENT.value: 0.40,
}

SAFETY_EVIDENCE_WEIGHTS: dict[str, float] = {
    "fingerprint_lock": 0.28,
    "camera": 0.25,
    "guard": 0.22,
    "safe_area": 0.18,
}

AMENITY_WEIGHTS_BY_ROOM_TYPE: dict[str, dict[str, float]] = {
    RoomType.ROOM.value: {
        "private_wc": 18.0, "aircon": 18.0, "kitchen": 12.0, "furniture": 12.0,
        "window_balcony": 10.0, "washing_machine": 8.0, "fridge": 8.0, "parking": 6.0, "mezzanine": 8.0,
    },
    RoomType.STUDIO.value: {
        "private_wc": 15.0, "aircon": 18.0, "furniture": 16.0, "kitchen": 13.0,
        "window_balcony": 10.0, "fridge": 10.0, "washing_machine": 10.0, "elevator": 4.0, "parking": 4.0,
    },
    RoomType.APARTMENT.value: {
        "private_wc": 12.0, "aircon": 18.0, "furniture": 20.0, "kitchen": 12.0,
        "window_balcony": 10.0, "washing_machine": 10.0, "fridge": 10.0, "elevator": 4.0, "parking": 4.0,
    },
    RoomType.SLEEPBOX.value: {
        "private_wc": 18.0, "aircon": 18.0, "kitchen": 12.0, "furniture": 14.0,
        "window_balcony": 10.0, "washing_machine": 10.0, "fridge": 10.0, "parking": 8.0,
    },
    RoomType.WHOLE_HOUSE.value: {
        "private_wc": 15.0, "kitchen": 15.0, "aircon": 18.0, "furniture": 18.0,
        "window_balcony": 10.0, "parking": 10.0, "washing_machine": 7.0, "fridge": 7.0,
    },
}


def _normalize_room_type_code(
    room_type: Optional[Union[RoomType, str, int]],
    fallback: Union[RoomType, str] = RoomType.ROOM,
) -> str:
    """Chuẩn hóa loại hình phòng từ Enum, string hoặc canonical room_type_id (1..5)."""
    candidate = room_type if room_type is not None else fallback
    if isinstance(candidate, RoomType):
        return candidate.value
    if isinstance(candidate, int) and not isinstance(candidate, bool):
        return ROOM_TYPE_ID_TO_CODE.get(candidate, RoomType.ROOM.value)
    raw = str(candidate or "").strip().upper()
    if raw.isdigit():
        return ROOM_TYPE_ID_TO_CODE.get(int(raw), RoomType.ROOM.value)
    if raw in SAFETY_BASELINE_BY_ROOM_TYPE:
        return raw
    return RoomType.ROOM.value

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

    def amenity_overall_score(
        self,
        *,
        room_type: Optional[Union[RoomType, str, int]] = None,
        furnishing_code: Optional[int] = None,
        bathrooms: Optional[int] = None,
        source_text: str = "",
    ) -> float:
        """Tính điểm tổng thể tiện nghi v2 chuẩn hóa theo loại phòng & tình trạng nội thất [0.0, 1.0].

        - Áp dụng bộ trọng số 100 điểm riêng cho từng loại phòng (ROOM/STUDIO/APARTMENT/SLEEPBOX/WHOLE_HOUSE).
        - Suy luận mặc định cấu trúc hiển nhiên (chỉ khi cờ đang 'unknown', tuyệt đối không ghi đè 'no').
        - Gộp raw_furnishing_code in (1, 2) hoặc mô tả 'full nội thất' hưởng sàn 80% cụm thiết bị (trừ SLEEPBOX).
        """
        rt_code = _normalize_room_type_code(room_type, self.room_type)
        av = {name: getattr(self.amenities, name).value for name in type(self.amenities).model_fields}
        extra_text = f"{source_text}\n{' '.join(self.extra_amenities or [])}".strip()

        has_private_bath = False
        if bathrooms is not None and not isinstance(bathrooms, bool):
            try:
                has_private_bath = int(float(bathrooms)) >= 1
            except (TypeError, ValueError):
                has_private_bath = False

        if av["private_wc"] == "unknown" and (
            rt_code in (RoomType.STUDIO.value, RoomType.APARTMENT.value, RoomType.WHOLE_HOUSE.value)
            or (has_private_bath and rt_code != RoomType.SLEEPBOX.value)
        ):
            av["private_wc"] = "yes"
        if av["kitchen"] == "unknown" and rt_code in (RoomType.APARTMENT.value, RoomType.WHOLE_HOUSE.value):
            av["kitchen"] = "yes"
        if rt_code == RoomType.APARTMENT.value:
            if av["elevator"] == "unknown":
                av["elevator"] = "yes"
            if av["parking"] == "unknown":
                av["parking"] = "yes"
        if av["furniture"] == "unknown" and furnishing_code in (1, 2):
            av["furniture"] = "yes"

        weights = AMENITY_WEIGHTS_BY_ROOM_TYPE.get(rt_code, AMENITY_WEIGHTS_BY_ROOM_TYPE[RoomType.ROOM.value])
        earned = sum(w for field_name, w in weights.items() if av.get(field_name) == "yes")

        has_full_furn_signal = furnishing_code in (1, 2) or (
            furnishing_code is None and bool(extra_text and P_FULL_FURN_TEXT.search(extra_text))
        )
        if rt_code != RoomType.SLEEPBOX.value and has_full_furn_signal:
            cluster_fields = [
                f for f in ("furniture", "aircon", "fridge", "washing_machine")
                if f in weights and av.get(f) != "no"
            ]
            if cluster_fields:
                cluster_max = sum(weights[f] for f in cluster_fields)
                cluster_got = sum(weights[f] for f in cluster_fields if av.get(f) == "yes")
                floor_target = 0.80 * cluster_max
                if cluster_got < floor_target:
                    earned += floor_target - cluster_got

        bonus = 0.0
        if rt_code == RoomType.ROOM.value and av.get("elevator") == "yes":
            bonus += 5.0
        if rt_code in (RoomType.STUDIO.value, RoomType.WHOLE_HOUSE.value) and av.get("mezzanine") == "yes":
            bonus += 4.0
        if rt_code == RoomType.WHOLE_HOUSE.value and av.get("elevator") == "yes":
            bonus += 4.0
        if self.rules.free_hours.value == "yes":
            bonus += 3.0
        if self.rules.no_shared_landlord.value == "yes":
            bonus += 3.0
        if self.rules.pet_allowed.value == "yes":
            bonus += 2.0
        if extra_text and P_PREMIUM_EXTRA.search(extra_text):
            bonus += 5.0

        earned += min(10.0, bonus)
        return round(max(0.0, min(1.0, earned / 100.0)), 2)

    def safety_score(
        self,
        *,
        room_type: Optional[Union[RoomType, str, int]] = None,
        source_text: str = "",
    ) -> float:
        """Điểm an ninh tổng thể v2 theo đường cong lợi ích cận biên giảm dần [0.0, 1.0].

        Kết hợp điểm nền nhẹ theo loại hình (0.26..0.40) và bằng chứng an ninh xác thực,
        thu hồi deterministic khi cờ đang 'unknown' (không đè 'no') cùng thưởng PCCC/cổng riêng.
        """
        rt_code = _normalize_room_type_code(room_type, self.room_type)
        sv = {k: getattr(self.safety, k).value for k in SAFETY_EVIDENCE_WEIGHTS}
        check_text = f"{source_text}\n{' '.join(self.extra_amenities or [])}".strip()

        if check_text:
            if sv["fingerprint_lock"] == "unknown" and P_SMART_LOCK.search(check_text):
                sv["fingerprint_lock"] = "yes"
            if sv["guard"] == "unknown" and P_GUARD.search(check_text):
                sv["guard"] = "yes"
            if sv["safe_area"] == "unknown" and P_SAFE_AREA.search(check_text):
                sv["safe_area"] = "yes"

        ev_raw = sum(w for k, w in SAFETY_EVIDENCE_WEIGHTS.items() if sv[k] == "yes")
        if check_text:
            if P_PCCC.search(check_text):
                ev_raw += 0.14
            if sv["fingerprint_lock"] != "yes" and P_GATE_LOCK.search(check_text):
                ev_raw += 0.12

        ev_gain = 0.62 * (min(1.0, ev_raw / 0.85) ** 0.68) if ev_raw > 0 else 0.0
        base = SAFETY_BASELINE_BY_ROOM_TYPE.get(rt_code, 0.30)
        return round(max(0.0, min(1.0, base + ev_gain)), 2)

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
