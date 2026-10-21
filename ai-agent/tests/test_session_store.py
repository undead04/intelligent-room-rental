import pytest

from core.session_store import MAX_SESSION_MESSAGES, SessionStore, new_session_id
from tests.helpers import room


class Clock:
    t = 1000.0
    def __call__(self): return self.t


def test_session_id_required_and_new_ids_unique():
    s = SessionStore()
    for bad in (None, ""):
        with pytest.raises(ValueError):
            s.get_or_create_session(bad)
    assert new_session_id() != new_session_id()


def test_sessions_are_isolated():
    s = SessionStore()
    a, b = s.get_or_create_session("a"), s.get_or_create_session("b")
    a.preferences.max_price = 3e6
    assert b.preferences.max_price is None and s.get_or_create_session("a") is a


def test_ttl_checked_on_access_and_session_restarts_clean():
    clk = Clock()
    s = SessionStore(clock=clk, ttl=100)
    a = s.get_or_create_session("a")
    a.preferences.max_price = 3e6
    clk.t += 101
    fresh = s.get_or_create_session("a")
    assert fresh is not a and fresh.preferences.max_price is None            # không "sống lại" với dữ liệu cũ
    clk.t += 50
    assert s.get_or_create_session("a") is fresh


def test_lru_eviction():
    clk = Clock()
    s = SessionStore(clock=clk, max_sessions=2)
    for i, sid in enumerate("abc"):
        clk.t += 1
        s.get_or_create_session(sid)
    assert len(s) <= 3
    clk.t += 1
    s.get_or_create_session("d")
    assert len(s) <= 3


def test_last_rooms_follow_the_search_not_the_commit():
    s = SessionStore()
    ses = s.get_or_create_session("a")
    s.commit_turn(ses, "tìm", "ok", [room(1), room(2)], searched=True)
    assert len(ses.last_rooms) == 2
    s.commit_turn(ses, "cảm ơn", "ok", [], searched=False)                     # lượt không tìm kiếm: giữ nguyên
    assert len(ses.last_rooms) == 2
    s.commit_turn(ses, "tìm khu khác", "không có", [], searched=True)          # tìm mới ra 0 phòng: xoá phòng cũ
    assert ses.last_rooms == []


def test_history_window_and_messages_conversion():
    s = SessionStore()
    ses = s.get_or_create_session("a")
    for i in range(30):
        s.commit_turn(ses, f"u{i}", f"a{i}", [])
    assert len(ses.history) == MAX_SESSION_MESSAGES and ses.messages is ses.history
    msgs = ses.history_as_messages(window=4)
    assert [type(m).__name__ for m in msgs] == ["HumanMessage", "AIMessage", "HumanMessage", "AIMessage"]
    assert msgs[-1].content == "a29"
