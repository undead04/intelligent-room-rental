"""Nguồn sự thật DUY NHẤT cho: mã tiện ích, loại phòng, hành động HITL.

Thay thế các bảng đang lặp ở nhiều file:
  - schemas.CANONICAL_AMENITIES / ROOM_TYPE_*            (giữ lại bên dưới dưới dạng suy ra từ enum)
  - graph.AMENITY_LABELS_VI / ROOM_TYPE_LABELS_VI
  - tools.AMENITY_ALIAS_MAP
  - grounding: dict {"ROOM": 1, ...} viết tay hai lần
  - prompts: danh sách mã tiện ích (dùng amenity_glossary() để sinh)

Các enum kế thừa `str` nên code cũ (`", ".join(pref.amenities)`, `dict.get(a, a)`,
json.dumps) vẫn chạy trong lúc bạn chuyển dần.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable, Optional

from utils.text import norm_key


class _StrEnum(str, Enum):
    """str-Enum có __str__/format trả về GIÁ TRỊ (nhất quán giữa Python 3.10 → 3.12)."""

    def __str__(self) -> str:  # noqa: D105
        return str(self.value)

    def __format__(self, spec: str) -> str:  # noqa: D105
        return format(str(self.value), spec)


# ---------------------------------------------------------------------------
# Tiện ích
# ---------------------------------------------------------------------------
class Amenity(_StrEnum):
    PRIVATE_WC = "private_wc"
    AIRCON = "aircon"
    MEZZANINE = "mezzanine"
    KITCHEN = "kitchen"
    FRIDGE = "fridge"
    WASHING_MACHINE = "washing_machine"
    WINDOW_BALCONY = "window_balcony"
    FURNITURE = "furniture"
    PARKING = "parking"
    ELEVATOR = "elevator"
    FREE_HOURS = "free_hours"
    NO_SHARED_LANDLORD = "no_shared_landlord"
    PET_ALLOWED = "pet_allowed"
    FINGERPRINT_LOCK = "fingerprint_lock"
    CAMERA = "camera"
    GUARD = "guard"
    SAFE_AREA = "safe_area"

    @property
    def label_vi(self) -> str:
        return _AMENITY_META[self][0]


# mã -> (nhãn tiếng Việt, alias CÓ DẤU cho prompt dễ đọc; khi tra cứu sẽ bỏ dấu)
_AMENITY_META: dict[Amenity, tuple[str, tuple[str, ...]]] = {
    Amenity.PRIVATE_WC: ("WC riêng", ("vệ sinh riêng", "khép kín", "toilet riêng")),
    Amenity.AIRCON: ("máy lạnh", ("điều hòa", "điều hoà", "ml", "ac")),
    Amenity.MEZZANINE: ("gác lửng", ("gác cao", "gác lững", "gác đúc", "gác xép", "có gác", "gác")),
    Amenity.KITCHEN: ("kệ bếp", ("bếp", "nấu ăn", "chỗ nấu ăn", "nấu nướng")),
    Amenity.FRIDGE: ("tủ lạnh", ()),
    Amenity.WASHING_MACHINE: ("máy giặt", ()),
    Amenity.WINDOW_BALCONY: ("ban công/cửa sổ", ("ban công", "cửa sổ", "view thoáng", "thoáng mát", "balcony")),
    Amenity.FURNITURE: ("full nội thất", ("nội thất", "đầy đủ đồ")),
    Amenity.PARKING: ("chỗ để xe", ("hầm xe", "bãi xe", "nhà xe")),
    Amenity.ELEVATOR: ("thang máy", ()),
    Amenity.FREE_HOURS: ("giờ tự do", ("24/24", "giờ giấc tự do")),
    Amenity.NO_SHARED_LANDLORD: ("không chung chủ", ("ko chung chủ", "lối đi riêng", "phòng không chung chủ")),
    Amenity.PET_ALLOWED: ("cho nuôi pet", ("nuôi boss", "nuôi chó", "nuôi mèo", "thú cưng", "pet")),
    Amenity.FINGERPRINT_LOCK: ("khóa vân tay", ("khoá vân tay", "thẻ từ")),
    Amenity.CAMERA: ("camera an ninh", ("camera",)),
    Amenity.GUARD: ("bảo vệ 24/7", ("bảo vệ",)),
    Amenity.SAFE_AREA: ("khu an ninh", ("an ninh", "an toàn")),
}

_AMENITY_INDEX: dict[str, Amenity] = {}
for _a, (_label, _aliases) in _AMENITY_META.items():
    for _s in (_a.value, _label, *_aliases):
        _AMENITY_INDEX.setdefault(norm_key(_s), _a)


def amenity_label(a: "Amenity | str") -> str:
    """Nhãn tiếng Việt; mã lạ thì trả lại nguyên văn."""
    code = normalize_amenity(a)
    return _AMENITY_META[code][0] if code else str(a)


def normalize_amenity(raw: "Amenity | str | None") -> Optional[Amenity]:
    """'Máy lạnh' / 'ml' / 'AIRCON' / Amenity.AIRCON -> Amenity.AIRCON; không nhận ra -> None."""
    if raw is None:
        return None
    if isinstance(raw, Amenity):
        return raw
    return _AMENITY_INDEX.get(norm_key(str(raw)))


def normalize_amenities(items: Optional[Iterable["Amenity | str"]]) -> list[Amenity]:
    """Chuẩn hoá cả danh sách: bỏ mã lạ, bỏ trùng, GIỮ thứ tự."""
    out: list[Amenity] = []
    for x in items or []:
        a = normalize_amenity(x)
        if a is not None and a not in out:
            out.append(a)
    return out


def amenity_glossary() -> str:
    """Danh mục mã tiện ích gọn để chèn vào prompt (alias đã do normalize_amenity xử lý)."""
    return "\n".join(f"- {a.value}: {label}" for a, (label, _) in _AMENITY_META.items())


# ---------------------------------------------------------------------------
# Loại phòng
# ---------------------------------------------------------------------------
class RoomType(_StrEnum):
    ROOM = "ROOM"
    STUDIO = "STUDIO"
    APARTMENT = "APARTMENT"
    SLEEPBOX = "SLEEPBOX"
    WHOLE_HOUSE = "WHOLE_HOUSE"

    @property
    def type_id(self) -> int:
        return _ROOM_TYPE_META[self][0]

    @property
    def label_vi(self) -> str:
        return _ROOM_TYPE_META[self][1]

    @classmethod
    def from_id(cls, type_id: int) -> Optional["RoomType"]:
        for rt, (rid, _l, _a) in _ROOM_TYPE_META.items():
            if rid == type_id:
                return rt
        return None


_ROOM_TYPE_META: dict[RoomType, tuple[int, str, tuple[str, ...]]] = {
    RoomType.ROOM: (1, "phòng trọ", ("phòng trọ",)),
    RoomType.STUDIO: (2, "căn hộ studio", ("studio", "căn hộ mini")),
    RoomType.APARTMENT: (3, "căn hộ chung cư", ("căn hộ", "chung cư", "chung cư dịch vụ")),
    RoomType.SLEEPBOX: (4, "ký túc xá sleepbox", ("ký túc xá", "ktx", "sleepbox", "giường tầng", "ở ghép")),
    RoomType.WHOLE_HOUSE: (5, "nhà nguyên căn", ("nguyên căn",)),
}

_ROOM_TYPE_INDEX: dict[str, RoomType] = {}
for _rt, (_rid, _lbl, _als) in _ROOM_TYPE_META.items():
    for _s in (_rt.value, _lbl, *_als):
        _ROOM_TYPE_INDEX.setdefault(norm_key(_s), _rt)


def normalize_room_type(raw: "RoomType | str | int | None") -> Optional[RoomType]:
    """'sleepbox' / 'KTX' / 4 / '4' / RoomType.SLEEPBOX -> RoomType.SLEEPBOX; không nhận ra -> None."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, RoomType):
        return raw
    if isinstance(raw, int):
        return RoomType.from_id(raw)
    s = str(raw).strip()
    if s.isdigit():
        return RoomType.from_id(int(s))
    return _ROOM_TYPE_INDEX.get(norm_key(s))


