"""NLU: MỘT lượt gọi LLM có đầu ra có cấu trúc (TurnAnalysis).

Nguyên tắc: LLM phân tích ngữ nghĩa ("người dùng đã nói gì": patch, mức ưu tiên định tính, ý định);
CODE thực thi các bất biến trạng thái (apply_patch, đổi mức -> hệ số, kiểm tra enum/slug/rank hợp lệ).
Mọi hàm ở đây là hàm thuần (không đọc/ghi session) để kiểm thử độc lập.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from domain.enums import (
    Amenity,
    RoomType,
    normalize_amenities,
    normalize_amenity,
    normalize_room_type,
    normalize_room_types,
)
from domain.schemas import UserPreferenceState
from prompts.nlu_prompt import (
    INTENT_GUIDE,
    NLU_RULES,
    build_nlu_system_prompt,
)
from utils.text import norm_key, strip_accents

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 2000
CRITERIA = ("price", "location", "safety", "amenity", "semantic")

IntentT = Literal[
    "new_search",
    "refine_search",
    "room_followup",
    "skill_advice",
    "smalltalk",
    "off_topic",
    "prompt_injection",
]
Level = Literal["lower", "normal", "high", "very_high"]

# Chỗ DUY NHẤT giữ con số ưu tiên
LEVEL_TO_MULT: dict[str, float] = {"lower": 0.5, "normal": 1.0, "high": 2.0, "very_high": 3.0}


# ---------------------------------------------------------------------------
# Schema đầu ra của LLM
# ---------------------------------------------------------------------------
class Priorities(BaseModel):
    """Mức ưu tiên từng tiêu chí. None = người dùng KHÔNG nhắc tới (giữ nguyên); 'normal' = đặt lại mức bình thường."""

    price: Optional[Level] = Field(
        None,
        description="Đặt 'high' hoặc 'very_high' khi người dùng nhấn mạnh giá rẻ, tiết kiệm, sinh viên nghèo, rẻ hơn",
    )
    location: Optional[Level] = Field(
        None,
        description="Đặt 'high' hoặc 'very_high' khi người dùng nhấn mạnh vị trí sát trường, đi bộ được, rất gần",
    )
    safety: Optional[Level] = Field(
        None,
        description="Đặt 'high' hoặc 'very_high' khi người dùng nhấn mạnh khu an ninh, an toàn, nữ ở một mình",
    )
    amenity: Optional[Level] = Field(
        None,
        description="Đặt 'high' hoặc 'very_high' khi người dùng nhấn mạnh full nội thất xịn, đầy đủ tiện nghi cao cấp",
    )
    semantic: Optional[Level] = Field(
        None,
        description="Đặt 'high' khi người dùng mô tả chi tiết phong cách sống hoặc không gian đặc thù",
    )


class PreferencePatch(BaseModel):
    """Tiêu chí người dùng nêu hoặc thay đổi TRONG LƯỢT NÀY."""

    location_text: Optional[str] = Field(None, description="Tên riêng của địa danh/khu vực (đã gộp tỉnh/thành từ ngữ cảnh nếu có)")
    location_kind: Optional[Literal["admin", "place"]] = Field(
        None,
        description="'admin' cho mọi tên Tỉnh/Thành phố/Quận/Huyện/Thị xã/Phường/Xã (kể cả không có chữ Tỉnh/Quận/Phường ở đầu như 'Quảng Ngãi', 'Cầu Giấy Hà Nội', 'Linh Trung Thủ Đức', 'Dĩ An'); 'place' CHỈ dùng cho điểm mốc cụ thể như trường học, KTX, chợ, KCN có tên riêng, toà nhà, tên đường (vd: 'UIT', 'ĐH Bách Khoa', 'chợ Thủ Đức', 'KCN VSIP 1')",
    )
    location_is_vague: bool = Field(False, description="True nếu chỉ nêu danh từ chung chưa có tên riêng (vd: 'gần trường', 'gần khu công nghiệp')")
    vague_category: Optional[str] = Field(
        None,
        description="Cụm danh từ chỉ loại địa điểm chung chung khi location_is_vague=True (vd: 'khu công nghiệp', 'trường đại học')",
    )
    location_region: Optional[str] = Field(
        None,
        description="Tên Tỉnh/Thành phố hoặc Quận/Huyện đi kèm trong câu hoặc ngữ cảnh (vd: 'Bình Dương' trong 'gần khu công nghiệp ở Bình Dương')",
    )
    min_price: Optional[float] = Field(
        None,
        description="Giá tối thiểu (VNĐ) — CHỈ điền khi người dùng nêu rõ mức sàn 'từ X đến Y' hoặc 'trên X'; BẮT BUỘC để null nếu người dùng nói 'dưới X', 'khoảng X', 'tầm X', 'loanh quanh X'",
    )
    max_price: Optional[float] = Field(
        None,
        description="Giá tối đa / trần ngân sách (VNĐ) — điền X khi người dùng nói 'dưới X', 'khoảng X', 'tầm X', 'loanh quanh X', hoặc 'từ Y đến X'",
    )
    min_area: Optional[float] = Field(None, description="Diện tích tối thiểu (m²)")
    max_area: Optional[float] = Field(None, description="Diện tích tối đa (m²)")
    room_type: Optional[RoomType] = Field(None, description="Loại phòng người dùng MUỐN")
    room_types_exclude: list[RoomType] = Field(
        default_factory=list,
        description="Loại phòng người dùng PHỦ ĐỊNH rõ ràng (vd: 'không lấy KTX', 'trừ sleepbox'); để rỗng [] nếu người dùng không phủ định",
    )
    amenities_add: list[Amenity] = Field(
        default_factory=list,
        description="Tiện ích BẮT BUỘC người dùng nêu trực tiếp bằng tên (không tự suy diễn từ 'khu an ninh', 'nuôi mèo' hay 'studio')",
    )
    preferred_amenities_add: list[Amenity] = Field(default_factory=list, description="Tiện ích ƯU TIÊN mềm ('ưu tiên...', 'càng tốt')")
    amenities_remove: list[Amenity] = Field(default_factory=list, description="Tiện ích người dùng không cần nữa")
    special_requirements_add: list[str] = Field(
        default_factory=list,
        description="Đặc điểm phòng ngoài danh mục Amenity (vd: 'yên tĩnh', 'hẻm xe hơi'). Không đưa từ đệm giao tiếp vào đây",
    )
    special_requirements_remove: list[str] = Field(
        default_factory=list,
        description="Yêu cầu mềm người dùng muốn huỷ bỏ",
    )
    clear: list[Literal["location", "price", "area", "room_type", "amenities", "special_requirements"]] = Field(
        default_factory=list, description="Nhóm tiêu chí người dùng không còn cần nữa"
    )

    @field_validator("location_text")
    @classmethod
    def _clean_loc(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v = re.sub(r"\s*\((?:ví dụ|vd|vd:)[^)]*\)", "", v, flags=re.IGNORECASE)
        v = re.sub(r"^(?:khu vực\s+)?(?:lân cận|quanh)\s+", "", v.strip(), flags=re.IGNORECASE)
        v = v.strip(" ,.-")
        return v or None

    @field_validator("min_price", "max_price")
    @classmethod
    def _price(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        if 0 < v < 100:                       # LLM trả '3.5' nghĩa là triệu
            return v * 1_000_000
        return v if 100_000 <= v <= 1_000_000_000 else None

    @field_validator("min_area", "max_area")
    @classmethod
    def _area(cls, v: Optional[float]) -> Optional[float]:
        return v if v is not None and 3 <= v <= 1000 else None

    @field_validator("room_type", mode="before")
    @classmethod
    def _rt(cls, v: Any) -> Optional[RoomType]:
        return normalize_room_type(v)

    @field_validator("room_types_exclude", mode="before")
    @classmethod
    def _rt_ex(cls, v: Any) -> list[RoomType]:
        return normalize_room_types(v)

    @field_validator("amenities_add", "amenities_remove", "preferred_amenities_add", mode="before")
    @classmethod
    def _am(cls, v: Any) -> list[Amenity]:
        return normalize_amenities(v)

    def is_empty(self) -> bool:
        return not self.model_dump(exclude_defaults=True, exclude_none=True)


class TurnAnalysis(BaseModel):
    intent: IntentT
    skill_slug: Optional[str] = Field(None, description="Điền mã kỹ năng khi người dùng hỏi kiến thức thuộc danh mục kỹ năng")
    referenced_room_rank: Optional[int] = Field(None, description="Thứ hạng phòng được nhắc tới (1-5)")
    is_multi_intent: bool = Field(
        False,
        description="True nếu người dùng gộp nhiều mệnh lệnh khác nhánh trong cùng 1 câu (VD: vừa tìm phòng vừa hỏi kỹ năng hợp đồng, hoặc vừa hỏi chi tiết phòng cũ vừa đổi tiêu chí tìm phòng mới)",
    )
    patch: PreferencePatch = Field(default_factory=PreferencePatch)
    priorities: Priorities = Field(default_factory=Priorities)
    priority_reasons: list[str] = Field(default_factory=list, description="Giải thích ngắn tiếng Việt, KHÔNG nêu con số/hệ số")
    reset_priorities: bool = Field(False, description="True nếu là nhu cầu tìm kiếm hoàn toàn mới")
    semantic_query: Optional[str] = Field(
        None,
        description="Câu truy vấn RAG tiếng Việt cô đọng tổng hợp nhu cầu hiện tại (bỏ hoàn toàn câu đệm giao tiếp/than phiền)",
    )


# ---------------------------------------------------------------------------
# Hàm thuần: áp patch, đổi mức ưu tiên
# ---------------------------------------------------------------------------
def _same_place(a: Optional[str], b: Optional[str]) -> bool:
    return bool(a and b and norm_key(a) == norm_key(b))


def apply_patch(pref: UserPreferenceState, patch: PreferencePatch) -> UserPreferenceState:
    """Trả BẢN MỚI, không đụng `pref`. Đổi vị trí => xoá toạ độ/ID cũ (qua set_location)."""
    p = pref.model_copy(deep=True)

    for group in patch.clear:
        if group == "location":
            p.clear_location()
        elif group == "price":
            p.min_price = p.max_price = None
        elif group == "area":
            p.min_area = p.max_area = None
        elif group == "room_type":
            p.room_type = None
            p.excluded_room_types = []
        elif group == "amenities":
            p.amenities = []
            p.preferred_amenities = []
        elif group == "special_requirements":
            p.special_requirements = []

    # Địa danh chung chung KHÔNG ghi vào tiêu chí (chờ người dùng nêu tên riêng)
    if patch.location_text and not patch.location_is_vague and not _same_place(patch.location_text, p.location_text):
        p.set_location(patch.location_text.strip(), kind=patch.location_kind)
    elif patch.location_kind and p.location_text and not patch.location_is_vague and p.location_kind is None:
        p.location_kind = patch.location_kind        # cùng địa danh nhưng giờ mới biết loại

    for key in ("min_price", "max_price", "min_area", "max_area"):
        v = getattr(patch, key)
        if v is not None:
            setattr(p, key, v)
    # Khoảng giá/diện tích không hợp lệ: ưu tiên giá trị người dùng vừa nói
    if p.min_price is not None and p.max_price is not None and p.min_price > p.max_price:
        if patch.max_price is not None and patch.min_price is None:
            p.min_price = None
        else:
            p.max_price = None
    if p.min_area is not None and p.max_area is not None and p.min_area > p.max_area:
        if patch.max_area is not None and patch.min_area is None:
            p.min_area = None
        else:
            p.max_area = None

    if patch.room_type is not None:
        p.room_type = patch.room_type
        p.excluded_room_types = [r for r in p.excluded_room_types if r != patch.room_type]
    if patch.room_types_exclude:                     # phủ định thắng nếu mâu thuẫn trong cùng lượt
        p.excluded_room_types = list(dict.fromkeys([*p.excluded_room_types, *patch.room_types_exclude]))
        if p.room_type in p.excluded_room_types:
            p.room_type = None

    if patch.amenities_add or patch.amenities_remove or patch.preferred_amenities_add:
        remove = set(patch.amenities_remove)
        # Bắt buộc: thêm mới và loại trừ remove
        p.amenities = [a for a in [*p.amenities, *patch.amenities_add] if a not in remove]
        # Ưu tiên mềm: thêm mới và loại trừ remove
        p.preferred_amenities = [a for a in [*p.preferred_amenities, *patch.preferred_amenities_add] if a not in remove]
        # Nếu tiện ích đã là bắt buộc thì không để trùng trong ưu tiên mềm
        mand_set = set(p.amenities)
        p.preferred_amenities = [a for a in p.preferred_amenities if a not in mand_set]

    if patch.special_requirements_remove:
        rem_reqs = {r.strip().lower() for r in patch.special_requirements_remove if r}
        p.special_requirements = [s for s in p.special_requirements if s.strip().lower() not in rem_reqs]

    if patch.special_requirements_add:
        p.special_requirements = list(dict.fromkeys([*p.special_requirements, *patch.special_requirements_add]))
    return p


def mult_to_level(v: float) -> str:
    return min(LEVEL_TO_MULT, key=lambda lvl: abs(LEVEL_TO_MULT[lvl] - v))


def multipliers_to_levels(multipliers: Optional[dict[str, float]]) -> dict[str, str]:
    m = multipliers or {}
    return {k: mult_to_level(m.get(k, 1.0)) for k in CRITERIA}


def apply_priorities(current: Optional[dict[str, float]], priorities: Priorities, reset: bool = False) -> dict[str, float]:
    """Trả hệ số mới. None = giữ nguyên; 'normal' = về 1.0; reset=True = bắt đầu lại từ 1.0."""
    out = {k: 1.0 for k in CRITERIA}
    if not reset:
        out.update({k: float(v) for k, v in (current or {}).items() if k in CRITERIA})
    for k in CRITERIA:
        lvl = getattr(priorities, k)
        if lvl is not None:
            out[k] = LEVEL_TO_MULT[lvl]
    return out


_TAG = re.compile(r"</?\s*user_message\s*>", re.IGNORECASE)


def sanitize_user_text(text: str) -> str:
    """Cắt độ dài và gỡ thẻ <user_message> do người dùng tự chèn để thoát khỏi khung dữ liệu."""
    return _TAG.sub("", (text or "")[:MAX_INPUT_CHARS]).strip()


def _build_context(
    pref: UserPreferenceState,
    rooms_brief: str,
    multipliers: Optional[dict],
    recent_dialog_turns: Optional[list[tuple[str, str]]] = None,
    recent_user_turns: Optional[list[str]] = None,
) -> str:
    if recent_dialog_turns:
        history_lines = []
        for role, msg in recent_dialog_turns[-4:]:
            label = "Người dùng" if role == "user" else "Trợ lý Homigo"
            history_lines.append(f"  - {label}: {msg}")
        history_str = "\n".join(history_lines)
    elif recent_user_turns:
        history_str = (
            "\n".join(f"  - Lượt trước {i+1}: {msg}" for i, msg in enumerate(recent_user_turns[-3:]))
        )
    else:
        history_str = "chưa có"
    return (
        f"Tiêu chí hiện tại:\n{pref.to_context_string()}\n"
        f"Mức ưu tiên hiện tại: {multipliers_to_levels(multipliers)}\n"
        f"Lịch sử đối thoại gần nhất (dùng để hiểu đại từ 'nó', câu trả lời cho Trợ lý, hoặc khi người dùng nói 'như lúc nãy'):\n{history_str}\n"
        f"Phòng vừa đề xuất ở lượt trước: {rooms_brief or 'chưa có'}"
    )


# ---------------------------------------------------------------------------
# Kiểm định bất biến cấu trúc đầu ra NLU (Schema & State Invariants)
# ---------------------------------------------------------------------------
def _postprocess(
    a: TurnAnalysis,
    *,
    user_text: str = "",
    n_rooms: int = 0,
    valid_slugs: Optional[set[str]] = None,
) -> TurnAnalysis:
    """Kiểm định tính hợp lệ của dữ liệu cấu trúc (Schema & State Invariants):
    1. Chuẩn hoá nếu LLM đặt mã Amenity chuẩn vào `special_requirements_add` thì nâng lên `amenities_add`.
    2. Bảo vệ tiêu chí tích lũy: Chặn LLM tự ý điền `clear: ['location']` nếu người dùng không có từ khóa hủy bỏ.
    3. Kiểm định `skill_slug` thuộc danh mục kỹ năng hiện có và `referenced_room_rank` trong khoảng `1..n_rooms`.
    4. Phát hiện đa mệnh lệnh (`is_multi_intent`) khi người dùng gộp nhiều tác vụ khác nhánh trong cùng một lượt.
    5. Xoá `semantic_query` đối với các intent không thực hiện tìm kiếm.
    """
    valid = valid_slugs or set()

    # Bảo vệ tiêu chí tích luỹ chống Hallucination của LLM trong patch.clear:
    # LLM (đặc biệt là model local) hay tự ý điền clear: ['location', 'price', ...] dù người dùng chỉ nói "thêm máy lạnh".
    # CHỈ chấp nhận clear từng nhóm khi văn bản người dùng thực sự có từ khóa mang nghĩa xoá bỏ/hủy/phủ định.
    if a.patch.clear and user_text:
        clean_msg = strip_accents(user_text).lower()
        has_general_reset = bool(re.search(r"\b(?:reset|bo het|xoa het|huy het|tim lai tu dau|nhu moi)\b", clean_msg))
        is_new_location_search = bool(a.patch.location_text and (a.intent == "new_search" or a.reset_priorities))
        if not has_general_reset:
            validated_clear = []
            for group in a.patch.clear:
                if group == "location":
                    if re.search(r"\b(?:bo|xoa|huy|khong can|ko can)\b.*\b(?:vi tri|khu vuc|dia diem|o do|uit|quan|truong)\b", clean_msg) or re.search(r"\b(?:dau cung duoc|khap noi|bat ky dau|toan thanh pho)\b", clean_msg):
                        validated_clear.append(group)
                elif group == "price":
                    if re.search(r"\b(?:bo|xoa|huy|khong can|ko can)\b.*\b(?:gia|ngan sach|tien)\b", clean_msg) or re.search(r"\b(?:gia nao cung duoc|bao nhieu cung duoc)\b", clean_msg):
                        validated_clear.append(group)
                elif group == "area":
                    if re.search(r"\b(?:bo|xoa|huy|khong can|ko can)\b.*\b(?:dien tich|m2|rong)\b", clean_msg):
                        validated_clear.append(group)
                elif group == "room_type":
                    if re.search(r"\b(?:bo|xoa|huy|khong can|ko can)\b.*\b(?:loai phong|phong tro|ktx|can ho)\b", clean_msg):
                        validated_clear.append(group)
                elif group == "amenities":
                    if is_new_location_search or re.search(r"\b(?:bo|xoa|huy|khong can|ko can)\b.*\b(?:tien ich|do dac|noi that)\b", clean_msg) or bool(a.patch.amenities_remove):
                        validated_clear.append(group)
                elif group == "special_requirements":
                    if is_new_location_search or re.search(r"\b(?:bo|xoa|huy|khong can|ko can)\b.*\b(?:yeu cau|dac diem)\b", clean_msg) or bool(a.patch.special_requirements_remove):
                        validated_clear.append(group)
            a.patch.clear = validated_clear

    # Bất biến ngân sách: nếu LLM điền min_price == max_price (do người dùng nói "khoảng 3 triệu"),
    # chỉ giữ trần ngân sách max_price, đặt min_price = None để không lọc cứng price == X.
    if a.patch.min_price is not None and a.patch.max_price is not None and a.patch.min_price >= a.patch.max_price:
        a.patch.min_price = None

    # Nếu một mục trong special_requirements_add thực chất trùng khớp Amenity enum thì chuyển sang amenities_add
    if a.patch.special_requirements_add:
        remained_specials: list[str] = []
        for req in a.patch.special_requirements_add:
            am = normalize_amenity(req)
            if am is not None:
                if am not in a.patch.amenities_add and am not in a.patch.preferred_amenities_add:
                    a.patch.amenities_add.append(am)
            else:
                remained_specials.append(req)
        a.patch.special_requirements_add = remained_specials

    raw_slug = (a.skill_slug or "").strip().lower()
    if raw_slug in valid:
        valid_slug: Optional[str] = raw_slug
    elif a.intent == "skill_advice" and len(valid) == 1:
        valid_slug = next(iter(valid))
    else:
        valid_slug = None

    valid_rank: Optional[int] = (
        a.referenced_room_rank
        if (n_rooms > 0 and a.referenced_room_rank is not None and 1 <= a.referenced_room_rank <= n_rooms)
        else None
    )

    # Nếu intent chính là skill_advice và không có tiêu chí tìm kiếm cốt lõi (địa điểm cụ thể, giá trần, loại phòng)
    # thì xoá các trường phụ bị rò rỉ trong patch (tránh chặn nhầm câu hỏi hợp đồng dài thành đa mệnh lệnh).
    has_concrete_search_target = bool(
        (a.patch.location_text and not a.patch.location_is_vague)
        or a.patch.max_price is not None
        or a.patch.room_type is not None
    )
    if a.intent == "skill_advice" and not has_concrete_search_target:
        a.patch = PreferencePatch()

    has_search_patch = bool(
        has_concrete_search_target
        or a.patch.min_price is not None
        or a.patch.min_area is not None
        or a.patch.max_area is not None
        or a.patch.room_types_exclude
        or a.patch.amenities_add
        or a.patch.preferred_amenities_add
    )
    has_skill = valid_slug is not None
    has_followup = (valid_rank is not None) or (a.intent == "room_followup" and n_rooms > 0)

    # Đa mệnh lệnh khi kết hợp >= 2 nhánh độc lập:
    # - Tìm phòng (có tiêu chí tìm phòng thực sự) + Hỏi kỹ năng (valid_slug)
    # - Hỏi phòng cũ (valid_rank / followup) + Hỏi kỹ năng (valid_slug)
    # - Tìm phòng (có patch) + Hỏi phòng cũ (khi intent là tìm kiếm nhưng kèm valid_rank, hoặc LLM bật is_multi_intent)
    is_compound = (
        (has_search_patch and has_skill)
        or (has_followup and has_skill)
        or (has_search_patch and valid_rank is not None and (a.is_multi_intent or a.intent in ("new_search", "refine_search")))
        or (a.is_multi_intent and sum([has_search_patch, has_skill, has_followup]) >= 2)
    )

    if is_compound:
        a.is_multi_intent = True
        a.skill_slug = valid_slug
        a.referenced_room_rank = valid_rank
        return a

    a.is_multi_intent = False
    if a.intent == "skill_advice":
        if valid_slug:
            a.skill_slug = valid_slug
        else:
            a.intent, a.skill_slug = "smalltalk", None
    else:
        a.skill_slug = None

    if a.intent == "room_followup":
        a.referenced_room_rank = valid_rank
        if n_rooms > 0:
            a.patch = PreferencePatch()
    else:
        a.referenced_room_rank = None

    if a.intent not in ("new_search", "refine_search"):
        a.semantic_query = None
    elif a.semantic_query:
        a.semantic_query = sanitize_user_text(a.semantic_query).strip() or None

    return a


def analyze_turn(
    model: Any,
    user_text: str,
    pref: UserPreferenceState,
    *,
    rooms_brief: str = "",
    multipliers: Optional[dict[str, float]] = None,
    n_rooms: int = 0,
    skills: Optional[dict[str, Any]] = None,
    recent_dialog_turns: Optional[list[tuple[str, str]]] = None,
    recent_user_turns: Optional[list[str]] = None,
) -> Optional[TurnAnalysis]:
    """Gọi LLM 1 lần để phân tích lượt hội thoại. Trả None khi không có model hoặc lỗi kết nối."""
    text = sanitize_user_text(user_text)
    if model is None or not text:
        return None
    if skills is None:
        from skills.skills_discovery import discover_housing_skills

        skills = discover_housing_skills()
    from skills.skills_discovery import skills_catalog_for_prompt

    messages = [
        ("system", build_nlu_system_prompt(skills_catalog_for_prompt(skills))),
        ("human", f"{_build_context(pref, rooms_brief, multipliers, recent_dialog_turns=recent_dialog_turns, recent_user_turns=recent_user_turns)}\n\n<user_message>\n{text}\n</user_message>"),
    ]
    kwargs: dict[str, Any] = {}
    method = os.environ.get("NLU_STRUCTURED_METHOD")
    if method:
        kwargs["method"] = method
    import time as _time

    analysis: Optional[TurnAnalysis] = None
    for attempt in range(3):
        try:
            raw = model.with_structured_output(TurnAnalysis, **kwargs).invoke(messages)
            if raw is None:
                return None
            analysis = raw if isinstance(raw, TurnAnalysis) else TurnAnalysis.model_validate(raw)
            break
        except Exception as exc:
            err_msg = str(exc).lower()
            is_rate_limit = any(t in err_msg for t in ("429", "rate limit", "resource_exhausted", "quota", "too many requests"))
            if is_rate_limit and attempt < 3:
                wait_sec = 12.0 * (attempt + 1)
                logger.warning("analyze_turn chạm rate limit (429), chờ %.1fs rồi thử lại lần %d...", wait_sec, attempt + 1)
                _time.sleep(wait_sec)
                continue
            is_transient = any(t in err_msg for t in ("model unloaded", "model reloaded", "failed to load model", "connection", "timeout"))
            if is_transient and attempt < 2:
                _time.sleep(1.0)
                continue
            logger.exception("analyze_turn gặp lỗi khi gọi LLM")
            return None
    if analysis is None:
        return None
    return _postprocess(analysis, user_text=text, n_rooms=n_rooms, valid_slugs=set(skills))


__all__ = [
    "MAX_INPUT_CHARS",
    "CRITERIA",
    "IntentT",
    "Level",
    "LEVEL_TO_MULT",
    "Priorities",
    "PreferencePatch",
    "TurnAnalysis",
    "apply_patch",
    "mult_to_level",
    "multipliers_to_levels",
    "apply_priorities",
    "INTENT_GUIDE",
    "NLU_RULES",
    "build_nlu_system_prompt",
    "sanitize_user_text",
    "analyze_turn",
]
