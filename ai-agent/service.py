"""HousingAgentService: Service chính cung cấp API interface cho AI Agent,
hỗ trợ cả chạy đồng bộ (invoke) và streaming sự kiện (SSE) cho Frontend.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator, Generator, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from agent import build_agent, build_model
from config import load_settings
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
        """Thực thi một lượt hội thoại đồng bộ và trả về AgentResponse chuẩn hoá."""
        messages: list[BaseMessage] = []

        if conversation_history:
            for turn in conversation_history:
                role = turn.get("role") or turn.get("sender")
                content = turn.get("content") or turn.get("text", "")
                if role in ("user", "human"):
                    messages.append(HumanMessage(content=content))
                elif role in ("ai", "assistant"):
                    messages.append(AIMessage(content=content))

        messages.append(HumanMessage(content=user_message))

        new_messages: list[BaseMessage] = []
        for mode, chunk in self.agent.stream({"messages": messages}, stream_mode=["updates"]):
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

        # Kiểm tra xem agent có đang hỏi làm rõ không
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
            need_clarification=need_clarification,
            follow_up_questions=follow_up_questions,
        )
