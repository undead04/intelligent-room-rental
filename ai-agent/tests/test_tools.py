import json
import sys
import types
import warnings

import httpx
import pytest

from skills import skills_discovery as sd
import tools.housing_tools as ht
from domain.enums import RoomType
from tools import http
from tests.test_location_service import CITIES, DISTRICTS, WARDS
from utils.text import norm_key


class Backend:
    """Backend giả: ghi lại mọi request; mô phỏng `search` chứa chuỗi con, không phân biệt dấu."""

    PLACES = {"uit": {"lat": 10.87, "lon": 106.8}, "đh bách khoa, hà nội": {"lat": 21.005, "lng": 105.843}}

    def __init__(self):
        self.calls: list[tuple[str, str, dict, dict | None]] = []
        self.rooms: list = []
        self.vs_status = 200
        self.listing: dict = {"id": "nhatot_1", "deposit": 3_000_000}
        self.stats = {"price_stats_general": {"total_listings": 120, "minimum_price_vnd": 1_800_000, "average_price_vnd": 3_200_000}}
        self.fail = False

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if self.fail:
            raise httpx.ConnectError("sập")
        params = dict(req.url.params)
        body = json.loads(req.content) if req.content else None
        self.calls.append((req.method, req.url.path, params, body))
        path = req.url.path
        for lvl, rows in (("cities", CITIES), ("districts", DISTRICTS), ("wards", WARDS)):
            if path.endswith(f"/locations/{lvl}"):
                out = [r for r in rows if norm_key(params.get("search", "")) in norm_key(r["name"])]
                if "city_id" in params:
                    out = [r for r in out if r.get("city_id") == int(params["city_id"])]
                if "district_id" in params:
                    out = [r for r in out if r.get("district_id") == int(params["district_id"])]
                return httpx.Response(200, json={"success": True, "data": out})
        if path.endswith("/geocode"):
            hit = self.PLACES.get(params.get("q", "").lower())
            return httpx.Response(200, json={"success": True, "data": hit}) if hit else httpx.Response(404, json={})
        if path.endswith("/listings/vector-search"):
            return httpx.Response(self.vs_status, json={"success": True, "data": self.rooms} if self.vs_status == 200 else {"message": "lỗi nội bộ"})
        if path.endswith("/listings/price-stats"):
            return httpx.Response(200, json=self.stats)
        if "/listings/" in path:
            return httpx.Response(404, json={}) if path.endswith("/missing") else httpx.Response(200, json={"success": True, "data": self.listing})
        return httpx.Response(404, json={})

    def paths(self) -> list[str]:
        return [c[1].split("/api/v1")[-1] for c in self.calls]


@pytest.fixture
def be():
    b = Backend()
    http.set_client(httpx.Client(transport=httpx.MockTransport(b), base_url="http://test/api/v1"))
    yield b
    http.set_client(None)


# ---------------- http ----------------
def test_unwrap_response_variants():
    u = http.unwrap_response
    assert u(httpx.Response(404, json={}))["status"] == 404
    assert u(httpx.Response(200, text="<html>lỗi</html>"))["error"].startswith("Phản hồi không phải JSON")
    assert u(httpx.Response(200, json={"success": False, "message": "sai"})) == {"ok": False, "error": "sai"}
    assert u(httpx.Response(200, json={"success": True, "data": [1]})) == {"ok": True, "data": [1]}
    assert u(httpx.Response(200, json=[1, 2])) == {"ok": True, "data": [1, 2]}
    r = u(httpx.Response(500, json={"message": "hỏng"}))
    assert r["ok"] is False and r["error"] == "hỏng" and r["status"] == 500


def test_request_never_raises_on_network_error(be):
    be.fail = True
    r = http.request("GET", "/x")
    assert r["ok"] is False and "Không thể kết nối" in r["error"]


def test_shared_client_is_reused_and_recreated_after_reset():
    http.set_client(None)
    a, b = http.get_client(), http.get_client()
    assert a is b
    http.set_client(None)
    assert http.get_client() is not a
    http.set_client(None)


def test_legacy_client_context_manager_does_not_close_shared_client(be):
    with ht._client() as c:
        assert c is http.get_client()
    assert not http.get_client().is_closed
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert ht.set_turn_query_context("x") is None and ht.clear_turn_query_context() is None
    assert any(issubclass(x.category, DeprecationWarning) for x in w)


