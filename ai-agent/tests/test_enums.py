import json

import pytest

from domain.enums import (
    AMENITY_LABELS_VI,
    CANONICAL_AMENITIES,
    ROOM_TYPE_ID_TO_NAME,
    ROOM_TYPE_NAME_TO_ID,
    Amenity,
    HitlAction,
    RoomType,
    amenity_glossary,
    amenity_label,
    normalize_amenities,
    normalize_amenity,
    normalize_room_type,
    normalize_room_types,
    _AMENITY_META,
    _AMENITY_INDEX,
)
from utils.text import norm_key


def test_17_canonical_amenities():
    assert len(CANONICAL_AMENITIES) == 17
    assert set(AMENITY_LABELS_VI) == CANONICAL_AMENITIES


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("máy lạnh", Amenity.AIRCON), ("Máy Lạnh", Amenity.AIRCON), ("may lanh", Amenity.AIRCON),
        ("ml", Amenity.AIRCON), ("AC", Amenity.AIRCON), ("aircon", Amenity.AIRCON), ("AIRCON", Amenity.AIRCON),
        ("điều hòa", Amenity.AIRCON), ("điều hoà", Amenity.AIRCON),
        ("có gác", Amenity.MEZZANINE), ("gác lững", Amenity.MEZZANINE), ("gac", Amenity.MEZZANINE),
        ("khép kín", Amenity.PRIVATE_WC), ("nuôi boss", Amenity.PET_ALLOWED), ("thú cưng", Amenity.PET_ALLOWED),
        ("balcony", Amenity.WINDOW_BALCONY), ("ban công", Amenity.WINDOW_BALCONY),
        ("24/24", Amenity.FREE_HOURS), ("ko chung chủ", Amenity.NO_SHARED_LANDLORD),
        ("bảo vệ", Amenity.GUARD), ("an ninh", Amenity.SAFE_AREA),
    ],
)
def test_normalize_amenity(raw, expected):
    assert normalize_amenity(raw) is expected


@pytest.mark.parametrize("raw", ["xyz", "", None, "bay trong phong"])
def test_normalize_amenity_unknown(raw):
    assert normalize_amenity(raw) is None


def test_every_code_and_label_resolves_to_itself():
    for a, (label, aliases) in _AMENITY_META.items():
        assert normalize_amenity(a.value) is a
        assert normalize_amenity(label) is a
        for al in aliases:
            assert normalize_amenity(al) is a, f"alias '{al}' không trỏ về {a}"


def test_no_alias_collisions():
    seen: dict[str, Amenity] = {}
    for a, (label, aliases) in _AMENITY_META.items():
        for s in (a.value, label, *aliases):
            k = norm_key(s)
            assert seen.setdefault(k, a) is a, f"alias '{s}' trùng giữa {seen[k]} và {a}"


def test_normalize_amenities_dedup_order_and_drop_unknown():
    out = normalize_amenities(["máy lạnh", "xyz", "ml", "gác", None, "camera"])
    assert out == [Amenity.AIRCON, Amenity.MEZZANINE, Amenity.CAMERA]
    assert normalize_amenities(None) == []


def test_amenity_label():
    assert amenity_label(Amenity.AIRCON) == "máy lạnh"
    assert amenity_label("ml") == "máy lạnh"
    assert amenity_label("lạ hoắc") == "lạ hoắc"


def test_str_enum_behaves_like_string():
    assert f"{Amenity.AIRCON}" == "aircon"
    assert str(RoomType.SLEEPBOX) == "SLEEPBOX"
    assert ", ".join([Amenity.AIRCON, Amenity.CAMERA]) == "aircon, camera"
    assert json.dumps({"a": Amenity.AIRCON, "r": RoomType.ROOM}) == '{"a": "aircon", "r": "ROOM"}'
    assert Amenity.AIRCON == "aircon"
    assert {"aircon": 1}[Amenity.AIRCON] == 1


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("SLEEPBOX", RoomType.SLEEPBOX), ("sleepbox", RoomType.SLEEPBOX), ("KTX", RoomType.SLEEPBOX),
        ("ký túc xá", RoomType.SLEEPBOX), ("ở ghép", RoomType.SLEEPBOX),
        (4, RoomType.SLEEPBOX), ("4", RoomType.SLEEPBOX), (RoomType.SLEEPBOX, RoomType.SLEEPBOX),
        ("phòng trọ", RoomType.ROOM), ("studio", RoomType.STUDIO), ("chung cư", RoomType.APARTMENT),
        ("nhà nguyên căn", RoomType.WHOLE_HOUSE), (5, RoomType.WHOLE_HOUSE),
    ],
)
def test_normalize_room_type(raw, expected):
    assert normalize_room_type(raw) is expected


@pytest.mark.parametrize("raw", [None, "", "tàu vũ trụ", 99, True, "99"])
def test_normalize_room_type_unknown(raw):
    assert normalize_room_type(raw) is None


def test_room_type_id_mapping_roundtrip():
    for rt in RoomType:
        assert RoomType.from_id(rt.type_id) is rt
        assert ROOM_TYPE_NAME_TO_ID[rt.value] == rt.type_id
        assert ROOM_TYPE_ID_TO_NAME[rt.type_id] == rt.value
        assert rt.label_vi
    assert sorted(r.type_id for r in RoomType) == [1, 2, 3, 4, 5]


def test_normalize_room_types_dedup():
    assert normalize_room_types(["ktx", "sleepbox", "studio", "bậy"]) == [RoomType.SLEEPBOX, RoomType.STUDIO]


def test_amenity_glossary_lists_every_code():
    g = amenity_glossary()
    for code in CANONICAL_AMENITIES:
        assert f"- {code}:" in g


def test_hitl_actions():
    assert {a.value for a in HitlAction} == {"relax_budget", "broaden", "dormitory", "reduce_amenities", "keep", "custom"}
    assert HitlAction("keep") is HitlAction.KEEP
