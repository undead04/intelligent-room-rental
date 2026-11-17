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

    # 1. "cần những phòng khác" -> tự nhảy sang Trang 2 (0 gọi lại search_calls!)
    r2 = h.turn("cần những phòng khác")
    assert len(h.search_calls) == 1
    assert r2.page == 2 and [rm.rank for rm in r2.rooms] == [6, 7, 8, 9, 10]
    assert "Trang 2/5" in r2.text_reply

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