# ---------------- hành chính / định vị ----------------
def test_admin_lookup_scopes_and_swallows_errors(be):
    assert [r["id"] for r in ht.admin_lookup("district", "Quận 7", city_id=79)] == [778]
    assert be.calls[-1][2] == {"search": "Quận 7", "city_id": "79"}
    assert ht.admin_lookup("ward", "Linh Trung", district_id=784)[0]["id"] == 1001
    be.fail = True
    assert ht.admin_lookup("city", "Hà Nội") == []


def test_geocode_point_success_key_variants_and_not_found(be):
    assert ht.geocode_point("UIT") == {"lat": 10.87, "lng": 106.8}
    assert ht.geocode_point("ĐH Bách Khoa, Hà Nội") == {"lat": 21.005, "lng": 105.843}           # backend trả 'lng' thay vì 'lon'
    assert ht.geocode_point("không có chỗ này") is None and ht.geocode_point("  ") is None


def test_geocode_point_404_triggers_llm_expansion_once(be, monkeypatch):
    seen = []
    monkeypatch.setattr(ht, "expand_location_with_llm", lambda q, h=None: seen.append((q, h)) or "UIT")
    assert ht.geocode_point("trường it", hint="TP.HCM") == {"lat": 10.87, "lng": 106.8}
    assert seen == [("trường it", "TP.HCM")]
    seen.clear()
    monkeypatch.setattr(ht, "expand_location_with_llm", lambda q, h=None: seen.append(1) or q)    # LLM không đổi gì -> không gọi lại vô tận
    assert ht.geocode_point("zzz") is None and seen == [1]


def test_geocode_tool_refuses_administrative_names_without_calling_geocode(be):
    out = json.loads(ht.geocode_location.invoke({"query": "Thủ Đức"}))
    assert out["ok"] is False and out["is_administrative"] and "get_location_hierarchy" in out["error"]
    assert "/geocode" not in be.paths()                                                          # quyết định bằng khớp tên chính xác, không LLM
    out = json.loads(ht.geocode_location.invoke({"query": "Phường 1"}))                           # trùng tên cũng là hành chính
    assert out["is_administrative"]
    assert json.loads(ht.geocode_location.invoke({"query": "Chợ Thủ Đức"}))["ok"] is False        # không phải hành chính, nhưng geocode không có
    assert "/geocode" in be.paths()


def test_geocode_tool_place_success_and_errors(be):
    assert json.loads(ht.geocode_location.invoke({"query": "UIT"})) == {"ok": True, "data": {"lat": 10.87, "lon": 106.8}}
    assert "Không tìm thấy toạ độ" in json.loads(ht.geocode_location.invoke({"query": "xyz"}))["error"]
    assert json.loads(ht.geocode_location.invoke({"query": "  "}))["ok"] is False


def _h(**kw):
    return json.loads(ht.get_location_hierarchy.invoke(kw))


def test_hierarchy_exact_first_and_levels(be):
    r = _h(district_name="Quận 1")
    assert r["level"] == "district" and r["match"] == "exact" and [x["id"] for x in r["data"]] == [760]     # 'Quận 10' không lọt vào
    r = _h(ward_name="Linh Trung", district_name="Thủ Đức", city_name="TP.HCM")
    assert r["level"] == "ward" and [x["id"] for x in r["data"]] == [1001]
    r = _h(ward_name="Phường 1")
    assert {x["id"] for x in r["data"]} == {2001, 2002}                                             # trùng tên: trả cả hai để agent hỏi lại
    r = _h(ward_name="Phường 1", district_name="Quận 7")
    assert [x["id"] for x in r["data"]] == [2002]
    r = _h(city_name="Hà Nội")
    assert r["level"] == "city" and r["data"][0]["id"] == 1


def test_hierarchy_partial_match_is_labelled_and_city_falls_back_to_district(be):
    r = _h(ward_name="Linh")
    assert r["match"] == "partial" and len(r["data"]) == 2
    r = _h(city_name="Dĩ An")                                                                       # nhập nhầm vào city_name nhưng nằm ở bảng quận/huyện
    assert r["level"] == "district" and r["data"][0]["id"] == 724 and "district_id" in r["note"]


def test_hierarchy_not_found_messages(be):
    assert "chưa có dữ liệu" in _h(city_name="Quảng Ngãi")["message"]
    assert "chưa có dữ liệu" in _h(district_name="Không Có")["message"]
    assert "chưa có dữ liệu" in _h(ward_name="Không Có")["message"]


