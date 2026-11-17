"""Kiểm thử độc lập (Black-Box, 4 nhóm) cho kỹ năng tra cứu mặt bằng giá: market-price-advisor."""

from __future__ import annotations

import json
from typing import Any, Optional

import httpx
import pytest

from core.session_store import PersistentSessionStore
from domain.schemas import UserPreferenceState
from graph import Deps, build_housing_graph, run_turn
from intelligence.nlu import PreferencePatch, TurnAnalysis, analyze_turn
from skills import skills_discovery as sd
from tests.e2e_helpers import FakeLLM, nlu
from tests.helpers import FakeModel
from tools import housing_tools as ht
from tools import http
from tools.location_service import admin_key
from tools.registry import ADVISORY_TOOLS
from utils.text import norm_key


class _LocalAdminDB:
    def __init__(self, cities=None, districts=None, wards=None):
        self.cities = cities or [{"id": 79, "name": "Hồ Chí Minh"}]
        self.districts = districts or [
            {"id": 764, "name": "Gò Vấp", "city_id": 79},
            {"id": 778, "name": "Quận 7", "city_id": 79},
        ]
        self.wards = wards or []

    def __call__(self, level: str, name: str, city_id=None, district_id=None):
        rows = {"city": self.cities, "district": self.districts, "ward": self.wards}[level]
        out = [r for r in rows if not name or norm_key(name) in norm_key(r["name"]) or admin_key(name) in norm_key(r["name"])]
        if city_id is not None and level == "district":
            out = [r for r in out if r["city_id"] == city_id]
        if district_id is not None and level == "ward":
            out = [r for r in out if r["district_id"] == district_id]
        return out


def _mock_backend_transport() -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path.endswith("/locations/cities"):
            q = (req.url.params.get("search") or "").lower()
            if "hồ chí minh" in q or "ho chi minh" in q:
                return httpx.Response(200, json={"success": True, "data": [{"id": 79, "name": "Hồ Chí Minh"}]})
            return httpx.Response(200, json={"success": True, "data": []})
        if path.endswith("/locations/districts"):
            q = (req.url.params.get("search") or "").lower()
            cid = req.url.params.get("city_id")
            if "gò vấp" in q and cid == "79":
                return httpx.Response(200, json={"success": True, "data": [{"id": 764, "name": "Gò Vấp", "city_id": 79}]})
            if "liên chiểu" in q:
                return httpx.Response(200, json={"success": True, "data": []})
            return httpx.Response(200, json={"success": True, "data": []})
        if path.endswith("/locations/wards"):
            return httpx.Response(200, json={"success": True, "data": []})
        if path.endswith("/listings/price-stats"):
            cid = req.url.params.get("city_id")
            did = req.url.params.get("district_id")
            rt_id = req.url.params.get("room_type_id")
            if cid == "79" and did == "764":
                avg = 4_200_000.0 if rt_id == "2" else 3_650_000.0
                return httpx.Response(
                    200,
                    json={
                        "success": True,
                        "data": {
                            "price_stats_general": {
                                "total_listings": 142,
                                "average_price_vnd": avg,
                                "minimum_price_vnd": 2_100_000.0,
                                "maximum_price_vnd": 6_500_000.0,
                                "price_fluctuation_month": 2.5,
                                "area_hotspot": "Phường 5",
                            },
                            "price_stats_by_area": [
                                {"area_id": 26881, "area": "Phường 5", "total_listings": 40, "average_price_vnd": 3_500_000.0},
                                {"area_id": 26890, "area": "Phường 10", "total_listings": 35, "average_price_vnd": 3_900_000.0},
                            ],
                        },
                    },
                )
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "price_stats_general": {"total_listings": 0, "average_price_vnd": None, "minimum_price_vnd": None, "maximum_price_vnd": None},
                        "price_stats_by_area": [],
                    },
                },
            )
        return httpx.Response(404, json={"success": False, "message": "not found"})

    return httpx.MockTransport(handler)


