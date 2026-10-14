"""HousingAgentService: Service chính cung cấp API interface cho AI Agent,
kết hợp Memory & Preference State Management và Guardrails Security.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator, Generator, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from agent import build_agent, build_model
from config import load_settings
from guardrails import check_guardrails
from memory import memory_manager
from schemas import AgentResponse, DecisionInsight, RoomItem, TradeOffAnalysis

logger = logging.getLogger(__name__)


class HousingAgentService:
    def __init__(self, settings=None):
        self.settings = settings or load_settings()
        self.model = build_model(self.settings)
        self.agent = build_agent(self.model)

    def _extract_rooms_from_messages(self, messages: list[BaseMessage]) -> list[RoomItem]:
        """Trích xuất danh sách phòng từ ToolMessage của tool search_rooms."""
        rooms: list[RoomItem] = []
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage) and msg.name == "search_rooms":
                try:
                    payload = json.loads(msg.content)
                    if isinstance(payload, dict) and payload.get("ok"):
                        raw_items = payload.get("data", [])
                        if isinstance(raw_items, list):
                            for idx, raw_item in enumerate(raw_items, 1):
                                rooms.append(RoomItem.from_backend_result(raw_item, rank=idx))
                            break
                except Exception as e:
                    logger.warning(f"Lỗi parse dữ liệu từ search_rooms: {e}")
        return rooms

    def _build_decision_insights(self, rooms: list[RoomItem]) -> Optional[DecisionInsight]:
        """Tổng hợp DecisionInsight dựa trên explain_match của Top 1 và các phòng so sánh."""
        if not rooms:
            return None

        top_1 = rooms[0]
        top_explain = top_1.explain_match or {}
        top_factors = top_explain.get("top_factors", [])

        factor_vn = {
            "price": "Mức giá tối ưu",
            "location": "Vị trí gần điểm mong muốn",
            "amenity": "Đáp ứng nhiều tiện nghi",
            "safety": "Điểm an ninh khu vực cao",
            "semantic": "Khớp sát mô tả ngữ nghĩa",
        }

        key_factors = [
            factor_vn.get(f.get("name"), f.get("name"))
            for f in top_factors[:3]
            if f.get("name") in factor_vn
        ]

        reason_str = (
            f"Phòng được xếp hạng Top 1 nhờ đạt Match Score cao nhất ({top_1.matchScore}). "
            f"Trong đó các yếu tố vượt trội nhất gồm: {', '.join(key_factors) if key_factors else 'giá tốt và vị trí thuận lợi'}."
        )

        trade_offs: list[TradeOffAnalysis] = []
        if len(rooms) > 1:
            top_2 = rooms[1]
            diff_price = top_1.priceNum - top_2.priceNum
            price_adv = (
                f"Rẻ hơn {abs(diff_price) / 1_000_000:.1f} tr/tháng"
                if diff_price < 0
                else f"Đắt hơn {diff_price / 1_000_000:.1f} tr/tháng"
            )

            trade_offs.append(
                TradeOffAnalysis(
                    compared_with=f"Top 2 ({top_2.title[:35]}...)",
                    advantage=f"Top 1 có điểm tổng thể cao hơn ({top_1.matchScore} vs {top_2.matchScore}), {price_adv}.",
                    disadvantage="Top 2 có thể có vị trí hoặc diện tích khác biệt cần cân nhắc.",
                )
            )

        verification_checklist = [
            "Xác nhận lại chi phí điện nước và phí dịch vụ phát sinh (gửi xe, rác, internet).",
            "Kiểm tra thực tế tình trạng cách âm và an ninh dãy trọ.",
            "Xác nhận lại với chủ nhà về quy định nuôi thú cưng hoặc giờ giấc ra vào.",
        ]

        return DecisionInsight(
            selected_top_1_id=top_1.id,
            top_1_reason=reason_str,
            key_factors=key_factors,
            trade_offs=trade_offs,
            verification_checklist=verification_checklist,
        )

    def run(
        self,
        user_message: str,
        conversation_history: Optional[list[dict]] = None,
        session_id: Optional[str] = None,
    ) -> AgentResponse:
        """Thực thi một lượt hội thoại có bảo vệ Guardrails và duy trì Memory / Preference State."""

        # 1. BẢO VỆ GUARDRAILS (Prompt Injection & Off-topic defense)
        guard = check_guardrails(user_message)
        if not guard.allowed:
            return AgentResponse(
                text_reply=guard.safe_response or "Yêu cầu ngoài phạm vi hỗ trợ của Homigo AI.",
                rooms=[],
                need_clarification=False,
                follow_up_questions=["Bạn có muốn tìm phòng trọ gần trường học hoặc công ty nào không?"],
            )

        # 2. QUẢN LÝ BỘ NHỚ & TÍCH LŨY TIÊU CHÍ (Memory & State Management)
        session = memory_manager.get_or_create_session(session_id)

        # Nếu client truyền conversation_history riêng, đồng bộ vào session
        if conversation_history and not session.messages:
            for turn in conversation_history:
                role = turn.get("role") or turn.get("sender")
                content = turn.get("content") or turn.get("text", "")
                if role in ("user", "human"):
                    session.messages.append(HumanMessage(content=content))
                elif role in ("ai", "assistant"):
                    session.messages.append(AIMessage(content=content))

        # Xây dựng danh sách messages có nén context và tiêm Preference State
        effective_messages = memory_manager.build_effective_messages(session, user_message)

        # 3. THỰC THI QUA LANGCHAIN AGENT
        new_messages: list[BaseMessage] = []
        for mode, chunk in self.agent.stream({"messages": effective_messages}, stream_mode=["updates"]):
            if mode == "updates":
                for update in chunk.values():
                    if isinstance(update, dict) and update.get("messages"):
                        new_messages.extend(update["messages"])

        final_text = ""
        for msg in reversed(new_messages):
            if isinstance(msg, AIMessage) and msg.content:
                final_text = str(msg.content)
                break

        rooms = self._extract_rooms_from_messages(new_messages)
        insights = self._build_decision_insights(rooms) if rooms else None

        # 4. LƯU LƯỢT CHAT VÀO MEMORY
        memory_manager.commit_turn(session, user_message, final_text, rooms)

        # 5. ĐÁNH GIÁ CẦN HỎI LÀM RÕ
        has_search_tool = any(
            isinstance(m, ToolMessage) and m.name == "search_rooms" for m in new_messages
        )
        need_clarification = not has_search_tool and len(rooms) == 0 and "?" in final_text

        follow_up_questions = []
        if need_clarification:
            follow_up_questions = [
                "Ngân sách tối đa của bạn là bao nhiêu triệu/tháng?",
                "Bạn muốn tìm phòng gần trường học hay công ty nào?",
            ]
        elif rooms:
            follow_up_questions = [
                "Bạn có muốn xem chi tiết liên hệ của phòng Top 1 không?",
                "Bạn có muốn nới rộng bán kính tìm kiếm thêm 2km không?",
            ]

        return AgentResponse(
            text_reply=final_text,
            rooms=rooms,
            insights=insights,
            current_preferences=session.preferences,
            need_clarification=need_clarification,
            follow_up_questions=follow_up_questions,
        )