# ---------------- tìm phòng ----------------
def test_search_rooms_api_builds_body_and_normalizes(be):
    be.rooms = [{"listing": {"id": "x"}}]
    r = ht.search_rooms_api({"query": "phòng", "lat": 10.87, "lng": 106.8, "city_id": 79, "district_id": 5, "room_type": RoomType.STUDIO,
                             "max_price": 3_000_000, "amenities": ["ml", "máy lạnh", "gác", "xyz"], "weights": {"price": 0.5}, "limit": 999})
    assert r == {"ok": True, "data": [{"listing": {"id": "x"}}]}
    body = be.calls[-1][3]
    assert be.calls[-1][0] == "POST" and body == {"query": "phòng", "limit": 20, "offset": 0, "lat": 10.87, "lng": 106.8, "room_type": "STUDIO",
                                                  "max_price": 3_000_000, "amenities": ["aircon", "mezzanine"], "weights": {"price": 0.5}}
    assert "city_id" not in body and "district_id" not in body                                       # có toạ độ -> bỏ ID hành chính


def test_search_rooms_api_admin_ids_when_no_coordinates_and_limit_floor(be):
    ht.search_rooms_api({"query": "q", "city_id": 79, "district_id": 5, "ward_id": 7, "limit": 0})
    body = be.calls[-1][3]
    assert (body["city_id"], body["district_id"], body["ward_id"], body["limit"]) == (79, 5, 7, 5)       # limit=0 -> mặc định 5
    assert "lat" not in body and "amenities" not in body and "weights" not in body


def test_search_rooms_empty_results_carry_human_in_the_loop_hints(be):
    r = ht.search_rooms_api({"query": "q", "max_price": 3_000_000, "ward_id": 7, "amenities": ["ml"], "min_area": 25})
    assert r["need_human_in_the_loop"] and r["data"] == []
    sug = " | ".join(r["context_suggestions"])
    assert "3.45 triệu/tháng" in sug and "toàn Quận/Huyện" in sug and "aircon" in sug and "25m²" in sug
    assert "Human-in-the-Loop" in r["message"]


def test_search_rooms_api_backend_error_and_tool_wrapper(be):
    be.vs_status = 500
    r = ht.search_rooms_api({"query": "q"})
    assert r["ok"] is False and r["error"] == "lỗi nội bộ"
    be.vs_status, be.rooms = 200, [{"listing": {"id": "y"}}]
    out = json.loads(ht.search_rooms.invoke({"query": "q", "max_price": 3_000_000, "amenities": ["ml"]}))
    assert out["ok"] and out["data"][0]["listing"]["id"] == "y" and be.calls[-1][3]["amenities"] == ["aircon"]


# ---------------- chi tiết / giá thị trường ----------------
def test_listing_detail_validates_id_before_any_request(be):
    for bad in ("../admin", "a/b", "x" * 65, "", "id có dấu cách", "a?b=1"):
        assert json.loads(ht.get_listing_detail.invoke({"listing_id": bad}))["ok"] is False
    assert be.calls == []
    assert json.loads(ht.get_listing_detail.invoke({"listing_id": "nhatot_1"}))["data"]["deposit"] == 3_000_000
    assert "Không tìm thấy tin đăng" in json.loads(ht.get_listing_detail.invoke({"listing_id": "missing"}))["error"]


def test_price_stats_never_guess_city(be):
    assert json.loads(ht.get_market_price_stats.invoke({}))["ok"] is False and be.calls == []
    assert ht.fetch_price_stats(None) is None and be.calls == []
    g = ht.fetch_price_stats(79, district_id=5, room_type_id=2)
    assert g["minimum_price_vnd"] == 1_800_000 and be.calls[-1][2] == {"city_id": "79", "district_id": "5", "room_type_id": "2"}
    be.fail = True
    assert ht.fetch_price_stats(79) is None
    import safety.grounding as grounding
    be.fail = False
    assert grounding.backend_market_fetcher(city_id=79, district_id=None, room_type_id=None)["average_price_vnd"] == 3_200_000


# ---------------- kỹ năng ----------------
@pytest.fixture
def skill_dir(tmp_path, monkeypatch):
    d = tmp_path / "skills" / "rental-contract-advisor"
    (d / "references").mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: Hợp đồng\ndescription: Tư vấn hợp đồng\n---\nNội dung chính", encoding="utf-8")
    (d / "references" / "coc.md").write_text("Quy định về cọc", encoding="utf-8")
    monkeypatch.setattr(sd, "SKILL_DIRS", [tmp_path / "skills"])
    sd.clear_cache()
    yield
    sd.clear_cache()


