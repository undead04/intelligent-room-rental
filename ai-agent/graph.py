"""LangGraph State Machine cho Smart Housing Decision Support System (Homigo).
Quy trình gồm 7 node với Intent-Aware Dynamic Weighting, Tool Partitioning và Dynamic Skill Discovery.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Mapping, Optional, Sequence, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from guardrails import GuardrailResult, check_guardrails
from grounding import (
    MAX_GROUNDING_RETRIES,
    verify_answer_grounding,
    verify_context_grounding,
)
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
from skills_discovery import match_skill_by_query
from tools import (
    ADVISORY_TOOLS,
    DETAIL_TOOLS,
    RETRIEVAL_TOOLS,
    consult_housing_skill,
    geocode_location,
    get_listing_detail,
    list_housing_skills,
    search_rooms,
)

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

    # Kỹ năng phù hợp được phát hiện qua Dynamic Skill Discovery
    matched_skill: Optional[str]

    # Cờ đánh dấu yêu cầu tư vấn hợp đồng / pháp lý (tương thích ngược)
    is_contract_query: Optional[bool]

    # Danh sách phòng sau khi Hybrid Search & Rerank từ Backend
    retrieved_rooms: list[RoomItem]

    # Trạng thái Corrective RAG Grounding & Retry
    retry_count: int
    retry_strategy: Optional[str]
    retry_notes: list[str]
    context_grounded: bool
    answer_retry_count: int
    answer_grounded: bool
    grounding_report: Optional[dict[str, Any]]

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
# Graph Nodes (Partitioned Tools Scoping)
# ---------------------------------------------------------

def guardrail_node(state: HousingAgentState) -> dict[str, Any]:
    """Node 1: Kiểm tra an toàn người dùng (Prompt Injection & Off-topic defense).
    Scope: 0 Tools (Tiết kiệm 100% token overhead).
    """
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
    """Node 2: Bóc tách nhu cầu tích lũy (Memory), Tính Trọng số Động & Dynamic Skill Discovery.
    Scope: 0 Tools (Chỉ xử lý logic nội bộ và so khớp trigger).
    """
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

    # 1. Tự động phát hiện Kỹ năng qua Dynamic Skill Discovery
    matched_meta = match_skill_by_query(user_text)
    matched_skill = matched_meta.name if matched_meta else None

    # Tương thích ngược với các từ khóa hợp đồng
    is_contract = (matched_skill == "rental-contract-advisor") or any(
        k in user_text.lower()
        for k in ["hợp đồng", "tiền cọc", "đặt cọc", "mất cọc", "pháp lý", "bẫy", "ký hợp đồng", "trả phòng"]
    )
    if is_contract and not matched_skill:
        matched_skill = "rental-contract-advisor"

    # 2. Kiểm tra truy vấn có quá mơ hồ cần hỏi làm rõ hay không
    words = user_text.strip().split()
    has_loc = bool(updated_pref.location_text or (updated_pref.lat and updated_pref.lng))
    has_budget = bool(updated_pref.max_price or updated_pref.min_price)
    has_amenity = bool(updated_pref.amenities)

    # Nếu câu hỏi khớp kỹ năng chuyên sâu -> Không hỏi làm rõ mà chuyển ngay sang advisory_node
    if matched_skill:
        needs_clarification = False
    else:
        needs_clarification = (not has_loc and not has_budget and not has_amenity and len(words) <= 4)

    return {
        "preferences": updated_pref,
        "multipliers": multipliers,
        "computed_weights": computed_weights,
        "weight_explanations": explanations,
        "needs_clarification": needs_clarification,
        "matched_skill": matched_skill,
        "is_contract_query": is_contract,
    }


def clarification_node(state: HousingAgentState) -> dict[str, Any]:
    """Node 3: Hỏi làm rõ khi truy vấn người dùng chưa đủ tiêu chí lọc cơ bản.
    Scope: 0 Tools.
    """
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


def advisory_node(state: HousingAgentState) -> dict[str, Any]:
    """Node 4: Tham vấn Kỹ năng chuyên sâu độc lập (Dynamic Skill Advisory).
    Scope: ADVISORY_TOOLS [list_housing_skills, consult_housing_skill].
    Hoàn toàn không tốn token của các công cụ tìm kiếm phòng trọ!
    """
    skill_name = state.get("matched_skill") or "rental-contract-advisor"
    user_text = state.get("user_message", "")

    # Gọi công cụ consult_housing_skill để nạp nội dung hướng dẫn nghiệp vụ
    skill_res_raw = consult_housing_skill.invoke({
        "skill_name": skill_name,
        "query": user_text,
    })
    try:
        skill_res = json.loads(skill_res_raw)
    except Exception:
        skill_res = {}

    if skill_name == "rental-contract-advisor":
        reply_lines = [
            "🛡️ **Homigo AI - Tư Vấn Hợp Đồng Thuê Trọ & Phòng Ngừa Rủi Ro (Tham vấn Skill `rental-contract-advisor`):**",
            "",
            "Khi xem xét hợp đồng thuê phòng trọ hoặc căn hộ, bạn cần đặc biệt lưu ý 5 điểm mấu chốt sau để bảo vệ quyền lợi:",
            "- **1. Tiền đặt cọc & Hoàn cọc:** Bắt buộc có điều khoản cam kết: *'Bên A hoàn trả 100% tiền cọc cho Bên B trong vòng 03 ngày làm việc kể từ ngày trả phòng và thanh toán xong điện nước'*. Tránh điều khoản ép phải tìm người thay thế mới được trả cọc.",
            "- **2. Cố định giá thuê:** Yêu cầu cam kết không tự ý tăng giá thuê trong suốt thời hạn hợp đồng.",
            "- **3. Minh bạch đơn giá điện nước & phí dịch vụ:** Ghi rõ số tiền cụ thể trên mỗi kWh điện và m³ nước (hoặc đầu người). Cam kết không phát sinh phụ phí ẩn.",
            "- **4. Biên bản hiện trạng bàn giao:** Chụp ảnh/quay video tình trạng phòng và số đo công tơ điện nước ngay ngày nhận phòng, ký xác nhận vào phụ lục.",
            "- **5. Thời hạn báo trước:** Ghi rõ hai bên có quyền chấm dứt hợp đồng nếu báo trước tối thiểu 30 ngày mà không bị phạt cọc.",
            "",
            "📋 **Khuyến nghị tiếp theo:** Bạn có thể gửi điều khoản cụ thể của chủ nhà đưa ra để Homigo thẩm định chi tiết hơn nhé!",
        ]
    else:
        # Trường hợp mở rộng cho bất kỳ kỹ năng mới nào trong tương lai
        instructions = skill_res.get("instructions", "")
        reply_lines = [
            f"💡 **Homigo AI - Tư Vấn Chuyên Sâu (Kỹ Năng `{skill_name}`):**",
            "",
            "Dựa trên cẩm nang chuyên môn nhà ở của Homigo:",
        ]
        non_empty = [
            line.strip()
            for line in instructions.splitlines()
            if line.strip() and not line.startswith("---") and not line.startswith("#")
        ]
        reply_lines.extend(non_empty[:8] if non_empty else ["Đã tham vấn thành công tài liệu chuyên môn."])
        reply_lines.append("")
        reply_lines.append("Bạn cần Homigo phân tích sâu hơn về điều khoản hoặc tiêu chí cụ thể nào không?")

    final_text = "\n".join(reply_lines)
    return {
        "final_text": final_text,
        "retrieved_rooms": [],
        "insights": None,
        "needs_clarification": False,
    }


def retrieval_node(state: HousingAgentState) -> dict[str, Any]:
    """Node 5: Truy vấn dữ liệu kết hợp Geocoding, Hybrid Search, Rerank và Context Grounding Check.
    Scope: RETRIEVAL_TOOLS [geocode_location, get_location_hierarchy, search_rooms].
    Hỗ trợ Corrective RAG Retry: Tự động nới biên độ ngân sách (±15%) hoặc mở rộng phạm vi khi kết quả rỗng.
    """
    user_text = state.get("user_message", "")
    pref = state.get("preferences") or UserPreferenceState()
    weights = state.get("computed_weights") or {}
    multipliers = state.get("multipliers") or {}
    retry_count = state.get("retry_count", 0)
    retry_strategy = state.get("retry_strategy")
    retry_notes = list(state.get("retry_notes") or [])

    # 1. Geocoding nếu có địa điểm văn bản mà chưa có toạ độ
    if pref.location_text and (pref.lat is None or pref.lng is None):
        try:
            geo_raw = geocode_location.invoke({"query": pref.location_text})
            geo_data = json.loads(geo_raw)
            if isinstance(geo_data, dict) and geo_data.get("ok"):
                inner = geo_data.get("data") if isinstance(geo_data.get("data"), dict) else geo_data
                pref.lat = inner.get("lat")
                pref.lng = inner.get("lng") if inner.get("lng") is not None else inner.get("lon")
                # Sau khi có lat, lng -> kích hoạt location weight và tính lại
                weights = compute_normalized_weights(pref, multipliers)
        except Exception as e:
            logger.warning(f"Lỗi geocode địa điểm {pref.location_text}: {e}")

    # 2. Điều chỉnh tham số lọc theo chiến lược Corrective Retry (nếu đang trong vòng lặp Retry)
    eff_min_price = pref.min_price
    eff_max_price = pref.max_price
    eff_amenities = pref.amenities if pref.amenities else None

    if retry_strategy == "relax_budget":
        if eff_max_price:
            eff_max_price = round(eff_max_price * 1.15, 0)
        if eff_min_price:
            eff_min_price = round(eff_min_price * 0.85, 0)
        retry_notes.append(f"Retry #{retry_count}: Nới biên độ ngân sách ±15% để tìm các phòng lân cận phù hợp.")
    elif retry_strategy == "broaden_search":
        eff_min_price = None
        eff_max_price = None
        eff_amenities = None
        retry_notes.append(f"Retry #{retry_count}: Mở rộng tìm kiếm ngữ nghĩa và chấm điểm mềm qua MCDM Rerank.")

    # 3. Gọi công cụ search_rooms kết hợp Rerank với Custom Weights
    rooms: list[RoomItem] = []
    api_ok = False
    try:
        search_args = {
            "query": user_text,
            "lat": pref.lat,
            "lng": pref.lng,
            "min_price": eff_min_price,
            "max_price": eff_max_price,
            "amenities": eff_amenities,
            "weights": weights,
            "limit": 5,
        }
        res_json = search_rooms.invoke(search_args)
        data = json.loads(res_json)
        if isinstance(data, dict) and data.get("ok"):
            api_ok = True
            raw_items = data.get("data", [])
            for idx, raw in enumerate(raw_items, 1):
                rooms.append(RoomItem.from_backend_result(raw, rank=idx))
    except Exception as e:
        logger.warning(f"Lỗi truy vấn search_rooms: {e}")

    # 4. Kiểm định Context Grounding (Chỉ kích hoạt retry khi API kết nối thành công nhưng kết quả chưa đạt)
    ctx_check = verify_context_grounding(rooms, pref, retry_count=retry_count)
    next_strategy = ctx_check.retry_strategy if (api_ok and not ctx_check.is_grounded and retry_count < MAX_GROUNDING_RETRIES) else None
    next_retry_count = retry_count + 1 if next_strategy else retry_count

    return {
        "retrieved_rooms": rooms,
        "preferences": pref,
        "computed_weights": weights,
        "context_grounded": ctx_check.is_grounded,
        "retry_strategy": next_strategy,
        "retry_count": next_retry_count,
        "retry_notes": retry_notes,
    }


def decision_node(state: HousingAgentState) -> dict[str, Any]:
    """Node 6: Phân tích Hỗ trợ Ra quyết định (Decision Support & Trade-offs).
    Scope: DETAIL_TOOLS [get_listing_detail].
    Nếu được gọi lại từ grounding_node (do phát hiện ảo giác ở lần sinh trước), sẽ tái tạo phản hồi bám sát 100% dữ liệu gốc.
    """
    rooms = state.get("retrieved_rooms", [])
    weights = state.get("computed_weights", {})
    explanations = state.get("weight_explanations", [])
    retry_notes = state.get("retry_notes") or []

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
    ]
    if retry_notes:
        reply_lines.append(f"*(Ghi chú Grounding: {retry_notes[-1]})*")

    reply_lines.extend([
        "",
        f"🏆 **Lựa chọn tối ưu nhất: {top_1.title}** (Điểm phù hợp: **{top_1.matchScore}**)",
        f"- **Giá thuê:** {top_1.price}",
        f"- **Địa chỉ:** {top_1.address}",
    ])
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


def grounding_node(state: HousingAgentState) -> dict[str, Any]:
    """Node 7: Kiểm định RAG Grounding & Chống ảo giác (Answer Faithfulness Check).
    Scope: 0 Tools.
    - Kiểm tra câu trả lời có bịa mã phòng (ID) hoặc mức giá không có trong retrieved_rooms hay không.
    - Nếu không hợp lệ (is_grounded=False) và còn lượt retry -> quay lại decision_node để tái tạo câu trả lời chuẩn xác.
    """
    final_text = state.get("final_text", "")
    rooms = state.get("retrieved_rooms", [])
    pref = state.get("preferences")
    ans_retry = state.get("answer_retry_count", 0)
    ctx_retries = state.get("retry_count", 0)
    retry_notes = list(state.get("retry_notes") or [])

    ans_check = verify_answer_grounding(final_text, rooms, pref)
    next_ans_retry = ans_retry + 1 if (not ans_check.is_grounded and ans_retry < MAX_GROUNDING_RETRIES) else ans_retry

    if not ans_check.is_grounded:
        retry_notes.append(f"Answer Grounding Retry #{next_ans_retry}: Phát hiện sai lệch {ans_check.issues} -> Tái tạo phản hồi chuẩn.")

    report = {
        "is_grounded": ans_check.is_grounded,
        "groundedness_score": ans_check.groundedness_score,
        "context_grounded": state.get("context_grounded", bool(rooms)),
        "context_retries": ctx_retries,
        "answer_retries": next_ans_retry,
        "retry_notes": retry_notes,
        "issues": ans_check.issues,
    }

    return {
        "answer_grounded": ans_check.is_grounded,
        "answer_retry_count": next_ans_retry,
        "retry_notes": retry_notes,
        "grounding_report": report,
    }


def formatter_node(state: HousingAgentState) -> dict[str, Any]:
    """Node 8: Đóng gói AgentResponse chuẩn cho Frontend và cập nhật Memory Session.
    Scope: 0 Tools.
    """
    final_text = state.get("final_text", "")
    rooms = state.get("retrieved_rooms", [])
    insights = state.get("insights")
    pref = state.get("preferences") or UserPreferenceState()
    need_clarification = state.get("needs_clarification", False)
    session_id = state.get("session_id", "default_session")
    grounding_report = state.get("grounding_report")

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
        session_id=session_id,
        text_reply=final_text,
        rooms=rooms,
        insights=insights,
        current_preferences=pref,
        need_clarification=need_clarification,
        follow_up_questions=follow_up,
        grounding_report=grounding_report,
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
    """Rẽ nhánh sau Preference:
    - Nếu khớp Kỹ năng chuyên sâu -> Chuyển thẳng tới advisory_node.
    - Nếu quá mơ hồ -> Chuyển tới clarification_node.
    - Nếu đủ thông tin tìm phòng -> Chuyển tới retrieval_node.
    """
    if state.get("matched_skill") or state.get("is_contract_query"):
        return "advisory_node"
    if state.get("needs_clarification"):
        return "clarification_node"
    return "retrieval_node"


def route_after_retrieval(state: HousingAgentState) -> str:
    """Rẽ nhánh sau Retrieval (Corrective RAG):
    - Nếu Context chưa đạt chuẩn Grounding và còn chiến lược retry_strategy -> Quay lại retrieval_node.
    - Ngược lại -> Sang decision_node để tổng hợp tư vấn.
    """
    if state.get("retry_strategy") and state.get("retry_count", 0) <= MAX_GROUNDING_RETRIES:
        return "retrieval_node"
    return "decision_node"


def route_after_grounding(state: HousingAgentState) -> str:
    """Rẽ nhánh sau Grounding Check (Self-RAG):
    - Nếu câu trả lời hợp lệ (answer_grounded=True) hoặc đã hết số lần retry -> Sang formatter_node trả về.
    - Nếu phát hiện ảo giác (answer_grounded=False) và còn lượt retry -> Quay lại decision_node để tạo lại câu trả lời chuẩn.
    """
    if not state.get("answer_grounded", True) and state.get("answer_retry_count", 0) <= MAX_GROUNDING_RETRIES:
        return "decision_node"
    return "formatter_node"


def build_housing_graph() -> StateGraph:
    """Khởi tạo và biên dịch StateGraph cho Housing Decision Support Agent (8 Nodes với Corrective RAG & Grounding Retry)."""
    workflow = StateGraph(HousingAgentState)

    # Đăng ký 8 Node chức năng
    workflow.add_node("guardrail_node", guardrail_node)
    workflow.add_node("preference_intent_node", preference_intent_node)
    workflow.add_node("clarification_node", clarification_node)
    workflow.add_node("advisory_node", advisory_node)
    workflow.add_node("retrieval_node", retrieval_node)
    workflow.add_node("decision_node", decision_node)
    workflow.add_node("grounding_node", grounding_node)
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
        {
            "advisory_node": "advisory_node",
            "clarification_node": "clarification_node",
            "retrieval_node": "retrieval_node",
        },
    )

    # Vòng lặp Corrective RAG ở tầng Retrieval (nếu rỗng/điểm thấp -> tự động nới điều kiện & retry)
    workflow.add_conditional_edges(
        "retrieval_node",
        route_after_retrieval,
        {
            "retrieval_node": "retrieval_node",
            "decision_node": "decision_node",
        },
    )

    workflow.add_edge("decision_node", "grounding_node")

    # Vòng lặp Self-RAG Grounding ở tầng Generation (nếu phát hiện ảo giác -> quay lại decision_node)
    workflow.add_conditional_edges(
        "grounding_node",
        route_after_grounding,
        {
            "decision_node": "decision_node",
            "formatter_node": "formatter_node",
        },
    )

    workflow.add_edge("advisory_node", "formatter_node")
    workflow.add_edge("clarification_node", "formatter_node")
    workflow.add_edge("formatter_node", END)

    return workflow.compile()


# Khởi tạo Graph Compiled dùng chung
housing_graph = build_housing_graph()
