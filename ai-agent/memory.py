"""Module Memory & Preference State Management cho Smart Housing Decision Support System.
Quản lý trạng thái nhu cầu (UserPreferenceState) và cửa sổ ngữ cảnh (Context Window) qua nhiều lượt chat.
"""

from __future__ import annotations

import re
import time
from typing import Any, Optional
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from schemas import RoomItem, UserPreferenceState
from extractor import extract_preferences_with_llm

MAX_HISTORY_TURNS = 8  # Tối đa 8 messages gần nhất, phần cũ hơn được nén vào Preference State


class SessionData:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.preferences = UserPreferenceState()
        self.multipliers: dict[str, float] = {
            "price": 1.0,
            "location": 1.0,
            "safety": 1.0,
            "amenity": 1.0,
            "semantic": 1.0,
        }
        self.proposed_budget: Optional[float] = None
        self.hitl_streak: int = 0
        self.messages: list[BaseMessage] = []
        self.last_rooms: list[RoomItem] = []
        self.last_active: float = time.time()


class SessionMemoryManager:
    """Quản lý phiên hội thoại và duy trì trạng thái tiêu chí của người dùng."""

    def __init__(self):
        self._sessions: dict[str, SessionData] = {}

    def get_or_create_session(self, session_id: Optional[str] = None) -> SessionData:
        sid = session_id or "default_session"
        if sid not in self._sessions:
            self._sessions[sid] = SessionData(session_id=sid)
        session = self._sessions[sid]
        session.last_active = time.time()
        return session

    def clear_session(self, session_id: str) -> None:
        """Xóa session khỏi bộ nhớ khi bắt đầu phiên hội thoại mới."""
        self._sessions.pop(session_id, None)

    def update_preferences_from_text(
        self, session: SessionData, text: str, model: Any = None
    ) -> UserPreferenceState:
        """Cập nhật các tiêu chí mới từ câu nói của người dùng vào Preference State hiện tại thông qua LLM & Amenity Catalog."""
        session.preferences = extract_preferences_with_llm(
            user_text=text,
            model=model,
            current_pref=session.preferences,
        )
        return session.preferences


    def build_effective_messages(self, session: SessionData, new_user_text: str) -> list[BaseMessage]:
        """Tạo danh sách messages gửi cho model:
        - Nén context cũ (chỉ giữ MAX_HISTORY_TURNS gần nhất).
        - Tiêm (Inject) trạng thái tiêu chí tích lũy (Preference State) vào đầu ngữ cảnh.
        """
        # Cập nhật state với câu nói mới
        self.update_preferences_from_text(session, new_user_text)

        # Giữ lại số messages gần nhất để chống tràn Context Window
        trimmed_history = session.messages[-MAX_HISTORY_TURNS:] if len(session.messages) > MAX_HISTORY_TURNS else session.messages

        effective_messages: list[BaseMessage] = []

        # 1. Đưa trạng thái tích lũy vào như một System Context Note
        state_note = (
            f"[TRẠNG THÁI TIÊU CHÍ NGƯỜI DÙNG ĐÃ TÍCH LŨY (ACCUMULATED PREFERENCE STATE)]:\n"
            f"{session.preferences.to_context_string()}\n\n"
            f"HƯỚNG DẪN BỘ NHỚ: Hãy tự động KẾ THỪA các tiêu chí trên khi tìm kiếm hoặc trả lời, "
            f"trừ khi người dùng rõ ràng yêu cầu thay đổi (ví dụ: đổi địa điểm hoặc nâng ngân sách)."
        )
        effective_messages.append(HumanMessage(content=state_note))
        effective_messages.append(AIMessage(content="Tôi đã ghi nhận đầy đủ các tiêu chí tích lũy trên."))

        # 2. Nối tiếp các lượt chat trước
        effective_messages.extend(trimmed_history)

        # 3. Lượt chat hiện tại của người dùng
        effective_messages.append(HumanMessage(content=new_user_text))

        return effective_messages

    def commit_turn(self, session: SessionData, user_text: str, assistant_reply: str, rooms: list[RoomItem]) -> None:
        """Lưu lượt chat hoàn tất vào bộ nhớ phiên."""
        session.messages.append(HumanMessage(content=user_text))
        session.messages.append(AIMessage(content=assistant_reply))
        if rooms:
            session.last_rooms = rooms


# Global Singleton Manager
memory_manager = SessionMemoryManager()
