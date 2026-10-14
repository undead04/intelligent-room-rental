"""Module Memory & Preference State Management cho Smart Housing Decision Support System.
Quản lý trạng thái nhu cầu (UserPreferenceState) và cửa sổ ngữ cảnh (Context Window) qua nhiều lượt chat.
"""

from __future__ import annotations

import re
import time
from typing import Any, Optional
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from schemas import RoomItem, UserPreferenceState

MAX_HISTORY_TURNS = 8  # Tối đa 8 messages gần nhất, phần cũ hơn được nén vào Preference State


class SessionData:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.preferences = UserPreferenceState()
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

    def update_preferences_from_text(self, session: SessionData, text: str) -> UserPreferenceState:
        """Cập nhật các tiêu chí mới từ câu nói của người dùng vào Preference State hiện tại."""
        clean = text.lower()
        pref = session.preferences

        # 1. Trích xuất ngân sách tối đa
        # "dưới 3 triệu", "tối đa 3.5tr", "tầm 3tr", "khoảng 2.5 triệu"
        max_price_match = re.search(r"(?:dưới|tối đa|khoảng|tầm|tới|dưới mức)\s*(\d+(?:[.,]\d+)?)\s*(?:triệu|tr)", clean)
        if max_price_match:
            val = float(max_price_match.group(1).replace(",", ".")) * 1_000_000
            pref.max_price = val
        elif "2tr" in clean or "3tr" in clean or "4tr" in clean:
            quick_m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:triệu|tr)", clean)
            if quick_m:
                pref.max_price = float(quick_m.group(1).replace(",", ".")) * 1_000_000

        # Trích xuất ngân sách tối thiểu (nếu có: "từ 2 đến 3 triệu")
        range_match = re.search(r"từ\s*(\d+(?:[.,]\d+)?)\s*(?:đến|tới|-)\s*(\d+(?:[.,]\d+)?)\s*(?:triệu|tr)", clean)
        if range_match:
            pref.min_price = float(range_match.group(1).replace(",", ".")) * 1_000_000
            pref.max_price = float(range_match.group(2).replace(",", ".")) * 1_000_000

        # 2. Trích xuất vị trí nếu người dùng đề cập rõ
        # Kiểm tra chuyển khu vực: "đổi sang quận 9", "chuyển qua bình thạnh", "tìm ở linh xuân"
        loc_patterns = [
            r"(?:gần|ở|khu vực|tại|phường|quận|đường|quanh)\s+([a-zA-Z0-9\sàáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđĐ]+)",
        ]
        for lp in loc_patterns:
            lm = re.search(lp, text, re.IGNORECASE)
            if lm:
                cand = lm.group(1).strip()
                # Cắt bớt nếu gặp từ khóa giá hoặc tiện ích
                cand = re.split(r"(?:giá|dưới|có|khoảng|tầm|\d+tr)", cand, flags=re.IGNORECASE)[0].strip()
                if len(cand) >= 3 and not any(cand.lower().startswith(w) for w in ["máy lạnh", "gác", "nuôi", "tiền"]):
                    pref.location_text = cand
                    break

        # 3. Trích xuất tiện ích
        amenity_map = {
            "máy lạnh": "ac",
            "điều hòa": "ac",
            "gác lửng": "mezzanine",
            "gác cao": "mezzanine",
            "nuôi mèo": "pet_allowed",
            "nuôi chó": "pet_allowed",
            "thú cưng": "pet_allowed",
            "pet": "pet_allowed",
            "wifi": "wifi",
            "máy giặt": "washing_machine",
            "tủ lạnh": "fridge",
            "ban công": "balcony",
            "không chung chủ": "private_entrance",
            "giờ giấc tự do": "free_time",
            "khoá vân tay": "smart_lock",
            "bảo vệ": "security",
        }
        for kw, code in amenity_map.items():
            if kw in clean and kw not in pref.amenities:
                pref.amenities.append(kw)

        # 4. Yêu cầu đặc biệt (nhu cầu mềm)
        special_keywords = ["yên tĩnh", "thoáng mát", "sạch sẽ", "an ninh", "đường không ngập", "nấu ăn"]
        for sk in special_keywords:
            if sk in clean and sk not in pref.special_requirements:
                pref.special_requirements.append(sk)

        return pref

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
