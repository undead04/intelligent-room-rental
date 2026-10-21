import pytest

from tools.location_service import admin_key, level_hint, resolve_admin, resolve_location, search_term
from utils.text import norm_key

CITIES = [{"id": 79, "name": "Thành phố Hồ Chí Minh"}, {"id": 1, "name": "Thành phố Hà Nội"}, {"id": 74, "name": "Tỉnh Bình Dương"}]
DISTRICTS = [
    {"id": 784, "city_id": 79, "name": "Thành phố Thủ Đức"}, {"id": 778, "city_id": 79, "name": "Quận 7"}, {"id": 760, "city_id": 79, "name": "Quận 1"},
    {"id": 761, "city_id": 79, "name": "Quận 10"}, {"id": 724, "city_id": 74, "name": "Thành phố Dĩ An"}, {"id": 5, "city_id": 1, "name": "Quận Cầu Giấy"},
]
WARDS = [
    {"id": 1001, "district_id": 784, "name": "Phường Linh Trung"}, {"id": 1002, "district_id": 784, "name": "Phường Linh Xuân"},
    {"id": 2001, "district_id": 760, "name": "Phường 1"}, {"id": 2002, "district_id": 778, "name": "Phường 1"},
    {"id": 3001, "district_id": 5, "name": "Phường Dịch Vọng"},
]


class FakeDB:
    """Mô phỏng server-side `search`: chứa chuỗi con, KHÔNG phân biệt dấu (gần với backend thật; exact-match do code lọc)."""
    def __init__(self):
        self.calls = []

    def __call__(self, level, name, city_id=None, district_id=None):
        self.calls.append((level, name, city_id, district_id))
        rows = {"city": CITIES, "district": DISTRICTS, "ward": WARDS}[level]
        out = [r for r in rows if norm_key(name) in norm_key(r["name"]) or admin_key(name) in norm_key(r["name"])]
        if city_id is not None and level == "district":
            out = [r for r in out if r["city_id"] == city_id]
        if district_id is not None and level == "ward":
            out = [r for r in out if r["district_id"] == district_id]
        return out


def geo_ok(q, hint):
    return {"lat": 10.87, "lng": 106.8}


@pytest.mark.parametrize("raw,key", [
    ("TP. Hồ Chí Minh", "ho chi minh"), ("tphcm", "ho chi minh"), ("Thành phố Hồ Chí Minh", "ho chi minh"), ("hcm", "ho chi minh"),
    ("Quận 7", "7"), ("q7", "7"), ("Q. 10", "10"), ("Phường Linh Trung", "linh trung"), ("p1", "1"), ("Tỉnh Bình Dương", "binh duong"),
    ("Thủ Đức", "thu duc"), ("  Đà   Nẵng ", "da nang"), ("hn", "ha noi"), ("", ""), (None, ""),
])
def test_admin_key(raw, key):
    assert admin_key(raw) == key


@pytest.mark.parametrize("raw,lvl", [("Quận 7", "district"), ("q7", "district"), ("Phường 1", "ward"), ("p1", "ward"), ("Tỉnh X", "city"), ("Thủ Đức", None)])
def test_level_hint(raw, lvl):
    assert level_hint(raw) == lvl


def test_resolves_city_district_ward_single_names():
    db = FakeDB()
    r = resolve_admin("Hồ Chí Minh", db)
    assert r.kind == "admin" and r.level == "city" and r.city_id == 79
    r = resolve_admin("Thủ Đức", db)
    assert (r.level, r.city_id, r.district_id) == ("district", 79, 784)
    r = resolve_admin("linh trung", db)                                   # không dấu, không tiền tố
    assert (r.level, r.ward_id, r.district_id) == ("ward", 1001, 784)
    r = resolve_admin("Quận 1", db)                                       # 'Quận 1' không bị nhầm với 'Quận 10'
    assert (r.level, r.district_id) == ("district", 760)


def test_exact_match_rejects_server_side_substring_hits():
    assert resolve_admin("Chợ Thủ Đức", FakeDB()).kind == "admin_not_found"      # bản cũ: data[0] = quận Thủ Đức
    assert resolve_admin("Linh", FakeDB()).kind == "admin_not_found"              # chỉ là chuỗi con của 'Linh Trung/Xuân'
    assert resolve_admin("", FakeDB()).kind == "admin_not_found"


