"""Kho phiên hội thoại (thay SessionMemoryManager trong memory.py).

Khác bản cũ:
  - KHÔNG còn session "default_session" dùng chung (rò rỉ dữ liệu giữa người dùng): session_id là bắt buộc;
    graph tự sinh id mới ở guardrail_node nếu client không gửi.
  - TTL kiểm tra NGAY khi truy cập (bản cũ chỉ dọn khi tạo session mới -> session hết hạn vẫn sống lại).
  - last_rooms gắn với LẦN TÌM: tìm mới (kể cả 0 kết quả) thì xoá phòng cũ, tránh "so sánh top 1" ra phòng của khu vực trước.
  - Lịch sử lưu (role, text), đổi sang BaseMessage khi cần -> không phụ thuộc langchain khi test.
  - Có khoá theo session (graph có thể chạy song song nhiều request cùng một session).
Interface (get_or_create_session / commit_turn / clear_session) giống bản cũ nên có thể thay thế trực tiếp;
muốn bền vững thì cài lại class này trên Redis/DB (hoặc chuyển sang checkpointer LangGraph ở bước sau).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import sqlite3
import threading
import time
import uuid
from typing import Any, Callable, Optional, Union

from domain.schemas import RoomItem, UserPreferenceState
from core.paths import DEFAULT_DB_PATH

logger = logging.getLogger(__name__)

MAX_SESSION_MESSAGES = 20
HISTORY_WINDOW = 8
MAX_SESSIONS = 500
SESSION_TTL_SECONDS = 86_400

DEFAULT_MULTIPLIERS = {"price": 1.0, "location": 1.0, "safety": 1.0, "amenity": 1.0, "semantic": 1.0}


def new_session_id() -> str:
    return uuid.uuid4().hex


class SessionData:
    def __init__(self, session_id: str, clock: Callable[[], float] = time.time):
        self.session_id = session_id
        self.preferences = UserPreferenceState()
        self.multipliers: dict[str, float] = dict(DEFAULT_MULTIPLIERS)
        self.proposed_budget: Optional[float] = None
        self.hitl_streak: int = 0
        self.history: list[tuple[str, str]] = []
        self.last_rooms: list[RoomItem] = []
        self.last_active: float = clock()
        self.lock = threading.RLock()
        self.version: int = 0          # số phiên bản đã lưu (PersistentSessionStore dùng để biết cache có cũ không)
        self.preference_history: list[UserPreferenceState] = []

    def record_preference_snapshot(self, pref: UserPreferenceState) -> None:
        """Lưu snapshot vào preference_history (tối đa 5 snapshots khác nhau gần nhất)."""
        dumped = pref.model_dump(exclude_defaults=True)
        if not dumped:
            return
        if self.preference_history:
            last_dumped = self.preference_history[-1].model_dump(exclude_defaults=True)
            if dumped == last_dumped:
                return
        self.preference_history.append(pref.model_copy(deep=True))
        if len(self.preference_history) > 5:
            self.preference_history = self.preference_history[-5:]

    @property
    def messages(self) -> list[tuple[str, str]]:   # tương thích code đọc `session.messages`
        return self.history

    def history_as_messages(self, window: int = HISTORY_WINDOW) -> list[Any]:
        from langchain_core.messages import AIMessage, HumanMessage

        return [(HumanMessage if role == "user" else AIMessage)(content=text) for role, text in self.history[-window:]]


class SessionStore:
    def __init__(self, clock: Callable[[], float] = time.time, ttl: float = SESSION_TTL_SECONDS, max_sessions: int = MAX_SESSIONS):
        self._sessions: dict[str, SessionData] = {}
        self._lock = threading.Lock()
        self._clock, self._ttl, self._max = clock, ttl, max_sessions

    def _evict_locked(self) -> None:
        now = self._clock()
        for sid in [s for s, d in self._sessions.items() if now - d.last_active > self._ttl]:
            self._sessions.pop(sid, None)
        if len(self._sessions) > self._max:
            for sid, _ in sorted(self._sessions.items(), key=lambda kv: kv[1].last_active)[: len(self._sessions) - self._max]:
                self._sessions.pop(sid, None)

    def get_or_create_session(self, session_id: str) -> SessionData:
        if not session_id:
            raise ValueError("session_id là bắt buộc (graph sinh id mới nếu client không gửi)")
        with self._lock:
            cur = self._sessions.get(session_id)
            if cur is not None and self._clock() - cur.last_active > self._ttl:   # hết hạn thì bắt đầu lại, không "sống lại"
                self._sessions.pop(session_id, None)
                cur = None
            if cur is None:
                self._evict_locked()
                cur = self._sessions[session_id] = SessionData(session_id, self._clock)
            cur.last_active = self._clock()
            return cur

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def commit_turn(self, session: SessionData, user_text: str, assistant_reply: str, rooms: list[RoomItem], *, searched: bool = False) -> None:
        """searched=True khi lượt này đã chạy tìm kiếm: last_rooms được THAY (kể cả rỗng)."""
        with session.lock:
            session.history.append(("user", user_text))
            session.history.append(("assistant", assistant_reply))
            if len(session.history) > MAX_SESSION_MESSAGES:
                session.history = session.history[-MAX_SESSION_MESSAGES:]
            if searched:
                session.last_rooms = list(rooms)
            session.last_active = self._clock()

    def __len__(self) -> int:
        return len(self._sessions)


# ---------------------------------------------------------------------------
# Bền vững: SQLite (sống qua khởi động lại, nhiều worker dùng chung một file)
# ---------------------------------------------------------------------------
def _dump(s: SessionData) -> str:
    return json.dumps({
        "preferences": s.preferences.model_dump(mode="json"), "multipliers": s.multipliers, "proposed_budget": s.proposed_budget,
        "hitl_streak": s.hitl_streak, "history": s.history, "last_rooms": [r.model_dump(mode="json") for r in s.last_rooms],
        "preference_history": [p.model_dump(mode="json") for p in s.preference_history],
    }, ensure_ascii=False)


def _load(session_id: str, payload: str, version: int, last_active: float, clock: Callable[[], float]) -> SessionData:
    d = json.loads(payload)
    s = SessionData(session_id, clock)
    s.preferences = UserPreferenceState.model_validate(d["preferences"])
    s.multipliers = {**DEFAULT_MULTIPLIERS, **(d.get("multipliers") or {})}
    s.proposed_budget = d.get("proposed_budget")
    s.hitl_streak = int(d.get("hitl_streak") or 0)
    s.history = [(str(r), str(t)) for r, t in d.get("history") or []]
    s.last_rooms = [RoomItem.model_validate(r) for r in d.get("last_rooms") or []]
    s.preference_history = [UserPreferenceState.model_validate(p) for p in d.get("preference_history") or []]
    s.version, s.last_active = version, last_active
    return s


class PersistentSessionStore(SessionStore):
    """SessionStore + ghi bền xuống SQLite.

    Trong MỘT lượt hội thoại các node sửa cùng một đối tượng SessionData (cache trong bộ nhớ); dữ liệu được ghi xuống DB khi
    commit_turn (cuối lượt). Ở đầu lượt kế tiếp, nếu worker khác đã ghi phiên bản mới hơn thì tải lại. Hai request ĐỒNG THỜI của cùng
    một session vẫn là "ghi sau thắng" (chấp nhận được cho chat một người dùng; cần khoá phân tán nếu muốn chặt hơn).
    """

    _PURGE_EVERY = 50

    def __init__(self, path: Union[str, Path] = DEFAULT_DB_PATH, clock: Callable[[], float] = time.time, ttl: float = SESSION_TTL_SECONDS, max_sessions: int = MAX_SESSIONS):
        super().__init__(clock=clock, ttl=ttl, max_sessions=max_sessions)
        self._path = str(path)
        self._commits = 0
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with self._db() as c:
            c.execute("CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY, version INTEGER NOT NULL, last_active REAL NOT NULL, payload TEXT NOT NULL)")

    def _db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10, isolation_level=None)   # autocommit; ta tự BEGIN IMMEDIATE khi ghi
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def get_or_create_session(self, session_id: str) -> SessionData:
        if not session_id:
            raise ValueError("session_id là bắt buộc (graph sinh id mới nếu client không gửi)")
        with self._lock:
            now = self._clock()
            cached = self._sessions.get(session_id)
            try:
                with self._db() as c:
                    row = c.execute("SELECT version, last_active, payload FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            except sqlite3.Error:
                logger.exception("Đọc session từ SQLite lỗi, dùng dữ liệu trong bộ nhớ")
                row = None

            if row is not None:
                version, last_active, payload = row
                if now - last_active > self._ttl:
                    self._delete(session_id)
                    cached = None
                elif cached is None or cached.version < version:
                    try:
                        cached = self._sessions[session_id] = _load(session_id, payload, version, last_active, self._clock)
                    except Exception:
                        logger.exception("Parse payload session từ SQLite lỗi, tạo mới")
                        cached = None

            if cached is None:
                self._evict_locked()
                cached = self._sessions[session_id] = SessionData(session_id, self._clock)

            cached.last_active = now
            return cached

    def _delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        try:
            with self._db() as c:
                c.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
        except sqlite3.Error:
            logger.exception("Xoá session trong SQLite lỗi")

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            self._delete(session_id)

    def commit_turn(self, session: SessionData, user_text: str, assistant_reply: str, rooms: list[RoomItem], *, searched: bool = False) -> None:
        super().commit_turn(session, user_text, assistant_reply, rooms, searched=searched)
        with self._lock:
            self._save(session)

    def _save(self, session: SessionData) -> None:
        try:
            with self._db() as c:
                c.execute("BEGIN IMMEDIATE")
                row = c.execute("SELECT version FROM sessions WHERE session_id=?", (session.session_id,)).fetchone()
                version = (row[0] if row else 0) + 1
                c.execute("INSERT INTO sessions(session_id, version, last_active, payload) VALUES (?,?,?,?) "
                          "ON CONFLICT(session_id) DO UPDATE SET version=excluded.version, last_active=excluded.last_active, payload=excluded.payload",
                          (session.session_id, version, session.last_active, _dump(session)))
                self._commits += 1
                if self._commits % self._PURGE_EVERY == 0:
                    c.execute("DELETE FROM sessions WHERE last_active < ?", (self._clock() - self._ttl,))
                c.execute("COMMIT")
            session.version = version
        except sqlite3.Error:
            logger.exception("Ghi session xuống SQLite lỗi (vẫn giữ trong bộ nhớ)")


__all__ = [
    "MAX_SESSION_MESSAGES",
    "HISTORY_WINDOW",
    "MAX_SESSIONS",
    "SESSION_TTL_SECONDS",
    "DEFAULT_MULTIPLIERS",
    "new_session_id",
    "SessionData",
    "SessionStore",
    "PersistentSessionStore",
]
