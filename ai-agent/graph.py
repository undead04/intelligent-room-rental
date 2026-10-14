"""LangGraph State Machine cho Smart Housing Decision Support System (Homigo).
Quy trình gồm 6 node với Intent-Aware Dynamic Weighting và Guardrails.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Mapping, Optional, Sequence, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from guardrails import GuardrailResult, check_guardrails
from intent_weights import (
    DEFAULT_BASE_WEIGHTS,
    compute_normalized_weights,
    detect_intent_multipliers,
)
from memory import SessionData, memory_manager
from schemas import (
    AgentResponse,
    DecisionInsight,
    RoomItem,
    TradeOffAnalysis,
    UserPreferenceState,
)
from tools import geocode_location, search_rooms

logger = logging.getLogger(__name__)


class HousingAgentState(TypedDict, total=False):
    """Trạng thái toàn cục luân chuyển qua các Node trong LangGraph."""

    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    user_message: str

    # Trạng thái nhu cầu tích lũy (Vị trí, ngân sách, tiện ích)
    preferences: UserPreferenceState

    # Kết quả kiểm tra Guardrail
    guardrail_result: Optional[GuardrailResult]

    # Hệ số nhân ưu tiên (Intent Multipliers)
    multipliers: dict[str, float]

    # Vector trọng số thích ứng theo ý định (Intent Weights)
    computed_weights: dict[str, float]

    # Lý do điều chỉnh trọng số (dùng giải thích cho user)
    weight_explanations: list[str]

    # Cờ đánh dấu có cần hỏi làm rõ hay không
    needs_clarification: bool

    # Danh sách phòng sau khi Hybrid Search & Rerank từ Backend
    retrieved_rooms: list[RoomItem]

    # Bảng phân tích hỗ trợ ra quyết định
    insights: Optional[DecisionInsight]

    # Câu trả lời dạng text
    final_text: str

    # Kết quả đóng gói trả về cho Frontend
    final_response: Optional[AgentResponse]


# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------

def build_decision_insights(
    rooms: list[RoomItem],
    weights: Optional[dict[str, float]] = None,
    weight_explanations: Optional[list[str]] = None,
) -> Optional[DecisionInsight]:
    """Tổng hợp DecisionInsight dựa trên explain_match của Top 1 và Intent Weights."""
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

    reason_parts = [
        f"Phòng được xếp hạng Top 1 nhờ đạt Match Score cao nhất ({top_1.matchScore}).",
    ]
    if key_factors:
        reason_parts.append(f"Các yếu tố nổi bật: {', '.join(key_factors)}.")
    if weight_explanations:
        reason_parts.append(f"Hệ thống đã tự động kích hoạt trọng số ưu tiên: {', '.join(weight_explanations)}.")

    reason_str = " ".join(reason_parts)

    trade_offs: list[TradeOffAnalysis] = []
    if len(rooms) > 1:
        top_2 = rooms[1]
        diff_price = top_1.priceNum - top_2.priceNum
        price_adv = (
            f"rẻ hơn {abs(diff_price) / 1_000_000:.1f} tr/tháng"
            if diff_price < 0
            else f"đắt hơn {diff_price / 1_000_000:.1f} tr/tháng"
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
        "Kiểm tra thực tế tình trạng cách âm và an ninh dãy trọ (camera, cổng khoá).",
        "Xác nhận lại với chủ nhà về hợp đồng cọc và giờ giấc ra vào.",
    ]

    return DecisionInsight(
        selected_top_1_id=top_1.id,
        top_1_reason=reason_str,
        key_factors=key_factors,
        trade_offs=trade_offs,
        verification_checklist=verification_checklist,
    )


# ---------------------------------------------------------
# Graph Nodes
# ---------------------------------------------------------

def guardrail_node(state: HousingAgentState) -> dict[str, Any]:
    """Node 1: Kiểm tra an toàn người dùng (Prompt Injection & Off-topic defense)."""
    user_text = state.get("user_message", "")
    guard = check_guardrails(user_text)

    if not guard.allowed:
        safe_reply = guard.safe_response or "Yêu cầu ngoài phạm vi hỗ trợ của Homigo AI."
        return {
            "guardrail_result": guard,
            "final_text": safe_reply,
            "needs_clarification": False,
            "retrieved_rooms": [],
        }

    return {"guardrail_result": guard}


def preference_intent_node(state: HousingAgentState) -> dict[str, Any]:
    """Node 2: Bóc tách nhu cầu tích lũy (Memory) & Tính toán Trọng số Động (Intent-Aware Dynamic MCDM)."""
    user_text = state.get("user_message", "")
    session_id = state.get("session_id", "default_session")
    session = memory_manager.get_or_create_session(session_id)

    # Cập nhật tiêu chí vào session
    updated_pref = memory_manager.update_preferences_from_text(session, user_text)

    # Phát hiện hệ số nhân theo ý định (Intent Multipliers)
    accumulated_m = state.get("multipliers")
    multipliers, explanations = detect_intent_multipliers(user_text, accumulated_multipliers=accumulated_m)

    # Tính toán vector trọng số chuẩn hóa
    computed_weights = compute_normalized_weights(updated_pref, multipliers)

    # Kiểm tra truy vấn có quá mơ hồ cần hỏi làm rõ hay không
    words = user_text.strip().split()
    has_loc = bool(updated_pref.location_text or (updated_pref.lat and updated_pref.lng))
    has_budget = bool(updated_pref.max_price or updated_pref.min_price)
    has_amenity = bool(updated_pref.amenities)

    # Nếu câu quá ngắn và không có bất kỳ thông tin vị trí / giá / tiện ích nào
    needs_clarification = (not has_loc and not has_budget and not has_amenity and len(words) <= 4)

    return {
        "preferences": updated_pref,
        "multipliers": multipliers,
        "computed_weights": computed_weights,
        "weight_explanations": explanations,
        "needs_clarification": needs_clarification,
    }


def clarification_node(state: HousingAgentState) -> dict[str, Any]:
    """Node 3: Hỏi làm rõ khi truy vấn người dùng chưa đủ tiêu chí lọc cơ bản."""
    clarification_text = (
        "Chào bạn! Để Homigo có thể lọc và gợi ý những phòng trọ phù hợp nhất cho bạn, "
        "bạn có thể chia sẻ thêm một vài thông tin như:\n"
        "1. Khu vực bạn muốn ở (quận, phường hoặc gần trường học/công ty nào)?\n"
        "2. Mức ngân sách dự kiến mỗi tháng (ví dụ: khoảng 3 triệu)?\n"
        "3. Các tiện nghi bạn ưu tiên (máy lạnh, gác lửng, giờ giấc tự do, cho nuôi thú cưng...)?\n\n"
        "Homigo sẽ lập tức tính toán và đề xuất phòng tối ưu cho bạn!"
    )
    return {
        "final_text": clarification_text,
        "needs_clarification": True,
        "retrieved_rooms": [],
        "insights": None,
    }


def retrieval_node(state: HousingAgentState) -> dict[str, Any]:
    """Node 4: Truy vấn dữ liệu kết hợp Geocoding, Hybrid Search và Rerank với Trọng số Động."""
    user_text = state.get("user_message", "")
    pref = state.get("preferences") or UserPreferenceState()
    weights = state.get("computed_weights") or {}
    multipliers = state.get("multipliers") or {}

    # 1. Geocoding nếu có địa điểm văn bản mà chưa có toạ độ
    if pref.location_text and (pref.lat is None or pref.lng is None):
        try:
            geo_raw = geocode_location.invoke({"address": pref.location_text})
            geo_data = json.loads(geo_raw)
            if geo_data.get("ok"):
                pref.lat = geo_data.get("lat")
                pref.lng = geo_data.get("lng")
                # Sau khi có lat, lng -> kích hoạt location weight và tính lại
                weights = compute_normalized_weights(pref, multipliers)
        except Exception as e:
            logger.warning(f"Lỗi geocode địa điểm {pref.location_text}: {e}")

    # 2. Gọi công cụ search_rooms kết hợp Rerank với Custom Weights
    rooms: list[RoomItem] = []
    try:
        search_args = {
            "query": user_text,
            "lat": pref.lat,
            "lng": pref.lng,
            "min_price": pref.min_price,
            "max_price": pref.max_price,
            "amenities": pref.amenities if pref.amenities else None,
            "weights": weights,
            "limit": 5,
        }
        res_json = search_rooms.invoke(search_args)
        data = json.loads(res_json)
        if isinstance(data, dict) and data.get("ok"):
            raw_items = data.get("data", [])
            for idx, raw in enumerate(raw_items, 1):
                rooms.append(RoomItem.from_backend_result(raw, rank=idx))
    except Exception as e:
        logger.warning(f"Lỗi truy vấn search_rooms: {e}")

    return {
        "retrieved_rooms": rooms,
        "preferences": pref,
        "computed_weights": weights,
    }


def decision_node(state: HousingAgentState) -> dict[str, Any]:
    """Node 5: Phân tích Hỗ trợ Ra quyết định (Decision Support & Trade-offs)."""
    rooms = state.get("retrieved_rooms", [])
    weights = state.get("computed_weights", {})
    explanations = state.get("weight_explanations", [])
    pref = state.get("preferences") or UserPreferenceState()

    insights = build_decision_insights(rooms, weights=weights, weight_explanations=explanations)

    if not rooms:
        reply = (
            "Homigo đã quét cơ sở dữ liệu nhưng hiện chưa tìm thấy phòng trọ nào khớp hoàn toàn "
            "với các điều kiện lọc hiện tại. Bạn có thể cân nhắc nới rộng ngân sách thêm 500k "
            "hoặc tăng bán kính tìm kiếm quanh khu vực mong muốn nhé!"
        )
        return {"insights": None, "final_text": reply}

    top_1 = rooms[0]
    weights_display = ", ".join(f"{k}: {int(v * 100)}%" for k, v in weights.items())

    reply_lines = [
        f"Dựa trên các tiêu chí và ý định của bạn, Homigo đã áp dụng mô hình phân tích đa tiêu chí (MCDM) "
        f"với các trọng số: {weights_display}.",
        "",
        f"🏆 **Lựa chọn tối ưu nhất: {top_1.title}** (Điểm phù hợp: **{top_1.matchScore}**)",
        f"- **Giá thuê:** {top_1.price}",
        f"- **Địa chỉ:** {top_1.address}",
    ]
    if insights and insights.top_1_reason:
        reply_lines.append(f"- **Lý do lựa chọn:** {insights.top_1_reason}")

    if len(rooms) > 1 and insights and insights.trade_offs:
        t = insights.trade_offs[0]
        reply_lines.extend([
            "",
            f"⚖️ **So sánh đối sánh (Trade-off):**",
            f"- So với {t.compared_with}: {t.advantage}",
        ])

    reply_lines.extend([
        "",
        "📋 **Lưu ý khi đi xem phòng:**",
        "- Kiểm tra kỹ đồng hồ điện/nước và xác nhận giá dịch vụ.",
        "- Quan sát môi trường xung quanh vào ban đêm để đánh giá an ninh.",
    ])

    final_text = "\n".join(reply_lines)
    return {"insights": insights, "final_text": final_text}


def formatter_node(state: HousingAgentState) -> dict[str, Any]:
    """Node 6: Đóng gói AgentResponse chuẩn cho Frontend và cập nhật Memory Session."""
    final_text = state.get("final_text", "")
    rooms = state.get("retrieved_rooms", [])
    insights = state.get("insights")
    pref = state.get("preferences") or UserPreferenceState()
    need_clarification = state.get("needs_clarification", False)
    session_id = state.get("session_id", "default_session")

    # Tạo câu hỏi gợi mở
    if need_clarification:
        follow_up = [
            "Ngân sách tối đa của bạn là bao nhiêu triệu/tháng?",
            "Bạn muốn tìm phòng gần trường học hay công ty nào?",
        ]
    elif rooms:
        follow_up = [
            "Bạn có muốn xem chi tiết thông tin liên hệ của phòng Top 1 không?",
            "Bạn có muốn so sánh chi tiết hơn với phòng Top 2 không?",
        ]
    else:
        follow_up = [
            "Bạn có muốn mở rộng bán kính tìm kiếm thêm 2-3km không?",
        ]

    response = AgentResponse(
        text_reply=final_text,
        rooms=rooms,
        insights=insights,
        current_preferences=pref,
        need_clarification=need_clarification,
        follow_up_questions=follow_up,
    )

    # Cập nhật vào SessionMemoryManager
    session = memory_manager.get_or_create_session(session_id)
    memory_manager.commit_turn(session, state.get("user_message", ""), final_text, rooms)

    return {
        "final_response": response,
        "messages": [AIMessage(content=final_text)],
    }


# ---------------------------------------------------------
# Graph Routing & Builder
# ---------------------------------------------------------

def route_after_guardrail(state: HousingAgentState) -> str:
    """Rẽ nhánh sau Guardrail: Nếu vi phạm thì đóng gói kết thúc, nếu an toàn thì tiếp tục."""
    res = state.get("guardrail_result")
    if res and not res.allowed:
        return "formatter_node"
    return "preference_intent_node"


def route_after_preference(state: HousingAgentState) -> str:
    """Rẽ nhánh sau Preference: Nếu quá mơ hồ thì hỏi làm rõ, nếu đủ thông tin thì truy vấn."""
    if state.get("needs_clarification"):
        return "clarification_node"
    return "retrieval_node"


def build_housing_graph() -> StateGraph:
    """Khởi tạo và biên dịch StateGraph cho Housing Decision Support Agent."""
    workflow = StateGraph(HousingAgentState)

    # Đăng ký 6 Node
    workflow.add_node("guardrail_node", guardrail_node)
    workflow.add_node("preference_intent_node", preference_intent_node)
    workflow.add_node("clarification_node", clarification_node)
    workflow.add_node("retrieval_node", retrieval_node)
    workflow.add_node("decision_node", decision_node)
    workflow.add_node("formatter_node", formatter_node)

    # Đăng ký luồng di chuyển và các cạnh điều kiện (Conditional Edges)
    workflow.add_edge(START, "guardrail_node")

    workflow.add_conditional_edges(
        "guardrail_node",
        route_after_guardrail,
        {"formatter_node": "formatter_node", "preference_intent_node": "preference_intent_node"},
    )

    workflow.add_conditional_edges(
        "preference_intent_node",
        route_after_preference,
        {"clarification_node": "clarification_node", "retrieval_node": "retrieval_node"},
    )

    workflow.add_edge("clarification_node", "formatter_node")
    workflow.add_edge("retrieval_node", "decision_node")
    workflow.add_edge("decision_node", "formatter_node")
    workflow.add_edge("formatter_node", END)

    return workflow.compile()


# Khởi tạo Graph Compiled dùng chung
housing_graph = build_housing_graph()