def test_multi_part_ward_district_and_district_city():
    r = resolve_admin("Linh Xuân, Thủ Đức", FakeDB())
    assert (r.level, r.ward_id, r.district_id, r.city_id) == ("ward", 1002, 784, 79)
    r = resolve_admin("Dĩ An, Bình Dương", FakeDB())
    assert (r.level, r.district_id, r.city_id) == ("district", 724, 74)
    assert resolve_admin("Linh Xuân, Quận 1", FakeDB()).kind == "admin_not_found"


def test_ambiguous_names_return_candidates_and_region_disambiguates():
    r = resolve_admin("Phường 1", FakeDB())
    assert r.kind == "ambiguous" and {c["id"] for c in r.candidates} == {2001, 2002}
    r = resolve_admin("Phường 1, Quận 7", FakeDB())
    assert r.kind == "admin" and r.ward_id == 2002


def test_region_hint_scopes_district_lookup():
    db = FakeDB()
    r = resolve_admin("Quận 7", db, region_hint="TP.HCM")
    assert r.district_id == 778
    assert ("district", "Quận 7", 79, None) in db.calls


def test_lookup_errors_are_swallowed():
    def boom(*a, **k): raise RuntimeError("db down")
    assert resolve_admin("Thủ Đức", boom).kind == "admin_not_found"


# ---------------- resolve_location ----------------
def test_kind_place_goes_straight_to_geocode():
    db = FakeDB()
    r = resolve_location("Đại học Bách Khoa", "place", db, geo_ok)
    assert r.kind == "point" and (r.lat, r.lng) == (10.87, 106.8) and db.calls == []        # không tốn truy vấn hành chính


def test_kind_admin_missing_in_db_is_admin_not_found_not_geocoded():
    called = []
    r = resolve_location("Quảng Ngãi", "admin", FakeDB(), lambda q, h: called.append(q) or {"lat": 1, "lng": 2})
    assert r.kind == "admin_not_found" and called == []


def test_kind_unknown_tries_admin_then_falls_back_to_place():
    r = resolve_location("Thủ Đức", None, FakeDB(), geo_ok)
    assert r.kind == "admin" and r.district_id == 784
    r = resolve_location("UIT", None, FakeDB(), geo_ok)
    assert r.kind == "point"


def test_geocode_failure_modes():
    assert resolve_location("UIT", "place", FakeDB(), lambda q, h: None).kind == "unresolved_point"
    def boom(q, h): raise RuntimeError("x")
    assert resolve_location("UIT", "place", FakeDB(), boom).kind == "unresolved_point"
    assert resolve_location("UIT", "place", FakeDB(), lambda q, h: {"lat": None, "lng": 1}).kind == "unresolved_point"
    assert resolve_location("  ", "place", FakeDB(), geo_ok).kind == "unresolved_point"


def test_geocode_hint_from_tail_city_or_region():
    seen = []
    geo = lambda q, h: seen.append((q, h)) or {"lat": 21.0, "lng": 105.8}
    resolve_location("ĐH Bách Khoa, Hà Nội", "place", FakeDB(), geo)
    assert seen[-1] == ("ĐH Bách Khoa, Hà Nội", "Hà Nội")
    resolve_location("ĐH Bách Khoa", "place", FakeDB(), geo, region_hint="Hà Nội")
    assert seen[-1] == ("ĐH Bách Khoa", "Hà Nội")
    resolve_location("Phố cổ, Gì Đó", "place", FakeDB(), geo)
    assert seen[-1][1] is None


@pytest.mark.parametrize("raw,term", [
    ("TP.HCM", "Hồ Chí Minh"), ("tphcm", "Hồ Chí Minh"), ("Thành phố Hồ Chí Minh", "Hồ Chí Minh"), ("Phường Linh Trung", "Linh Trung"),
    ("q7", "Quận 7"), ("Quận 7", "Quận 7"), ("p.1", "Phường 1"), ("Tỉnh Bình Dương", "Bình Dương"), ("Thủ Đức", "Thủ Đức"),
    ("Chợ Thủ Đức", "Chợ Thủ Đức"), ("Thị xã Dĩ An", "Dĩ An"),
])
def test_search_term(raw, term):
    assert search_term(raw) == term