class _MarketHarness:
    def __init__(
        self,
        llm: Optional[FakeLLM],
        *,
        db: Optional[_LocalAdminDB] = None,
        stats_payload: Optional[dict[str, Any]] = None,
        sessions: Any = None,
    ):
        from core.session_store import SessionStore

        self.llm = llm
        self.sessions = sessions if sessions is not None else SessionStore()
        self.db = db or _LocalAdminDB()
        self.search_calls: list[dict[str, Any]] = []
        self.stats_calls: list[tuple[int, Optional[int], Optional[int]]] = []
        default_stats = {
            "price_stats_general": {
                "total_listings": 85,
                "average_price_vnd": 3_600_000.0,
                "minimum_price_vnd": 2_000_000.0,
                "maximum_price_vnd": 6_200_000.0,
                "price_fluctuation_month": 1.5,
                "area_hotspot": "Phường 5",
            },
            "price_stats_by_area": [
                {"area_id": 1, "area": "Phường 5", "total_listings": 30, "average_price_vnd": 3_400_000.0},
            ],
        }
        self.stats_payload = default_stats if stats_payload is None else stats_payload

        def search(args: dict[str, Any]) -> dict[str, Any]:
            self.search_calls.append(args)
            return {"ok": True, "data": []}

        def full_stats(city_id: int, district_id: Optional[int] = None, room_type_id: Optional[int] = None):
            self.stats_calls.append((city_id, district_id, room_type_id))
            return self.stats_payload

        sd.clear_cache()
        self.deps = Deps(
            sessions=self.sessions,
            get_llm=lambda temperature=None: self.llm,
            base_prompt="BASE",
            decision_system_prompt="DECISION",
            search_rooms=search,
            geocode=lambda q, h: None,
            admin_lookup=self.db,
            consult_skill=ht.consult_skill,
            skills=sd.discover_housing_skills,
            full_price_stats=full_stats,
        )
        self.graph = build_housing_graph(self.deps)

    def turn(self, text: str, session_id: str = "s1"):
        return run_turn(self.graph, text, session_id=session_id)


# ===========================================================================
# Nhóm 1: Happy Path
# ===========================================================================
def test_market_price_skill_discovered_and_tool_registered():
    sd.clear_cache()
    skills = sd.discover_housing_skills(force_reload=True)
    assert "market-price-advisor" in skills
    assert "rental-contract-advisor" in skills
    s = skills["market-price-advisor"]
    assert s.follow_ups and len(s.triggers) >= 3
    tool_names = {t.name for t in ADVISORY_TOOLS}
    assert {"list_housing_skills", "consult_housing_skill", "get_market_price_stats"} <= tool_names


def test_get_market_price_stats_tool_end_to_end_via_http_mock():
    http.set_client(httpx.Client(transport=_mock_backend_transport(), base_url="http://test/api/v1"))
    try:
        res_all = json.loads(ht.get_market_price_stats.invoke({"location_text": "Gò Vấp"}))
        assert res_all["ok"] is True
        assert res_all["city_id"] == 79 and res_all["district_id"] == 764
        assert res_all["average_price_vnd"] == 3_650_000.0
        assert res_all["total_listings"] == 142
        assert len(res_all["by_area"]) == 2

        res_studio = json.loads(ht.get_market_price_stats.invoke({"location_text": "Gò Vấp", "room_type": "STUDIO"}))
        assert res_studio["ok"] is True
        assert res_studio["average_price_vnd"] == 4_200_000.0
        assert res_studio["room_type"] == "căn hộ studio"
    finally:
        http.set_client(None)


def test_graph_market_price_happy_path_uses_real_stats_and_no_room_search():
    analysis = TurnAnalysis(
        intent="skill_advice",
        skill_slug="market-price-advisor",
        patch=PreferencePatch(location_text="Gò Vấp", location_kind="admin"),
    )
    llm_reply = (
        "Giá phòng trọ trung bình tại Gò Vấp hiện vào khoảng 3.6 triệu/tháng dựa trên 85 tin đăng thực tế, "
        "dao động từ 2 triệu đến 6.2 triệu/tháng."
    )
    llm = FakeLLM().on("TurnAnalysis", analysis).on("text", llm_reply)
    h = _MarketHarness(llm)

    resp = h.turn("giá phòng trọ trung bình ở Gò Vấp")

    assert h.search_calls == []
    assert h.stats_calls == [(79, 764, None)]
    assert resp.rooms == []
    assert resp.searched is False
    assert "3.6 triệu" in resp.text_reply
    assert len(resp.follow_up_questions) >= 1

    text_calls = [m for n, m in llm.calls if n == "text"]
    assert len(text_calls) == 1
    human_msg = text_calls[0][-1][1]
    assert "<market_stats>" in human_msg and "85 tin" in human_msg and "3.6 triệu" in human_msg