def normalize_room_types(items: Optional[Iterable["RoomType | str | int"]]) -> list[RoomType]:
    out: list[RoomType] = []
    for x in items or []:
        rt = normalize_room_type(x)
        if rt is not None and rt not in out:
            out.append(rt)
    return out


def room_type_glossary() -> str:
    """Danh mục loại phòng gọn để chèn vào prompt NLU (sinh từ enum)."""
    return "\n".join(f"- {rt.value}: {label}" for rt, (_, label, _) in _ROOM_TYPE_META.items())


# ---------------------------------------------------------------------------
# Hành động Human-in-the-Loop (frontend gửi về đúng giá trị này, không dò emoji)
# ---------------------------------------------------------------------------
class HitlAction(_StrEnum):
    RELAX_BUDGET = "relax_budget"
    BROADEN = "broaden"
    DORMITORY = "dormitory"
    REDUCE_AMENITIES = "reduce_amenities"
    KEEP = "keep"
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# Hằng số tương thích ngược (code cũ import các tên này từ schemas)
# ---------------------------------------------------------------------------
CANONICAL_AMENITIES: set[str] = {a.value for a in Amenity}
CANONICAL_ROOM_TYPES: set[str] = {r.value for r in RoomType}
ROOM_TYPE_NAME_TO_ID: dict[str, int] = {r.value: r.type_id for r in RoomType}
ROOM_TYPE_ID_TO_NAME: dict[int, str] = {r.type_id: r.value for r in RoomType}
AMENITY_LABELS_VI: dict[str, str] = {a.value: meta[0] for a, meta in _AMENITY_META.items()}
ROOM_TYPE_LABELS_VI: dict[str, str] = {r.value: r.label_vi for r in RoomType}
