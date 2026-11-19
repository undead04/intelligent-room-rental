"""Black-box tests cho Phân trang 10 trang (50 phòng), chuyển trang qua chat & tra cứu rank toàn cục."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api import routes as api_routes
from core.config import DEFAULT_PAGE_SIZE, MAX_PAGED_ROOMS, MAX_PAGINATION_PAGES
from core.session_store import PersistentSessionStore
from domain.schemas import RoomItem
from intelligence.nlu import Priorities
from tests.e2e_helpers import GOOD_ADVICE, FakeAgent, FakeLLM, Harness, agent_reply, nlu, raw_room


def _many_rooms(count: int) -> list[dict]:
    return [raw_room(i, price=2_500_000 + i * 20_000, area=20 + (i % 8)) for i in range(1, count + 1)]


def test_retrieval_prefetches_up_to_50_rooms_and_caps_at_10_pages():
    llm = FakeLLM().on(
        "TurnAnalysis",
        nlu("new_search", location_text="UIT", location_kind="place", max_price=4_500_000),
    ).on("Advice", GOOD_ADVICE)

    # Giả lập Backend trả 50 phòng (thậm chí >50 nếu raw có 55): vẫn giới hạn 10 trang (50 phòng)
    h = Harness(llm, _many_rooms(55))
    r = h.turn("tìm phòng gần UIT dưới 4tr5")

    assert h.search_calls[0]["limit"] == 50
    assert len(r.rooms) == 5
    assert [rm.rank for rm in r.rooms] == [1, 2, 3, 4, 5]
    assert r.page == 1
    assert r.page_size == DEFAULT_PAGE_SIZE
    assert r.total_rooms == MAX_PAGED_ROOMS
    assert r.total_pages == MAX_PAGINATION_PAGES
    assert len(h.session.paged_rooms) == MAX_PAGED_ROOMS


def test_chat_page_navigation_next_specific_prev_first_last_and_bounds():
    llm = (
        FakeLLM()
        .on(
            "TurnAnalysis",
            nlu("new_search", location_text="UIT", location_kind="place", max_price=4_500_000),
            # Lượt 2..7: NLU trả quyết định chuyển trang có cấu trúc
            nlu("refine_search").model_copy(update={"page_action": "next"}),
            nlu("refine_search").model_copy(update={"page_action": "goto", "target_page": 4}),
            nlu("refine_search").model_copy(update={"page_action": "prev"}),
            nlu("refine_search").model_copy(update={"page_action": "last"}),
            nlu("refine_search").model_copy(update={"page_action": "next"}),
            nlu("refine_search").model_copy(update={"page_action": "first"}),
        )
        .on("Advice", GOOD_ADVICE)
    )
    h = Harness(llm, _many_rooms(22))  # 22 phòng -> 5 trang (trang 5 có 2 phòng)

    r1 = h.turn("tìm phòng gần UIT dưới 4tr5")
    assert len(h.search_calls) == 1
    assert r1.page == 1 and r1.total_pages == 5 and r1.total_rooms == 22

    # 1. "cần những phòng khác" -> tự nhảy sang Trang 2 theo offset=5 (0 gọi lại search_calls!)
    r2 = h.turn("cần những phòng khác")
    assert len(h.search_calls) == 1
    assert r2.page == 2 and r2.total_pages == 5 and [rm.rank for rm in r2.rooms] == [6, 7, 8, 9, 10]
    assert "Phòng số 6" in r2.text_reply and "Top 7" in r2.text_reply

    # 2. Đích danh "qua trang 4 đi" -> Trang 4
    r4 = h.turn("qua trang 4 đi")
    assert len(h.search_calls) == 1
    assert r4.page == 4 and [rm.rank for rm in r4.rooms] == [16, 17, 18, 19, 20]

    # 3. "trang trước" -> Trang 3
    r3 = h.turn("xem trang trước")
    assert r3.page == 3 and [rm.rank for rm in r3.rooms] == [11, 12, 13, 14, 15]

    # 4. "trang cuối" -> Trang 5 (2 phòng: rank 21, 22)
    r5 = h.turn("xem trang cuối")
    assert r5.page == 5 and [rm.rank for rm in r5.rooms] == [21, 22]

    # 5. Đã ở trang cuối mà vẫn đòi "cần những phòng khác" -> báo hết, giữ nguyên trang 5
    r_over = h.turn("cần những phòng khác")
    assert r_over.page == 5 and [rm.rank for rm in r_over.rooms] == [21, 22]
    assert "22 phòng" in r_over.text_reply and "5 trang" in r_over.text_reply

    # 6. "trang đầu" -> Trang 1
    r_first = h.turn("về trang đầu")
    assert r_first.page == 1 and [rm.rank for rm in r_first.rooms] == [1, 2, 3, 4, 5]


def test_chat_navigation_does_not_hijack_new_criteria_search():
    """Khi user nói 'cho những phòng khác rẻ hơn', priorities.price='high' -> PHẢI chạy search mới."""
    llm = (
        FakeLLM()
        .on(
            "TurnAnalysis",
            nlu("new_search", location_text="UIT", location_kind="place", max_price=4_500_000),
            nlu("refine_search", priorities=Priorities(price="high")),
        )
        .on("Advice", GOOD_ADVICE)
    )
    h = Harness(llm, _many_rooms(20))
    h.turn("tìm phòng gần UIT dưới 4tr5")
    assert len(h.search_calls) == 1

    r2 = h.turn("cho những phòng khác rẻ hơn")
    assert len(h.search_calls) == 2
    assert r2.page == 1


def test_page_3_global_rank_followup_top1_vs_top12_vs_current_page_first(monkeypatch):
    """Đứng ở Trang 3 (Top 11..15):
    - Hỏi 'phòng top 1' -> trả đúng Top 1 thật (nhatot_1)
    - Hỏi 'phòng số 12' -> trả đúng Top 12 (nhatot_12)
    - Hỏi 'phòng đầu tiên trang này' -> trả đúng Top 11 (nhatot_11)
    """
    from graph.nodes import decision as decision_mod

    detail_calls: list[str] = []

    def fake_detail(listing_id: str) -> dict:
        detail_calls.append(listing_id)
        return {"ok": True, "data": {"id": listing_id, "title": f"Phòng {listing_id}", "description": "Chi tiết phòng."}}

    monkeypatch.setattr(decision_mod, "fetch_listing_detail", fake_detail)

    agent = FakeAgent(agent_reply("Thông tin chi tiết phòng bạn hỏi đây nhé."))
    llm = (
        FakeLLM()
        .on(
            "TurnAnalysis",
            nlu("new_search", location_text="UIT", location_kind="place", max_price=4_500_000),
            nlu("refine_search").model_copy(update={"page_action": "goto", "target_page": 3}),  # qua trang 3
            nlu("room_followup").model_copy(update={"referenced_room_rank": 1}),   # hỏi top 1
            nlu("room_followup").model_copy(update={"referenced_room_rank": 12}),  # hỏi top 12
            nlu("room_followup").model_copy(update={"referenced_room_rank": None, "followup_current_page_first": True}),  # hỏi phòng đầu trang này
        )
        .on("Advice", GOOD_ADVICE)
    )
    h = Harness(llm, _many_rooms(20), agent=agent)
    h.turn("tìm phòng gần UIT dưới 4tr5")
    r_p3 = h.turn("qua trang 3")
    assert r_p3.page == 3 and [rm.rank for rm in r_p3.rooms] == [11, 12, 13, 14, 15]

    # 1. Hỏi 'phòng top 1' khi đang đứng ở Trang 3 -> phải fetch detail của nhatot_1!
    h.turn("phòng top 1 tiền cọc bao nhiêu?")
    assert detail_calls[-1] == "nhatot_1"

    # 2. Hỏi 'phòng số 12' khi đang đứng ở Trang 3 -> phải fetch detail của nhatot_12!
    h.turn("phòng số 12 điện nước sao?")
    assert detail_calls[-1] == "nhatot_12"

    # 3. Hỏi 'phòng đầu tiên trang này' -> phải fetch detail của nhatot_11!
    h.turn("phòng đầu tiên trang này có nuôi pet không?")
    assert detail_calls[-1] == "nhatot_11"


def test_session_rooms_rest_endpoint_and_sqlite_persistence(tmp_path, monkeypatch):
    db_path = tmp_path / "sessions.db"
    store = PersistentSessionStore(db_path)
    monkeypatch.setattr(api_routes, "SESSION_STORE", store)

    sess = store.get_or_create_session("sess-page-test")
    rooms_25 = [RoomItem(id=f"r_{i}", rank=i, rankText=f"Top {i}", title=f"Phòng {i}", price="3 triệu/tháng", priceNum=3_000_000) for i in range(1, 26)]
    store.commit_turn(sess, "tìm phòng", "đã tìm", rooms_25[:5], searched=True, paged_rooms=rooms_25)

    client = TestClient(api_routes.app)
    resp = client.get("/api/v1/session/sess-page-test/rooms?page=4&page_size=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 4
    assert body["total_rooms"] == 25
    assert body["total_pages"] == 5
    assert [r["id"] for r in body["rooms"]] == ["r_16", "r_17", "r_18", "r_19", "r_20"]

    # Reload SQLite bằng store mới -> current_page & paged_rooms vẫn còn nguyên
    store_reloaded = PersistentSessionStore(db_path)
    reloaded = store_reloaded.get_or_create_session("sess-page-test")
    assert reloaded.current_page == 4
    assert len(reloaded.paged_rooms) == 25
    assert [r.id for r in reloaded.last_rooms] == ["r_16", "r_17", "r_18", "r_19", "r_20"]


def test_followup_surface_info_and_compare_skip_get_listing_detail(monkeypatch):
    """Nhóm 1 (Happy Path): Hỏi giá, diện tích, địa chỉ hoặc so sánh các phòng -> dùng thẳng rooms, 0 gọi get_listing_detail."""
    from graph.nodes import decision as decision_mod

    detail_calls: list[str] = []
    monkeypatch.setattr(
        decision_mod,
        "fetch_listing_detail",
        lambda lid: detail_calls.append(lid) or {"ok": True, "data": {"id": lid}},
    )

    agent = FakeAgent(
        agent_reply("Phòng Top 1 có giá thuê 2.52 triệu/tháng tại 1 Đường X, Dĩ An."),
        agent_reply("Phòng Top 2 có diện tích 22 m², giá 2.54 triệu/tháng."),
        agent_reply("So sánh nhanh: Top 1 rẻ hơn với giá 2.52 triệu/tháng (21 m²), còn Top 2 rộng hơn với 22 m² (2.54 triệu/tháng)."),
    )
    llm = (
        FakeLLM()
        .on(
            "TurnAnalysis",
            nlu("new_search", location_text="UIT", location_kind="place", max_price=4_500_000),
            nlu("room_followup").model_copy(update={"referenced_room_rank": 1}),
            nlu("room_followup").model_copy(update={"referenced_room_rank": 2}),
            nlu("room_followup").model_copy(update={"referenced_room_rank": None}),
        )
        .on("Advice", GOOD_ADVICE)
    )
    h = Harness(llm, _many_rooms(5), agent=agent)
    h.turn("tìm phòng gần UIT dưới 4tr5")

    r_price = h.turn("phòng 1 giá bao nhiêu?")
    r_area = h.turn("phòng 2 diện tích bao nhiêu m2?")
    r_cmp = h.turn("so sánh top 1 và top 2")

    assert detail_calls == []
    assert len(h.search_calls) == 1
    assert "2.52 triệu/tháng" in r_price.text_reply
    assert "22 m²" in r_area.text_reply
    assert "Top 1" in r_cmp.text_reply
    assert "<focus>" not in agent.inputs[-1]["messages"][-1].content
    assert r_price.grounding_report.is_grounded is True
    assert r_area.grounding_report.is_grounded is True
    assert r_cmp.grounding_report.is_grounded is True


def test_followup_deep_detail_caches_and_reuses_without_repeat_fetch(monkeypatch):
    """Nhóm 1 & 3: Lần đầu hỏi sâu gọi get_listing_detail 1 lần và cache; lượt sau hỏi tiếp cùng phòng dùng lại cache (0 gọi lại)."""
    from graph.nodes import decision as decision_mod

    detail_calls: list[str] = []

    def fake_detail(lid: str) -> dict:
        detail_calls.append(lid)
        return {
            "ok": True,
            "data": {
                "id": lid,
                "title": "Phòng số 1",
                "deposit": 2_500_000,
                "description": "Đặt cọc 2.5 triệu, điện 3.500đ/kWh, nước 100k/tháng.",
            },
        }

    monkeypatch.setattr(decision_mod, "fetch_listing_detail", fake_detail)

    agent = FakeAgent(
        agent_reply("Phòng Top 1 yêu cầu đặt cọc 2.5 triệu đồng nhé bạn."),
        agent_reply("Phòng Top 1 tính điện 3.500đ/kWh và nước 100k/tháng theo mô tả bài đăng."),
    )
    llm = (
        FakeLLM()
        .on(
            "TurnAnalysis",
            nlu("new_search", location_text="UIT", location_kind="place", max_price=4_500_000),
            nlu("room_followup").model_copy(update={"referenced_room_rank": 1}),
            nlu("room_followup").model_copy(update={"referenced_room_rank": None}),
        )
        .on("Advice", GOOD_ADVICE)
    )
    h = Harness(llm, _many_rooms(5), agent=agent)
    h.turn("tìm phòng gần UIT dưới 4tr5")

    r_dep = h.turn("phòng 1 cọc bao nhiêu?")
    assert detail_calls == ["nhatot_1"]
    assert "nhatot_1" in h.session.room_details_cache
    assert "2.5 triệu" in r_dep.text_reply

    r_util = h.turn("điện nước phòng này sao?")
    assert detail_calls == ["nhatot_1"]
    assert "<prefetched_listing_detail>" not in agent.inputs[1]["messages"][0].content
    assert agent.inputs[0]["messages"][0].content == agent.inputs[1]["messages"][0].content
    assert "<prefetched_listing_detail>" in agent.inputs[1]["messages"][-1].content
    assert "3.500đ/kWh" in r_util.text_reply
    assert r_util.grounding_report.is_grounded is True


def test_chat_pagination_ignores_repeated_criteria_or_default_room_type_noise():
    """Nhóm 2 (Boundary): Chuyển trang qua chat không bị gọi search_rooms dù NLU lặp lại tiêu chí cũ, gắn ROOM/SLEEPBOX hay reset_priorities."""
    from domain.enums import RoomType

    llm = (
        FakeLLM()
        .on(
            "TurnAnalysis",
            nlu("new_search", location_text="UIT", location_kind="place", max_price=4_500_000),
            nlu("refine_search", allowed_room_types=[RoomType.ROOM], excluded_room_types=[RoomType.SLEEPBOX]).model_copy(
                update={"page_action": "next", "reset_priorities": True}
            ),
            nlu("room_followup", location_text="UIT", max_price=4_500_000).model_copy(
                update={"page_action": "goto", "target_page": 3}
            ),
        )
        .on("Advice", GOOD_ADVICE)
    )
    h = Harness(llm, _many_rooms(15))
    h.turn("tìm phòng gần UIT dưới 4tr5")
    assert len(h.search_calls) == 1

    r2 = h.turn("xem thêm các phòng trọ khác đi")
    assert len(h.search_calls) == 1
    assert r2.page == 2 and [rm.rank for rm in r2.rooms] == [6, 7, 8, 9, 10]

    r3 = h.turn("qua trang 3 đi")
    assert len(h.search_calls) == 1
    assert r3.page == 3 and [rm.rank for rm in r3.rooms] == [11, 12, 13, 14, 15]


def test_chat_pagination_when_paged_pool_empty_asks_clarification_without_search():
    """Nhóm 2 (Boundary): Chưa có phòng trong phiên mà đòi qua trang -> không gọi search_rooms, nhắc tìm phòng trước."""
    llm = FakeLLM().on(
        "TurnAnalysis",
        nlu("refine_search").model_copy(update={"page_action": "goto", "target_page": 2}),
    )
    h = Harness(llm, _many_rooms(10))

    res = h.turn("qua trang 2")
    assert h.search_calls == []
    assert res.need_clarification is True
    assert "chưa có danh sách phòng" in res.text_reply


def test_new_search_clears_stale_room_details_cache():
    """Nhóm 3 (State Mutation): Tìm kiếm mới xóa detail cache của các phòng cũ không còn trong danh sách."""
    from core.session_store import SessionStore

    mem = SessionStore()
    sess = mem.get_or_create_session("s-cache")
    sess.room_details_cache["old_room"] = {"id": "old_room", "deposit": 2_000_000}
    new_room = RoomItem(id="new_room", rank=1, title="Phòng mới", price="3 triệu/tháng", priceNum=3_000_000)

    mem.commit_turn(sess, "tìm mới", "ok", [new_room], searched=True, paged_rooms=[new_room])
    assert "old_room" not in sess.room_details_cache


def test_room_details_cache_persists_across_sqlite_reload(tmp_path, monkeypatch):
    """Nhóm 4 (Persistence): room_details_cache được lưu xuống SQLite và nạp lại nguyên vẹn cho phiên tiếp theo."""
    from graph import build_housing_graph, run_turn
    from graph.nodes import decision as decision_mod

    db_path = tmp_path / "detail_cache.db"
    detail_calls: list[str] = []

    def fake_detail(lid: str) -> dict:
        detail_calls.append(lid)
        return {
            "ok": True,
            "data": {
                "id": lid,
                "title": "Phòng số 1",
                "deposit": 3_000_000,
                "description": "Tiền cọc 3 triệu, điện 3.800đ/kWh.",
            },
        }

    monkeypatch.setattr(decision_mod, "fetch_listing_detail", fake_detail)

    agent = FakeAgent(
        agent_reply("Phòng Top 1 cọc 3 triệu đồng."),
        agent_reply("Phòng Top 1 tính điện 3.800đ/kWh."),
    )
    llm1 = (
        FakeLLM()
        .on(
            "TurnAnalysis",
            nlu("new_search", location_text="UIT", location_kind="place", max_price=4_500_000),
            nlu("room_followup").model_copy(update={"referenced_room_rank": 1}),
        )
        .on("Advice", GOOD_ADVICE)
    )

    store1 = PersistentSessionStore(db_path)
    h1 = Harness(llm1, _many_rooms(5), agent=agent)
    h1.deps.sessions = store1
    g1 = build_housing_graph(h1.deps)

    run_turn(g1, "tìm phòng gần UIT dưới 4tr5", session_id="persist-detail")
    run_turn(g1, "phòng 1 cọc bao nhiêu?", session_id="persist-detail")
    assert detail_calls == ["nhatot_1"]

    # Reload bằng store & graph mới hoàn toàn
    store2 = PersistentSessionStore(db_path)
    reloaded = store2.get_or_create_session("persist-detail")
    assert "nhatot_1" in reloaded.room_details_cache

    llm2 = FakeLLM().on("TurnAnalysis", nlu("room_followup").model_copy(update={"referenced_room_rank": 1}))
    h2 = Harness(llm2, _many_rooms(5), agent=agent)
    h2.deps.sessions = store2
    g2 = build_housing_graph(h2.deps)

    res2 = run_turn(g2, "phòng 1 điện sao?", session_id="persist-detail")
    assert detail_calls == ["nhatot_1"]
    assert "3.800đ/kWh" in res2.text_reply
    assert res2.grounding_report.is_grounded is True


def test_followup_uses_preloaded_description_and_deposit_from_state_zero_detail_api(monkeypatch):
    """Khi search_rooms đã trả kèm deposit/description/poster vào RoomItem -> follow-up dùng thẳng từ state, 0 gọi fetch_listing_detail."""
    from graph.nodes import decision as decision_mod
    from intelligence.payload_builder import compact_room

    detail_calls: list[str] = []
    monkeypatch.setattr(
        decision_mod,
        "fetch_listing_detail",
        lambda lid: detail_calls.append(lid) or {"ok": True, "data": {"id": lid}},
    )

    rooms_with_detail = _many_rooms(3)
    rooms_with_detail[0]["listing"]["deposit"] = 3_000_000
    rooms_with_detail[0]["listing"]["description"] = "Đặt cọc 3 triệu, điện 3.500đ/kWh, nước 100k/tháng."
    rooms_with_detail[0]["listing"]["poster"] = {"name": "Anh Minh"}

    agent = FakeAgent(
        agent_reply("Phòng Top 1 đặt cọc 3 triệu, điện 3.500đ/kWh và nước 100k/tháng, liên hệ Anh Minh nhé.")
    )
    llm = (
        FakeLLM()
        .on(
            "TurnAnalysis",
            nlu("new_search", location_text="UIT", location_kind="place", max_price=4_500_000),
            nlu("room_followup").model_copy(update={"referenced_room_rank": 1}),
        )
        .on("Advice", GOOD_ADVICE)
    )
    h = Harness(llm, rooms_with_detail, agent=agent)
    r1 = h.turn("tìm phòng gần UIT dưới 4tr5")

    assert r1.rooms[0].deposit == 3_000_000
    assert "3.500đ/kWh" in (r1.rooms[0].description or "")
    assert r1.rooms[0].contact_name == "Anh Minh"
    compacted = compact_room(r1.rooms[0])
    assert "description" not in compacted and "deposit" not in compacted and "contact_name" not in compacted

    r2 = h.turn("phòng 1 cọc và điện nước sao?")
    assert detail_calls == []
    assert "<prefetched_listing_detail>" not in agent.inputs[0]["messages"][0].content
    assert "<prefetched_listing_detail>" in agent.inputs[0]["messages"][-1].content
    assert "3.500đ/kWh" in agent.inputs[0]["messages"][-1].content
    assert "3 triệu" in r2.text_reply
    assert r2.grounding_report.is_grounded is True


def test_chat_and_rest_pagination_include_page_insights_and_analysis(tmp_path, monkeypatch):
    """Phân trang qua cả Chat và REST API đều trả về insights động + dùng chung luồng generate_advice/template_reply trên lát cắt offset."""
    llm = (
        FakeLLM()
        .on(
            "TurnAnalysis",
            nlu("new_search", location_text="UIT", location_kind="place", max_price=4_500_000),
            nlu("refine_search").model_copy(update={"page_action": "goto", "target_page": 2}),
        )
        .on("Advice", GOOD_ADVICE)
    )
    h = Harness(llm, _many_rooms(15))
    h.turn("tìm phòng gần UIT dưới 4tr5")

    r_p2 = h.turn("qua trang 2")
    assert r_p2.page == 2
    assert r_p2.insights is not None
    assert r_p2.insights.selected_top_1_id == "nhatot_6"
    assert "Top 6" in r_p2.insights.top_1_reason
    assert r_p2.insights.trade_offs and "Top 7" in r_p2.insights.trade_offs[0].compared_with
    assert "6. **Phòng số 6**" in r_p2.text_reply
    assert "🏆 **Lựa chọn tối ưu nhất: Phòng số 6**" in r_p2.text_reply
    assert "⚖️ **So với Top 7:**" in r_p2.text_reply
    assert "📋 **Lưu ý khi đi xem phòng:**" in r_p2.text_reply

    # Kiểm chứng input gửi vào Advice ở lượt tìm kiếm (offset=0) và lượt phân trang (offset=5) dùng chung 1 cấu trúc prompt
    advice_calls = [msgs for name, msgs in llm.calls if name == "Advice"]
    assert len(advice_calls) == 2
    assert advice_calls[0][0][1] == advice_calls[1][0][1]  # cùng System Prompt
    assert "<criteria>" in advice_calls[1][1][1] and "<rooms_data>" in advice_calls[1][1][1]
    assert '"nhatot_6"' in advice_calls[1][1][1] and '"nhatot_1"' not in advice_calls[1][1][1]

    # Kiểm tra REST endpoint GET /api/v1/session/{session_id}/rooms cũng trả về insights của trang 3
    db_path = tmp_path / "page_insights.db"
    store = PersistentSessionStore(db_path)
    monkeypatch.setattr(api_routes, "SESSION_STORE", store)
    sess = store.get_or_create_session("sess-page-insights")
    rooms_15 = [
        RoomItem.from_backend_result(raw_room(i, price=2_500_000 + i * 50_000, area=20 + i), rank=i)
        for i in range(1, 16)
    ]
    store.commit_turn(sess, "tìm phòng", "đã tìm", rooms_15[:5], searched=True, paged_rooms=rooms_15)

    client = TestClient(api_routes.app)
    resp = client.get("/api/v1/session/sess-page-insights/rooms?page=3&page_size=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 3
    assert body["insights"] is not None
    assert body["insights"]["selected_top_1_id"] == "nhatot_11"
    assert "Top 11" in body["insights"]["top_1_reason"]


def test_page_navigation_routes_through_decision_and_verify_with_llm_analysis_and_retry():
    """Nhóm 1 & 3: Chuyển trang cắt theo offset qua understand_node -> decision_node (chung prompt/luồng với search) -> verify_node (retry + fallback template_reply) -> formatter_node."""
    search_reply = (
        "Homigo đã tìm được 5 phòng phù hợp gần UIT (Top 1–5):\n\n"
        "- **Top 1. Phòng số 1** (Giá: 2.52 triệu/tháng | 21 m² | phù hợp 84%)\n\n"
        "### 🏆 Lựa chọn nổi bật\n"
        "- **Top 1 (Phòng số 1)** có giá **2.52 triệu/tháng** rất hợp lý.\n\n"
        "### 📋 Lưu ý khi xem phòng\n"
        "- Hỏi rõ tiền điện nước và hợp đồng cọc."
    )
    bad_draft = (
        "Danh sách phòng trang 2:\n---\n"
        "- **Top 6. Phòng số 6** (2.62 triệu/tháng)"
    )
    good_analysis = (
        "Dưới đây là 5 phòng tiếp theo phù hợp với tiêu chí của bạn:\n\n"
        "- **Top 6. Phòng số 6** (Giá: 2.62 triệu/tháng | 26 m² | phù hợp 83%)\n"
        "- **Top 7. Phòng số 7** (Giá: 2.64 triệu/tháng | 27 m² | phù hợp 82%)\n\n"
        "### 🏆 Điểm nhấn nổi bật\n"
        "- **Top 6 (Phòng số 6)** dẫn đầu nhóm này với giá thuê **2.62 triệu/tháng**.\n\n"
        "### ⚖️ So sánh & Đánh đổi\n"
        "- **Top 6** rẻ hơn **Top 7** 20k/tháng nhưng nhỏ hơn 1 m².\n\n"
        "### 📋 Gợi ý tiếp theo\n"
        "- Bạn có thể bấm vào phòng để xem điểm Rerank chi tiết hoặc hỏi sâu về tiền cọc, điện nước nhé."
    )
    agent = FakeAgent(
        agent_reply(search_reply),
        agent_reply(bad_draft),
        agent_reply(good_analysis),
    )
    llm = FakeLLM().on(
        "TurnAnalysis",
        nlu("new_search", location_text="UIT", location_kind="place", max_price=4_500_000),
        nlu("page_navigation").model_copy(update={"page_action": "goto", "target_page": 2}),
    )
    h = Harness(llm, _many_rooms(15), agent=agent, constrained_generation=False)
    h.turn("tìm phòng gần UIT dưới 4tr5")
    assert len(h.search_calls) == 1

    res = h.turn("ok đc rồi zay trang thứ 2 đi")
    # 0 gọi search_rooms lại
    assert len(h.search_calls) == 1
    assert res.searched is False
    assert res.page == 2
    assert [r.rank for r in res.rooms] == [6, 7, 8, 9, 10]
    # Kiểm chứng decision_agent nhận input cùng cấu trúc y hệt search (chỉ đổi tập 5 phòng ở offset=5)
    assert len(agent.inputs) == 3  # 1 search + 1 draft lỗi '---' + 1 retry
    assert len(agent.inputs[0]["messages"]) == len(agent.inputs[1]["messages"]) == 3
    search_ctx = agent.inputs[0]["messages"][0].content
    page2_ctx = agent.inputs[1]["messages"][0].content
    assert "<criteria>" in search_ctx and "<rooms_data>" in search_ctx
    assert "<criteria>" in page2_ctx and "<rooms_data>" in page2_ctx
    assert '"nhatot_6"' in page2_ctx and '"nhatot_10"' in page2_ctx and '"nhatot_1"' not in page2_ctx
    assert "<focus>" not in agent.inputs[1]["messages"][-1].content
    assert res.text_reply == good_analysis
    assert res.grounding_report.is_grounded is True
    assert res.grounding_report.answer_retries == 1
    dod_report = res.grounding_report.dod_report or {}
    dod_cids = {c["condition_id"]: c for c in dod_report["conditions"]}
    assert dod_cids["cond_no_unrequested_search"]["passed"] is True
    assert dod_cids["cond_no_unrequested_search"]["actual_value"] == 0
    nodes_seen = [ev.get("node") for ev in res.trace_events if ev.get("node")]
    assert "understand_node" in nodes_seen
    assert "verify_node" in nodes_seen
    assert "retrieval_node" not in nodes_seen

    # Kiểm chứng thêm đường fallback template_reply chung khi Advice lỗi/None ở trang 3 (offset=10)
    llm_fb = (
        FakeLLM()
        .on(
            "TurnAnalysis",
            nlu("new_search", location_text="UIT", location_kind="place", max_price=4_500_000),
            nlu("page_navigation").model_copy(update={"page_action": "goto", "target_page": 3}),
        )
        .on("Advice", RuntimeError("llm down"))
    )
    h_fb = Harness(llm_fb, _many_rooms(15))
    h_fb.turn("tìm phòng gần UIT dưới 4tr5")
    res_p3 = h_fb.turn("qua trang 3")
    assert res_p3.page == 3 and [r.rank for r in res_p3.rooms] == [11, 12, 13, 14, 15]
    assert "11. **Phòng số 11**" in res_p3.text_reply
    assert "🏆 **Lựa chọn tối ưu nhất: Phòng số 11**" in res_p3.text_reply
    assert "⚖️ **So với Top 12" in res_p3.text_reply


def test_llm_page_navigation_handles_goto_overbound_and_intent_only_fallback():
    """Nhóm 2 (Boundary): Khi LLM trả page_navigation (goto hợp lệ, goto vượt biên, hoặc quên điền page_action -> mặc định next), đều xử lý chuẩn không search lại."""
    llm = (
        FakeLLM()
        .on(
            "TurnAnalysis",
            nlu("new_search", location_text="UIT", location_kind="place", max_price=4_000_000),
            nlu("page_navigation").model_copy(update={"page_action": "goto", "target_page": 4}),
            nlu("page_navigation").model_copy(update={"page_action": "goto", "target_page": 6}),
            nlu("page_navigation"),
        )
        .on("Advice", GOOD_ADVICE)
    )
    h = Harness(llm, _many_rooms(24))  # 24 phòng -> 5 trang
    h.turn("tìm phòng gần UIT dưới 4tr")
    assert len(h.search_calls) == 1

    r4 = h.turn("ok di truyển tới trang 4 cho tui")
    assert len(h.search_calls) == 1
    assert r4.page == 4 and [r.rank for r in r4.rooms] == [16, 17, 18, 19, 20]

    r6_over = h.turn("ok zay bạn giup tui di chuyen toi trang 6 đi")
    assert len(h.search_calls) == 1
    assert r6_over.page == 4
    assert "24 phòng" in r6_over.text_reply and "5 trang" in r6_over.text_reply

    r5 = h.turn("xem trang tiếp theo đi")
    assert len(h.search_calls) == 1
    assert r5.page == 5 and [r.rank for r in r5.rooms] == [21, 22, 23, 24]


def test_pagination_module_parse_and_plan_boundaries():
    """Nhóm 2 & 3 (Unit / Boundary): Kiểm tra intelligence.pagination xử lý đúng cấu trúc từ LLM và từ chối khi có tiêu chí lọc mới hoặc multi-intent."""
    from types import SimpleNamespace
    from domain.enums import RoomType
    from domain.schemas import UserPreferenceState
    from intelligence.nlu import PreferencePatch, Priorities, TurnAnalysis
    from intelligence.pagination import (
        is_effective_patch_empty_for_pagination,
        parse_page_navigation,
        plan_page_navigation,
    )

    pref = UserPreferenceState(location_text="UIT", max_price=4_000_000)
    assert is_effective_patch_empty_for_pagination(PreferencePatch(location_text="UIT", max_price=4_000_000), pref) is True
    assert is_effective_patch_empty_for_pagination(PreferencePatch(max_price=3_000_000), pref) is False
    assert is_effective_patch_empty_for_pagination(PreferencePatch(allowed_room_types=[RoomType.STUDIO]), pref) is False

    # Happy path: goto / first / last / next / prev & intent-only fallback -> next
    assert parse_page_navigation(TurnAnalysis(intent="page_navigation", page_action="goto", target_page=3), 1, 5, pref) == 3
    assert parse_page_navigation(TurnAnalysis(intent="page_navigation"), 2, 5, pref) == 3
    assert parse_page_navigation(TurnAnalysis(intent="page_navigation", page_action="prev"), 1, 5, pref) == 0

    # Negative boundaries: có filter mới, ưu tiên mới, hỏi phòng hoặc multi-intent -> không hijack thành phân trang
    assert parse_page_navigation(
        TurnAnalysis(intent="refine_search", page_action="next", patch=PreferencePatch(max_price=3_000_000)),
        1, 5, pref,
    ) is None
    assert parse_page_navigation(
        TurnAnalysis(intent="refine_search", page_action="next", priorities=Priorities(price="high")),
        1, 5, pref,
    ) is None
    assert parse_page_navigation(
        TurnAnalysis(intent="room_followup", page_action="next", referenced_room_rank=1),
        1, 5, pref,
    ) is None
    assert parse_page_navigation(
        TurnAnalysis(intent="page_navigation", page_action="next", is_multi_intent=True),
        1, 5, pref,
    ) is None

    # plan_page_navigation khi quay về trước Trang 1 -> direct_reply=True, page_switched=False
    pool = [RoomItem.from_backend_result(raw_room(i), rank=i) for i in range(1, 11)]
    sess = SimpleNamespace(page_size=5, current_page=1)
    underflow = plan_page_navigation(TurnAnalysis(intent="page_navigation", page_action="prev"), sess, pref, pool)
    assert underflow is not None
    assert underflow["direct_reply"] is True
    assert underflow["page_switched"] is False
    assert underflow["target_page"] == 1
    assert "Trang 1/2" in underflow["final_text"]