def test_graph_market_price_falls_back_deterministically_when_llm_unavailable():
    analysis = TurnAnalysis(
        intent="skill_advice",
        skill_slug="market-price-advisor",
        patch=PreferencePatch(location_text="Gò Vấp", location_kind="admin"),
    )
    # LLM phân tích NLU chạy xong rồi model chính trả về lỗi khi sinh văn bản
    llm = FakeLLM().on("TurnAnalysis", analysis).on("text", RuntimeError("LLM overloaded"))
    h = _MarketHarness(llm)

    resp = h.turn("giá phòng trọ trung bình ở Gò Vấp")

    assert h.stats_calls == [(79, 764, None)]
    assert "3.6 triệu" in resp.text_reply
    assert "85 tin" in resp.text_reply


# ===========================================================================
# Nhóm 2: Boundary & Edge Cases
# ===========================================================================
def test_lookup_market_price_stats_edge_cases():
    db = _LocalAdminDB(
        cities=[{"id": 79, "name": "Hồ Chí Minh"}, {"id": 80, "name": "Long An"}],
        districts=[
            {"id": 1, "name": "Châu Thành", "city_id": 79},
            {"id": 2, "name": "Châu Thành", "city_id": 80},
        ],
    )
    for bad_loc in ("", "   ", "\n\t"):
        r = ht.lookup_market_price_stats(bad_loc, admin_lookup_fn=db)
        assert r["ok"] is False and r["error"] == "MISSING_LOCATION"

    r_bad_rt = ht.lookup_market_price_stats("Gò Vấp", room_type="INVALID_TYPE", admin_lookup_fn=db)
    assert r_bad_rt["ok"] is False and r_bad_rt["error"] == "INVALID_ROOM_TYPE"

    r_ambig = ht.lookup_market_price_stats("Châu Thành", admin_lookup_fn=db)
    assert r_ambig["ok"] is False and r_ambig["error"] == "AMBIGUOUS_LOCATION"
    assert len(r_ambig["candidates"]) == 2

    r_missing = ht.lookup_market_price_stats("Quận Không Tồn Tại XYZ", location_kind="admin", admin_lookup_fn=db)
    assert r_missing["ok"] is False and r_missing["error"] == "LOCATION_NOT_FOUND"


def test_graph_market_price_missing_location_asks_clarification_without_guessing_city():
    analysis = TurnAnalysis(intent="skill_advice", skill_slug="market-price-advisor")
    llm = FakeLLM().on("TurnAnalysis", analysis)
    h = _MarketHarness(llm)

    resp = h.turn("giá phòng trọ trung bình khoảng bao nhiêu?")

    assert h.stats_calls == []
    assert resp.need_clarification is True
    assert "quận/huyện" in resp.text_reply.lower() or "tỉnh/thành" in resp.text_reply.lower()


def test_graph_market_price_zero_listings_returns_honest_empty_message():
    analysis = TurnAnalysis(
        intent="skill_advice",
        skill_slug="market-price-advisor",
        patch=PreferencePatch(location_text="Gò Vấp", location_kind="admin"),
    )
    empty_stats = {
        "price_stats_general": {"total_listings": 0, "average_price_vnd": None, "minimum_price_vnd": None, "maximum_price_vnd": None},
        "price_stats_by_area": [],
    }
    llm = FakeLLM().on("TurnAnalysis", analysis)
    h = _MarketHarness(llm, stats_payload=empty_stats)

    resp = h.turn("giá phòng trọ trung bình ở Gò Vấp")

    assert h.stats_calls == [(79, 764, None)]
    assert "chưa có tin đăng" in resp.text_reply.lower()


def test_nlu_still_flags_true_compound_search_and_market_price_query():
    skills = sd.discover_housing_skills(force_reload=True)
    model = FakeModel(
        TurnAnalysis(
            intent="skill_advice",
            skill_slug="market-price-advisor",
            patch=PreferencePatch(location_text="Gò Vấp", max_price=3_000_000),
        )
    )
    res = analyze_turn(model, "tìm phòng ở Gò Vấp dưới 3 triệu và cho biết giá trung bình ở đó", UserPreferenceState(), skills=skills)
    assert res is not None and res.is_multi_intent is True