def test_consult_skill_reads_by_slug_only(skill_dir):
    r = ht.consult_skill("rental-contract-advisor", "q")
    assert r["ok"] and "Nội dung chính" in r["instructions"] and r["references"] == {"coc.md": "Quy định về cọc"} and r["skill_name"] == "rental-contract-advisor"
    for bad in ("../../etc/passwd", "nope", "", "Rental-Contract-Advisor/../x"):
        assert ht.consult_skill(bad)["ok"] is False
    assert ht.consult_skill("RENTAL-CONTRACT-ADVISOR")["ok"]                                         # slug không phân biệt hoa/thường


def test_skill_tools_do_not_leak_server_paths(skill_dir):
    listed = json.loads(ht.list_housing_skills.invoke({}))
    assert listed["skills"] == [{"slug": "rental-contract-advisor", "name": "Hợp đồng", "description": "Tư vấn hợp đồng"}] and "path" not in json.dumps(listed)
    assert "Nội dung chính" in json.loads(ht.consult_housing_skill.invoke({"skill_name": "rental-contract-advisor"}))["instructions"]


# ---------------- tích hợp: graph chạy qua hàm tool thật + backend giả ----------------
def _deps(llm):
    from graph import Deps
    from core.session_store import SessionStore
    return Deps(sessions=SessionStore(), get_llm=lambda role: llm, base_prompt="BASE", decision_system_prompt="DECISION", search_rooms=ht.search_rooms_api,
                geocode=ht.geocode_point, admin_lookup=ht.admin_lookup, consult_skill=ht.consult_skill, skills=sd.discover_housing_skills)


def _raw(i, price):
    return {"listing": {"id": f"nhatot_{i}", "title": f"Phòng {i}", "price_vnd": price, "area_m2": 22, "address_raw": f"{i} Đường X", "lat": 10.871, "lng": 106.801},
            "match_score": 0.9 - i / 100, "explain_match": {"top_factors": [{"name": "price"}]}}


def test_graph_end_to_end_through_real_tool_functions(be):
    from graph import build_housing_graph, run_turn
    from tests.e2e_helpers import GOOD_ADVICE, FakeLLM, nlu
    be.rooms = [_raw(1, 2_400_000), _raw(2, 2_800_000)]
    llm = FakeLLM().on("TurnAnalysis", nlu(location_text="UIT", location_kind="place", max_price=3_500_000, amenities_add=["ml"]),
                       nlu(location_text="Dĩ An", location_kind="admin")).on("Advice", GOOD_ADVICE)
    g = build_housing_graph(_deps(llm))
    r = run_turn(g, "tìm phòng gần UIT dưới 3tr5 có máy lạnh", session_id="s")
    body = [c for c in be.calls if c[0] == "POST"][-1][3]
    assert [x.id for x in r.rooms] == ["nhatot_1", "nhatot_2"] and r.grounding_report.is_grounded
    assert body["lat"] == 10.87 and body["lng"] == 106.8 and body["amenities"] == ["aircon"] and "district_id" not in body
    r2 = run_turn(g, "đổi sang Dĩ An", session_id="s2")                                               # hành chính: tra ID qua backend giả, không geocode
    body2 = [c for c in be.calls if c[0] == "POST"][-1][3]
    assert (body2["city_id"], body2["district_id"]) == (74, 724) and "lat" not in body2 and len(r2.rooms) == 2


def test_default_deps_wires_core_functions_and_accepts_a_persistent_store(tmp_path, monkeypatch):
    stub = types.ModuleType("prompts")
    stub.BASE_PROMPT, stub.build_decision_prompt, stub.build_advice_prompt = "BASE", lambda: "RULES", lambda: "ADVICE"
    monkeypatch.setitem(sys.modules, "prompts", stub)
    from graph import default_deps
    from core.session_store import PersistentSessionStore
    store = PersistentSessionStore(str(tmp_path / "s.db"))
    d = default_deps(sessions=store)
    assert d.search_rooms is ht.search_rooms_api and d.geocode is ht.geocode_point and d.admin_lookup is ht.admin_lookup and d.consult_skill is ht.consult_skill
    assert d.sessions is store and d.decision_system_prompt.startswith("RULES") and "Quy tắc bổ sung" in d.decision_system_prompt and callable(d.market_fetcher)
    assert d.advice_system_prompt == "ADVICE"
