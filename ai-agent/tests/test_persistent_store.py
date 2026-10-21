import sqlite3

import pytest

from domain.enums import Amenity, RoomType
from core.session_store import PersistentSessionStore, SessionStore
from tests.helpers import room


class Clock:
    t = 1_000.0
    def __call__(self): return self.t


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "sessions.db")


def populate(store, sid="a"):
    s = store.get_or_create_session(sid)
    s.preferences.max_price = 3_000_000
    s.preferences.amenities = ["ml"]
    s.preferences.room_type = "studio"
    s.preferences.excluded_room_types = ["ktx"]
    s.preferences.set_location("Dĩ An", kind="admin", city_id=74, district_id=724)
    s.multipliers["price"] = 2.0
    s.proposed_budget, s.hitl_streak = 3_450_000, 1
    store.commit_turn(s, "tìm phòng ở Dĩ An", "ok", [room(1, RoomType.STUDIO), room(2)], searched=True)
    return s


def test_state_survives_restart(db):
    populate(PersistentSessionStore(db))
    fresh = PersistentSessionStore(db).get_or_create_session("a")                      # "khởi động lại": store mới, cùng file
    p = fresh.preferences
    assert (p.max_price, p.amenities, p.room_type, p.excluded_room_types) == (3_000_000, [Amenity.AIRCON], RoomType.STUDIO, [RoomType.SLEEPBOX])
    assert (p.location_text, p.location_kind, p.city_id, p.district_id) == ("Dĩ An", "admin", 74, 724)
    assert fresh.multipliers["price"] == 2.0 and fresh.proposed_budget == 3_450_000 and fresh.hitl_streak == 1
    assert fresh.history == [("user", "tìm phòng ở Dĩ An"), ("assistant", "ok")]
    assert [r.id for r in fresh.last_rooms] == ["nhatot_1", "nhatot_2"] and fresh.last_rooms[0].room_type is RoomType.STUDIO and fresh.version == 1


def test_same_object_within_a_process_so_nodes_see_each_others_changes(db):
    s = PersistentSessionStore(db)
    a = s.get_or_create_session("a")
    a.preferences.max_price = 1.0
    assert s.get_or_create_session("a") is a and s.get_or_create_session("a").preferences.max_price == 1.0


def test_other_worker_newer_version_is_picked_up(db):
    w1, w2 = PersistentSessionStore(db), PersistentSessionStore(db)
    populate(w1)
    assert w2.get_or_create_session("a").preferences.max_price == 3_000_000           # w2 nạp từ DB
    s2 = w2.get_or_create_session("a")
    s2.preferences.max_price = 5_000_000
    w2.commit_turn(s2, "nâng giá", "ok", [], searched=False)
    seen = w1.get_or_create_session("a")                                               # w1 còn cache cũ -> phải tải lại
    assert seen.preferences.max_price == 5_000_000 and seen.version == 2 and len(seen.history) == 4


def test_unsaved_changes_are_not_persisted_until_commit(db):
    w1 = PersistentSessionStore(db)
    w1.get_or_create_session("a").preferences.max_price = 9.0
    assert PersistentSessionStore(db).get_or_create_session("a").preferences.max_price is None     # lượt bị chặn/không commit: không ghi


def test_ttl_expiry_removes_persisted_row(db):
    clk = Clock()
    s = PersistentSessionStore(db, clock=clk, ttl=100)
    populate(s)
    clk.t += 101
    fresh = PersistentSessionStore(db, clock=clk, ttl=100).get_or_create_session("a")
    assert fresh.preferences.max_price is None and fresh.history == []
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_clear_session_deletes_everywhere(db):
    s = PersistentSessionStore(db)
    populate(s)
    s.clear_session("a")
    assert PersistentSessionStore(db).get_or_create_session("a").history == [] and s.get_or_create_session("a").preferences.max_price is None


def test_corrupt_payload_starts_fresh_and_does_not_crash(db):
    s = PersistentSessionStore(db)
    populate(s)
    with sqlite3.connect(db) as c:
        c.execute("UPDATE sessions SET payload='{không phải json', version=version+1")
    fresh = PersistentSessionStore(db).get_or_create_session("a")
    assert fresh.preferences.max_price is None
    s2 = PersistentSessionStore(db)
    s2.commit_turn(s2.get_or_create_session("a"), "u", "a", [])                         # ghi lại bình thường
    assert PersistentSessionStore(db).get_or_create_session("a").history == [("user", "u"), ("assistant", "a")]


def test_requires_session_id_and_isolates_sessions(db):
    s = PersistentSessionStore(db)
    with pytest.raises(ValueError):
        s.get_or_create_session("")
    populate(s, "a")
    assert PersistentSessionStore(db).get_or_create_session("b").preferences.max_price is None


def test_db_failure_degrades_to_memory(tmp_path):
    s = PersistentSessionStore(str(tmp_path / "ok.db"))
    ses = s.get_or_create_session("a")
    s._path = str(tmp_path / "không_có_thư_mục" / "x.db")                               # đường dẫn hỏng sau khi khởi tạo
    s.commit_turn(ses, "u", "a", [room(1)], searched=True)                             # không ném lỗi
    assert s.get_or_create_session("a") is ses and len(ses.last_rooms) == 1


def test_purge_removes_expired_rows(db):
    clk = Clock()
    s = PersistentSessionStore(db, clock=clk, ttl=100)
    s._PURGE_EVERY = 2
    populate(s, "old")
    clk.t += 500
    populate(s, "new1")
    with sqlite3.connect(db) as c:
        ids = {r[0] for r in c.execute("SELECT session_id FROM sessions")}
    assert "old" not in ids and "new1" in ids


def test_graph_runs_on_persistent_store_and_resumes_after_restart(db):
    from tests.e2e_helpers import GOOD_ADVICE, FakeLLM, Harness, nlu, raw_room
    rooms = [raw_room(1, 2_400_000, 25), raw_room(2, 2_800_000, 21)]
    llm = FakeLLM().on("TurnAnalysis", nlu(location_text="UIT", location_kind="place", max_price=3_500_000), nlu("room_followup")).on("Advice", GOOD_ADVICE)
    h1 = Harness(llm, rooms)
    h1.deps.sessions = PersistentSessionStore(db)
    h1.turn("tìm phòng gần UIT")
    h2 = Harness(llm, rooms)                                                           # tiến trình mới
    h2.deps.sessions = PersistentSessionStore(db)
    r = h2.turn("so sánh top 1 và top 2")
    assert len(h2.search_calls) == 0 and len(r.rooms) == 2 and r.current_preferences.lat == 10.87     # nhớ phòng + toạ độ từ trước khi "restart"