# ===========================================================================
# Nhóm 3: State Mutation & Zero Leakage
# ===========================================================================
def test_market_price_query_does_not_mutate_existing_search_preferences_and_preserves_kv_cache():
    t1 = nlu("skill_advice", location_text="Gò Vấp", location_kind="admin").model_copy(update={"skill_slug": "market-price-advisor"})
    t2 = nlu("skill_advice", location_text="Quận 7", location_kind="admin").model_copy(update={"skill_slug": "market-price-advisor"})
    reply_ok = "Mặt bằng giá tại khu vực này trung bình khoảng 3.6 triệu/tháng dựa trên dữ liệu hệ thống."
    llm = FakeLLM().on("TurnAnalysis", t1, t2).on("text", reply_ok, reply_ok)
    h = _MarketHarness(llm)

    # Đặt sẵn tiêu chí tìm phòng trước đó ở Quận 7, tối đa 3 triệu
    h.sessions.get_or_create_session("s1").preferences = UserPreferenceState(
        location_text="Quận 7",
        location_kind="admin",
        city_id=79,
        district_id=778,
        max_price=3_000_000,
    )

    r1 = h.turn("giá phòng trọ trung bình ở Gò Vấp")
    assert r1.current_preferences.location_text == "Quận 7"
    assert r1.current_preferences.max_price == 3_000_000
    assert h.stats_calls[-1] == (79, 764, None)

    h.turn("còn ở Quận 7 thì giá trung bình bao nhiêu?")
    assert h.stats_calls[-1] == (79, 778, None)

    text_calls = [m for n, m in llm.calls if n == "text"]
    assert len(text_calls) == 2
    assert text_calls[0][0] == text_calls[1][0] and text_calls[0][0][0] == "system"


def test_contextual_anaphora_uses_session_location_without_mutating_state():
    t1 = nlu("skill_advice").model_copy(update={"skill_slug": "market-price-advisor"})
    reply_ok = "Mặt bằng giá tại Gò Vấp trung bình khoảng 3.6 triệu/tháng từ dữ liệu thực tế."
    llm = FakeLLM().on("TurnAnalysis", t1).on("text", reply_ok)
    h = _MarketHarness(llm)
    h.sessions.get_or_create_session("s1").preferences = UserPreferenceState(
        location_text="Gò Vấp",
        location_kind="admin",
        city_id=79,
        district_id=764,
        max_price=3_200_000,
    )

    resp = h.turn("vậy giá trung bình ở đây khoảng bao nhiêu?")
    assert h.stats_calls == [(79, 764, None)]
    assert resp.current_preferences.max_price == 3_200_000


# ===========================================================================
# Nhóm 4: Persistence & Integration Consistency
# ===========================================================================
def test_persistent_session_and_trace_consistency(tmp_path):
    db_path = str(tmp_path / "sessions.db")
    store1 = PersistentSessionStore(db_path)
    s1 = store1.get_or_create_session("persist-1")
    s1.preferences = UserPreferenceState(location_text="Quận 7", location_kind="admin", city_id=79, district_id=778, max_price=4_000_000)
    store1.commit_turn(s1, "tìm phòng Quận 7 dưới 4tr", "OK", [])

    analysis = TurnAnalysis(
        intent="skill_advice",
        skill_slug="market-price-advisor",
        patch=PreferencePatch(location_text="Gò Vấp", location_kind="admin"),
    )
    llm = FakeLLM().on("TurnAnalysis", analysis).on("text", "Giá phòng trọ trung bình tại Gò Vấp khoảng 3.6 triệu/tháng.")
    h = _MarketHarness(llm, sessions=store1)
    resp = h.turn("giá phòng trọ trung bình ở Gò Vấp", session_id="persist-1")

    # Kiểm tra TraceStore ghi nhận đủ cả consult_housing_skill và get_market_price_stats
    finished_tools = [e.get("tool") for e in resp.trace_events if e.get("type") == "tool_finished"]
    assert "consult_housing_skill" in finished_tools
    assert "get_market_price_stats" in finished_tools

    # Nạp lại từ SQLite trên đĩa: tiêu chí tìm phòng Quận 7 không bị hỏng/ghi đè
    store2 = PersistentSessionStore(db_path)
    reloaded = store2.get_or_create_session("persist-1")
    assert reloaded.preferences.location_text == "Quận 7"
    assert reloaded.preferences.max_price == 4_000_000
