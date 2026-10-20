"""HousingAgentService: Service chính cung cấp API interface cho AI Agent,
sử dụng trực tiếp Core Agent từ agent.py (đồng bộ 100% với Streamlit Console)
kết hợp trích xuất danh sách phòng và bảng phân tích hỗ trợ ra quyết định.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, ToolMessage

from agent import build_agent, build_model
from config import RECURSION_LIMIT, load_settings
from graph import build_decision_insights
from schemas import AgentResponse, DecisionInsight, RoomItem, UserPreferenceState
from tools.housing_tools import clear_turn_query_context, set_turn_query_context

logger = logging.getLogger(__name__)

MAX_HITL_STREAK = 2


class ChatRequest(BaseModel):
    message: str = Field(..., description="Nội dung câu hỏi hoặc yêu cầu tìm kiếm phòng của người dùng")
    conversation_history: Optional[list[dict]] = Field(default=None, description="Lịch sử chat các lượt trước")
    session_id: Optional[str] = Field(default=None, description="Mã phiên làm việc để tích lũy tiêu chí đa lượt")
    use_graph: Optional[bool] = Field(default=False, description="Tùy chọn sử dụng LangGraph State Machine (housing_graph) thay vì React Agent")


def _compact_trace_event(event_type: str, data: dict[str, Any], step: int, model_calls: int) -> dict[str, Any]:
    """Chuẩn hoá sự kiện từ ObserverMiddleware thành gói JSON gọn nhẹ cho Frontend hiển thị giống Streamlit."""
    base: dict[str, Any] = {
        "type": event_type,
        "step": step,
    }
    if event_type == "model_request":
        messages = data.get("messages", [])
        tools = data.get("tools", [])
        sys_prompt = data.get("system_prompt", "")
        msg_chars = sum(len(str(m.get("content", ""))) for m in messages if isinstance(m, dict))
        base.update({
            "model_call_index": model_calls,
            "model_name": data.get("model_name", ""),
            "message_count": len(messages),
            "tool_count": len(tools),
            "system_prompt_chars": len(sys_prompt),
            "message_chars": msg_chars,
        })
    elif event_type == "model_response":
        req_tools = data.get("tool_calls_requested") or []
        base.update({
            "model_call_index": model_calls,
            "elapsed_ms": data.get("elapsed_ms"),
            "usage": data.get("usage"),
            "tool_calls_requested": req_tools,
            "requested_tools": [tc.get("name") for tc in req_tools if isinstance(tc, dict) and tc.get("name")],
        })
    elif event_type == "tool_started":
        args = data.get("arguments") or data.get("args") or {}
        base.update({
            "tool_call_id": data.get("tool_call_id"),
            "tool_name": data.get("tool_name"),
            "arguments": args,
            "args": args,
        })
    elif event_type == "tool_finished":
        args = data.get("arguments") or data.get("args") or {}
        base.update({
            "tool_call_id": data.get("tool_call_id"),
            "tool_name": data.get("tool_name"),
            "arguments": args,
            "args": args,
            "status": data.get("status", "ok"),
            "elapsed_ms": data.get("elapsed_ms"),
            "result": data.get("result"),
            "error": data.get("error"),
        })
    return base


class HousingAgentService:
    def __init__(self, settings: Any = None):
        self.settings, _ = load_settings()
        self.model = build_model(self.settings)
        self.agent = build_agent(self.model)
        self.session_histories: dict[str, list[BaseMessage]] = {}
        self.session_hitl_streaks: dict[str, int] = {}

    def _build_decision_insights(self, rooms: list[RoomItem]) -> Optional[DecisionInsight]:
        return build_decision_insights(rooms)

    def _extract_rooms_from_messages(self, messages: list[BaseMessage]) -> list[RoomItem]:
        """Trích xuất danh sách phòng từ ToolMessage của tool search_rooms kèm khoảng cách thực tế."""
        rooms: list[RoomItem] = []
        target_lat: Optional[float] = None
        target_lng: Optional[float] = None

        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc.get("name") == "search_rooms":
                        args = tc.get("args") or {}
                        if args.get("lat") is not None and args.get("lng") is not None:
                            try:
                                target_lat = float(args["lat"])
                                target_lng = float(args["lng"])
                                break
                            except Exception:
                                pass
            elif isinstance(msg, ToolMessage) and msg.name == "geocode_location" and target_lat is None:
                try:
                    g_payload = json.loads(msg.content)
                    g_data = g_payload.get("data") if isinstance(g_payload, dict) else None
                    if isinstance(g_data, dict) and g_data.get("lat") is not None and g_data.get("lon") is not None:
                        target_lat = float(g_data["lat"])
                        target_lng = float(g_data["lon"])
                except Exception:
                    pass

        for msg in reversed(messages):
            if isinstance(msg, ToolMessage) and msg.name == "search_rooms":
                try:
                    payload = json.loads(msg.content)
                    if isinstance(payload, dict) and payload.get("ok"):
                        raw_items = payload.get("data", [])
                        if isinstance(raw_items, list):
                            for idx, raw_item in enumerate(raw_items, 1):
                                rooms.append(
                                    RoomItem.from_backend_result(
                                        raw_item,
                                        rank=idx,
                                        target_lat=target_lat,
                                        target_lng=target_lng,
                                    )
                                )
                            break
                except Exception as e:
                    logger.warning(f"Lỗi parse dữ liệu từ search_rooms: {e}")
        return rooms

    def _extract_preferences_from_tool_calls(self, messages: list[BaseMessage]) -> UserPreferenceState:
        """Trích xuất các tiêu chí tìm kiếm từ tham số gọi tool và tin nhắn người dùng."""
        import re
        pref = UserPreferenceState()
        for msg in messages:
            if isinstance(msg, HumanMessage) and isinstance(msg.content, str):
                text_low = msg.content.lower()
                m_price = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:triệu|tr|trieu|củ)\b", text_low)
                if m_price:
                    try:
                        pref.max_price = float(m_price.group(1).replace(",", ".")) * 1_000_000
                    except Exception:
                        pass
            elif isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    name = tc.get("name")
                    args = tc.get("args") or {}
                    if name == "geocode_location":
                        pref.location_text = args.get("query")
                    elif name == "get_location_hierarchy":
                        loc_parts = [
                            args.get("ward_name"),
                            args.get("district_name"),
                            args.get("city_name"),
                        ]
                        loc_str = ", ".join(str(p).strip() for p in loc_parts if p)
                        if loc_str:
                            pref.location_text = loc_str
                    elif name == "search_rooms":
                        if args.get("lat") is not None and args.get("lng") is not None:
                            try:
                                pref.lat = float(args["lat"])
                                pref.lng = float(args["lng"])
                            except Exception:
                                pass
                        if args.get("max_price"):
                            try:
                                pref.max_price = float(args["max_price"])
                            except Exception:
                                pass
                        if args.get("min_price"):
                            try:
                                pref.min_price = float(args["min_price"])
                            except Exception:
                                pass
                        if args.get("amenities"):
                            pref.amenities = list(args["amenities"])
                        if not pref.location_text and args.get("query"):
                            pref.location_text = args["query"]
        return pref

    def _prepare_history(
        self,
        user_message: str,
        conversation_history: Optional[list[dict]],
        effective_session_id: str,
    ) -> tuple[list[BaseMessage], int]:
        if conversation_history is not None and len(conversation_history) == 0:
            self.session_histories.pop(effective_session_id, None)
            self.session_hitl_streaks.pop(effective_session_id, None)

        if effective_session_id in self.session_histories:
            history: list[BaseMessage] = list(self.session_histories[effective_session_id])
        else:
            history = []
            if conversation_history:
                for turn in conversation_history:
                    role = turn.get("role") or turn.get("sender")
                    content = (turn.get("content") or turn.get("text", "")).strip()
                    if not content:
                        continue
                    if role in ("ai", "assistant") and not history and content.startswith("Chào bạn! Tôi là Trợ lý AI Tìm Trọ"):
                        continue
                    if role in ("user", "human"):
                        history.append(HumanMessage(content=content))
                    elif role in ("ai", "assistant"):
                        history.append(AIMessage(content=content))

        prev_len = len(history)
        history.append(HumanMessage(content=user_message))
        return history, prev_len

    def _finalize_response(
        self,
        effective_session_id: str,
        user_message: str,
        all_msgs: list[BaseMessage],
        prev_len: int,
        trace_events: list[dict[str, Any]],
    ) -> AgentResponse:
        from grounding import verify_answer_grounding, verify_context_grounding
        from intent_weights import compute_normalized_weights, detect_intent_multipliers

        self.session_histories[effective_session_id] = list(all_msgs)
        turn_msgs = all_msgs[prev_len:]

        rooms = self._extract_rooms_from_messages(turn_msgs)
        pref = self._extract_preferences_from_tool_calls(all_msgs)
        multipliers, weight_explanations = detect_intent_multipliers(user_message)
        computed_weights = compute_normalized_weights(pref, multipliers)
        insights = (
            build_decision_insights(
                rooms,
                weights=computed_weights,
                weight_explanations=weight_explanations,
            )
            if rooms
            else None
        )

        called_search_rooms = any(
            isinstance(m, ToolMessage) and m.name == "search_rooms"
            for m in turn_msgs
        )
        called_location_tool = any(
            isinstance(m, ToolMessage) and m.name in ("get_location_hierarchy", "geocode_location")
            for m in turn_msgs
        )

        last_search_args: dict[str, Any] = {}
        for m in reversed(turn_msgs):
            if isinstance(m, AIMessage) and m.tool_calls:
                for tc in m.tool_calls:
                    if tc.get("name") == "search_rooms":
                        last_search_args = tc.get("args") or {}
                        break
                if last_search_args:
                    break

        user_low = user_message.lower().strip()
        is_keep_criteria = (
            user_low.startswith("❌")
            or "giữ nguyên tiêu chí" in user_low
            or "không nới" in user_low
        )

        final_text = ""
        for m in reversed(turn_msgs):
            if isinstance(m, AIMessage) and not m.tool_calls:
                final_text = m.content if isinstance(m.content, str) else str(m.content)
                break
        if not final_text and all_msgs:
            last_c = all_msgs[-1].content
            final_text = last_c if isinstance(last_c, str) else str(last_c)

        has_criteria = bool(pref.location_text or pref.max_price or pref.min_price or called_search_rooms or called_location_tool)
        need_clarification = (len(rooms) == 0) and (not has_criteria)
        grounding_report = None

        hitl_proposal = None
        if is_keep_criteria:
            rooms = []
            insights = None
            self.session_hitl_streaks[effective_session_id] = 0
            follow_up = [
                "🔍 Thử tìm khu vực khác",
                "✏️ Tùy chỉnh tiêu chí (Nhập thông tin mới)",
            ]
            if not final_text or len(final_text.strip()) < 10:
                final_text = (
                    "Dạ Homigo đã ghi nhận bạn muốn giữ nguyên các tiêu chí tìm kiếm ban đầu.\n\n"
                    "Hiện tại trong hệ thống chưa có phòng nào đáp ứng trọn vẹn 100% các tiêu chí này. "
                    "Khi có phòng mới phù hợp được đăng tải, Homigo sẽ cập nhật ngay cho bạn nhé! "
                    "Bạn có thể tùy chỉnh hoặc nới lỏng tiêu chí bất cứ lúc nào."
                )
            grounding_report = {
                "is_grounded": True,
                "context_grounded": False,
                "needs_user_consent": False,
                "hitl_streak": 0,
                "hitl_concluded": True,
            }
        elif rooms:
            self.session_hitl_streaks[effective_session_id] = 0
            ans_check = verify_answer_grounding(final_text, rooms, pref)
            grounding_report = {
                "is_grounded": ans_check.is_grounded,
                "groundedness_score": ans_check.groundedness_score,
                "context_grounded": True,
                "needs_user_consent": False,
                "issues": ans_check.issues,
            }
            follow_up = [
                "Bạn có muốn xem chi tiết liên hệ phòng Top 1?",
                "Bạn có muốn lọc thêm theo tiện ích khác không?",
            ]
        elif called_search_rooms and len(rooms) == 0:
            # CHỈ kích hoạt Human-in-the-Loop khi search_rooms trả về rỗng
            streak = self.session_hitl_streaks.get(effective_session_id, 0) + 1
            self.session_hitl_streaks[effective_session_id] = streak

            if streak > MAX_HITL_STREAK:
                # Đã vượt quá giới hạn 2 lần thử nới lỏng liên tiếp -> dừng HITL
                follow_up = [
                    "🔄 Đổi sang khu vực tìm kiếm khác",
                    "✏️ Nhập lại nhu cầu mới từ đầu",
                ]
                grounding_report = {
                    "is_grounded": True,
                    "context_grounded": False,
                    "needs_user_consent": False,
                    "hitl_streak": streak,
                    "hitl_limit_reached": True,
                }
            else:
                ctx_check = verify_context_grounding(
                    rooms,
                    pref,
                    retry_count=0,
                    last_search_args=last_search_args,
                    area_name=pref.location_text,
                )
                hitl_proposal = ctx_check.hitl_proposal
                prop_str = ctx_check.proposed_budget_str

                if hitl_proposal and hitl_proposal.options:
                    follow_up = []
                    for opt in hitl_proposal.options:
                        txt = opt.action_text
                        if "nới ngân sách" in txt.lower() and "Nới ngân sách" not in txt:
                            txt = f"{txt} (Nới ngân sách)"
                        follow_up.append(txt)
                else:
                    follow_up = []
                    if pref.max_price and prop_str:
                        follow_up.append(f"👍 Nới ngân sách lên {prop_str} (+15%)")

                    if last_search_args.get("ward_id") is not None:
                        follow_up.append("🧭 Mở rộng ra toàn Quận/Huyện thay vì chỉ 1 Phường")
                    elif (
                        last_search_args.get("district_id") is not None
                        or last_search_args.get("lat") is not None
                        or pref.location_text
                    ):
                        follow_up.append("🧭 Mở rộng sang các quận/khu vực lân cận")

                    req_amenities = last_search_args.get("amenities") or pref.amenities
                    if req_amenities:
                        am_preview = ", ".join(str(a) for a in req_amenities[:2])
                        follow_up.append(f"🪄 Lược bớt yêu cầu tiện ích ({am_preview})")

                    if last_search_args.get("min_area"):
                        follow_up.append("📐 Giảm nhẹ yêu cầu diện tích tối thiểu")

                    if not follow_up:
                        follow_up.append("👍 Nới nhẹ ngân sách hoặc mở rộng bán kính tìm kiếm")

                    follow_up.append("❌ Giữ nguyên tiêu chí của tôi")
                    follow_up.append("✏️ Tùy chỉnh tiêu chí khác")

                grounding_report = {
                    "is_grounded": True,
                    "context_grounded": False,
                    "needs_user_consent": True,
                    "proposed_budget": ctx_check.proposed_budget,
                    "proposed_budget_str": prop_str,
                    "is_market_gap": ctx_check.is_market_gap,
                    "hitl_streak": streak,
                    "hitl_max_streak": MAX_HITL_STREAK,
                }
        elif called_location_tool and not called_search_rooms:
            # Vị trí trả về rỗng (ví dụ: Tỉnh/Thành chưa có dữ liệu) -> KHÔNG kích hoạt HITL
            follow_up = [
                "🔍 Tìm phòng tại TP. Thủ Đức (TP.HCM)",
                "🔍 Tìm phòng tại Quận Bình Thạnh",
                "🔍 Tìm phòng tại Đà Nẵng",
            ]
        else:
            follow_up = [
                "Khu vực Thủ Đức / Làng Đại học",
                "Khu vực Quận 1 / Bình Thạnh",
                "Ngân sách dưới 3.5 triệu/tháng",
                "Ngân sách từ 3.5 - 5 triệu/tháng",
            ]

        return AgentResponse(
            session_id=effective_session_id,
            text_reply=final_text,
            rooms=rooms,
            insights=insights,
            current_preferences=pref,
            need_clarification=need_clarification,
            follow_up_questions=follow_up,
            grounding_report=grounding_report,
            hitl_proposal=hitl_proposal if (called_search_rooms and len(rooms) == 0 and streak <= MAX_HITL_STREAK) else None,
            trace_events=trace_events,
        )

    def run(
        self,
        user_message: str,
        conversation_history: Optional[list[dict]] = None,
        session_id: Optional[str] = None,
    ) -> AgentResponse:
        """Thực thi một lượt hội thoại qua Core Agent (đồng bộ 100% với Streamlit)."""
        import uuid
        from guardrails import check_guardrails

        effective_session_id = session_id or uuid.uuid4().hex
        guard = check_guardrails(user_message)
        if not guard.allowed:
            safe_reply = guard.safe_response or "Yêu cầu ngoài phạm vi hỗ trợ của Homigo AI."
            return AgentResponse(
                session_id=effective_session_id,
                text_reply=safe_reply,
                rooms=[],
                insights=None,
                current_preferences=UserPreferenceState(),
                need_clarification=False,
                follow_up_questions=[
                    "Khu vực Thủ Đức / Làng Đại học",
                    "Ngân sách dưới 3.5 triệu/tháng",
                ],
                grounding_report={
                    "is_grounded": True,
                    "blocked_by_guardrail": True,
                    "reason": guard.reason,
                },
                hitl_proposal=None,
                trace_events=[],
            )

        history, prev_len = self._prepare_history(user_message, conversation_history, effective_session_id)
        human_texts = [
            getattr(m, "content", "")
            for m in history
            if isinstance(m, HumanMessage) and isinstance(getattr(m, "content", ""), str)
        ]

        trace_events: list[dict[str, Any]] = []
        working = list(history)
        step = 0
        model_calls = 0

        set_turn_query_context(user_message, " ; ".join(human_texts))
        try:
            stream = self.agent.stream(
                {"messages": working},
                config={"recursion_limit": RECURSION_LIMIT},
                stream_mode=["updates", "custom"],
            )
            for mode, chunk in stream:
                if mode == "custom" and isinstance(chunk, dict) and chunk.get("observer"):
                    ev_type = chunk["event"]
                    ev_data = chunk["data"]
                    step += 1
                    if ev_type == "model_request":
                        model_calls += 1
                    trace_events.append(_compact_trace_event(ev_type, ev_data, step, model_calls))
                elif mode == "updates" and isinstance(chunk, dict):
                    for update in chunk.values():
                        if isinstance(update, dict) and update.get("messages"):
                            working.extend(update["messages"])
        finally:
            clear_turn_query_context()

        return self._finalize_response(
            effective_session_id=effective_session_id,
            user_message=user_message,
            all_msgs=working,
            prev_len=prev_len,
            trace_events=trace_events,
        )

    def run_graph(
        self,
        user_message: str,
        session_id: Optional[str] = None,
    ) -> AgentResponse:
        """Thực thi qua LangGraph State Machine (housing_graph) 8 nodes."""
        import uuid
        from graph import housing_graph

        effective_session_id = session_id or uuid.uuid4().hex
        state = {
            "user_message": user_message,
            "session_id": effective_session_id,
        }
        result = housing_graph.invoke(state)
        resp = result.get("final_response")
        if isinstance(resp, AgentResponse):
            return resp
        return AgentResponse(
            session_id=effective_session_id,
            text_reply=result.get("final_text", ""),
            rooms=result.get("retrieved_rooms", []),
            insights=result.get("insights"),
        )

    def run_stream(
        self,
        user_message: str,
        conversation_history: Optional[list[dict]] = None,
        session_id: Optional[str] = None,
    ):
        """Generator phát SSE thời gian thực:
        - event: trace (model_request, model_response, tool_started, tool_finished)
        - event: text_delta (từng cụm từ trả lời của AI khi đang sinh văn bản)
        - event: done (toàn bộ AgentResponse hoàn chỉnh kèm danh sách phòng & insights)
        """
        import uuid
        from guardrails import check_guardrails

        effective_session_id = session_id or uuid.uuid4().hex
        guard = check_guardrails(user_message)
        if not guard.allowed:
            safe_reply = guard.safe_response or "Yêu cầu ngoài phạm vi hỗ trợ của Homigo AI."
            yield f"event: text_delta\ndata: {json.dumps({'delta': safe_reply}, ensure_ascii=False)}\n\n"
            blocked_resp = AgentResponse(
                session_id=effective_session_id,
                text_reply=safe_reply,
                rooms=[],
                insights=None,
                current_preferences=UserPreferenceState(),
                need_clarification=False,
                follow_up_questions=[
                    "Khu vực Thủ Đức / Làng Đại học",
                    "Ngân sách dưới 3.5 triệu/tháng",
                ],
                grounding_report={
                    "is_grounded": True,
                    "blocked_by_guardrail": True,
                    "reason": guard.reason,
                },
                hitl_proposal=None,
                trace_events=[],
            )
            yield f"event: done\ndata: {blocked_resp.model_dump_json()}\n\n"
            return

        history, prev_len = self._prepare_history(user_message, conversation_history, effective_session_id)
        human_texts = [
            getattr(m, "content", "")
            for m in history
            if isinstance(m, HumanMessage) and isinstance(getattr(m, "content", ""), str)
        ]

        trace_events: list[dict[str, Any]] = []
        working = list(history)
        step = 0
        model_calls = 0

        set_turn_query_context(user_message, " ; ".join(human_texts))
        try:
            stream = self.agent.stream(
                {"messages": working},
                config={"recursion_limit": RECURSION_LIMIT},
                stream_mode=["messages", "updates", "custom"],
            )
            for mode, chunk in stream:
                if mode == "custom" and isinstance(chunk, dict) and chunk.get("observer"):
                    ev_type = chunk["event"]
                    ev_data = chunk["data"]
                    step += 1
                    if ev_type == "model_request":
                        model_calls += 1
                    compact = _compact_trace_event(ev_type, ev_data, step, model_calls)
                    trace_events.append(compact)
                    yield f"event: trace\ndata: {json.dumps(compact, ensure_ascii=False)}\n\n"
                elif mode == "messages" and isinstance(chunk, tuple) and len(chunk) >= 1:
                    msg_chunk = chunk[0]
                    if isinstance(msg_chunk, AIMessageChunk):
                        has_tool_chunks = bool(
                            getattr(msg_chunk, "tool_call_chunks", None)
                            or getattr(msg_chunk, "tool_calls", None)
                        )
                        content = getattr(msg_chunk, "content", "")
                        if not has_tool_chunks and isinstance(content, str) and content:
                            yield f"event: text_delta\ndata: {json.dumps({'delta': content}, ensure_ascii=False)}\n\n"
                elif mode == "updates" and isinstance(chunk, dict):
                    for update in chunk.values():
                        if isinstance(update, dict) and update.get("messages"):
                            working.extend(update["messages"])

            final_resp = self._finalize_response(
                effective_session_id=effective_session_id,
                user_message=user_message,
                all_msgs=working,
                prev_len=prev_len,
                trace_events=trace_events,
            )
            yield f"event: done\ndata: {final_resp.model_dump_json()}\n\n"
        except Exception as e:
            logger.exception(f"Lỗi khi stream hội thoại AI: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            clear_turn_query_context()


# Khởi tạo singleton service dùng chung Core Agent
service = HousingAgentService()

# Khởi tạo ứng dụng FastAPI phục vụ Frontend Next.js
app = FastAPI(
    title="Homigo Smart Housing AI Agent API",
    description="Microservice cung cấp API tư vấn và hỗ trợ ra quyết định tìm phòng trọ thông minh",
    version="1.0.0",
)

# Cấu hình CORS cho phép Next.js Frontend truy vấn
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
@app.get("/health")
def health_check() -> dict[str, str]:
    """Kiểm tra tình trạng hoạt động của AI Agent service."""
    return {"status": "ok", "service": "Homigo AI Agent", "version": "1.0.0"}


@app.post("/api/v1/chat", response_model=AgentResponse)
@app.post("/chat", response_model=AgentResponse)
def chat_endpoint(request: ChatRequest) -> AgentResponse:
    """Endpoint chính nhận tin nhắn từ giao diện người dùng và trả về phản hồi kèm danh sách phòng & insight."""
    try:
        if request.use_graph:
            return service.run_graph(
                user_message=request.message,
                session_id=request.session_id,
            )
        return service.run(
            user_message=request.message,
            conversation_history=request.conversation_history,
            session_id=request.session_id,
        )
    except Exception as e:
        logger.exception(f"Lỗi khi xử lý hội thoại AI: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/chat/stream")
@app.post("/chat/stream")
def chat_stream_endpoint(request: ChatRequest) -> StreamingResponse:
    """Endpoint SSE stream từng bước suy nghĩ/gọi tool và stream từng token câu trả lời thời gian thực."""
    return StreamingResponse(
        service.run_stream(
            user_message=request.message,
            conversation_history=request.conversation_history,
            session_id=request.session_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("service:app", host="0.0.0.0", port=8001, reload=True)

