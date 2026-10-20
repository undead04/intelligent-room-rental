"""LangGraph State Machine cho Smart Housing Decision Support System (Homigo).
Quy trình gồm 7 node với Intent-Aware Dynamic Weighting, Tool Partitioning và Dynamic Skill Discovery.
"""

from __future__ import annotations

import json
import logging
import re
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
    HitlProposal,
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

from config import load_settings
from agent import build_model

logger = logging.getLogger(__name__)

_llm_model = None

def _get_llm():
    global _llm_model
    if _llm_model is None:
        try:
            settings, _ = load_settings()
            if settings:
                _llm_model = build_model(settings)
        except Exception as e:
            logger.warning(f"Không thể khởi tạo LLM cho extractor: {e}")
    return _llm_model


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
    needs_user_consent: bool
    proposed_budget: Optional[float]
    proposed_budget_str: Optional[str]
    is_keep_criteria: bool
    answer_retry_count: int
    answer_grounded: bool
    grounding_report: Optional[dict[str, Any]]
    hitl_proposal: Optional[HitlProposal]

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
    Hỗ trợ tiếp nhận phản hồi từ người dùng cho 4 lựa chọn (Nới ngân sách +15%, Mở rộng bán kính, Giữ nguyên tiêu chí, Tùy chỉnh).
    Scope: 0 Tools (Chỉ xử lý logic nội bộ và so khớp trigger).
    """
    user_text = state.get("user_message", "")
    session_id = state.get("session_id", "default_session")
    session = memory_manager.get_or_create_session(session_id)
    user_lower = user_text.lower().strip()

    # 1. Kiểm tra các ý định phản hồi lựa chọn nới lỏng từ lượt trước
    is_relax_budget = (
        user_lower.startswith("👍")
        or "đồng ý nới ngân sách" in user_lower
        or "nới ngân sách" in user_lower
        or "tăng ngân sách" in user_lower
        or "nâng ngân sách" in user_lower
        or "điều chỉnh ngân sách" in user_lower
        or "nới giá" in user_lower
        or "+15%" in user_lower
    )
    is_broaden_search = (
        user_lower.startswith("🧭")
        or "mở rộng bán kính" in user_lower
        or "tìm kiếm lân cận" in user_lower
        or "mở rộng khu vực" in user_lower
        or "khu vực lân cận" in user_lower
        or "bán kính lân cận" in user_lower
        or "toàn quận" in user_lower
    )
    is_keep_criteria = (
        user_lower.startswith("❌")
        or "giữ nguyên tiêu chí" in user_lower
        or "giữ nguyên" in user_lower
        or "không nới" in user_lower
        or "không đồng ý" in user_lower
    )
    is_dormitory_choice = (
        user_lower.startswith("🛌")
        or "ký túc xá" in user_lower
        or "ở ghép" in user_lower
        or "sleepbox" in user_lower
        or "giường tầng" in user_lower
    )
    is_reduce_amenities = (
        user_lower.startswith("🪄")
        or "lược bớt yêu cầu tiện ích" in user_lower
        or "lược bớt tiện ích" in user_lower
    )

    # Nếu người dùng chọn GIỮ NGUYÊN TIÊU CHÍ
    if is_keep_criteria:
        reply_keep = (
            "Dạ Homigo đã ghi nhận bạn muốn giữ nguyên các tiêu chí tìm kiếm ban đầu.\n\n"
            "Hiện tại trong hệ thống chưa có phòng nào đáp ứng trọn vẹn 100% các tiêu chí này. "
            "Khi có phòng mới phù hợp được đăng tải, Homigo sẽ cập nhật ngay cho bạn nhé! "
            "Bạn có thể tùy chỉnh hoặc nới lỏng tiêu chí bất cứ lúc nào."
        )
        return {
            "preferences": session.preferences,
            "final_text": reply_keep,
            "is_keep_criteria": True,
            "retrieved_rooms": [],
            "needs_clarification": False,
            "matched_skill": None,
            "is_contract_query": False,
        }

    # Nếu người dùng bấm Tùy chỉnh mà chưa nhập nội dung cụ thể
    clean_custom = user_lower.replace("✏️", "").replace("tùy chỉnh tiêu chí", "").replace("(nhập thông tin mới)", "").strip()
    if (user_lower.startswith("✏️") or user_lower == "tùy chỉnh tiêu chí") and not clean_custom:
        reply_custom = (
            "Bạn có thể nhập trực tiếp tiêu chí bạn muốn điều chỉnh vào ô chat "
            "(ví dụ: đổi khu vực sang Dĩ An, thêm tiện ích máy lạnh/gác lửng, hoặc mức giá khác) "
            "để Homigo tìm kiếm lại cho bạn nhé!"
        )
        return {
            "preferences": session.preferences,
            "final_text": reply_custom,
            "needs_clarification": True,
            "retrieved_rooms": [],
            "is_keep_criteria": False,
        }

    # Nếu người dùng ĐỒNG Ý NỚI NGÂN SÁCH (+15% hoặc theo giá sàn thị trường)
    if is_relax_budget:
        m_target = re.search(r"lên\s*(\d+(?:[.,]\d+)?)\s*(?:triệu|tr|trieu|củ)\b", user_lower)
        if m_target:
            val = float(m_target.group(1).replace(",", ".")) * 1_000_000
            new_max = val
        elif state.get("proposed_budget") or session.proposed_budget:
            new_max = float(state.get("proposed_budget") or session.proposed_budget)
        else:
            curr_max = session.preferences.max_price or 3000000
            new_max = round(curr_max * 1.15, 0)
        session.preferences.max_price = new_max
        updated_pref = session.preferences
        price_disp = f"{new_max / 1_000_000:.2f} triệu/tháng".replace(".00", "")
        explanations = [f"đã điều chỉnh ngân sách lên {price_disp} theo sự đồng ý của bạn"]
        multipliers = state.get("multipliers") or {"price": 1.5, "location": 1.2, "amenity": 1.0, "safety": 1.0}
    # Nếu người dùng CHUYỂN SANG KÝ TÚC XÁ / Ở GHÉP / SLEEPBOX
    elif is_dormitory_choice:
        session.preferences.special_requirements = list(set(session.preferences.special_requirements + ["ký túc xá", "ở ghép"]))
        updated_pref = session.preferences
        explanations = ["chuyển hướng sang tìm kiếm ký túc xá / ở ghép (sleepbox) phù hợp ngân sách sinh viên"]
        multipliers = state.get("multipliers") or {"price": 1.8, "location": 1.0, "amenity": 1.0, "safety": 1.2}
    # Nếu người dùng LƯỢC BỚT TIỆN ÍCH BẮT BUỘC
    elif is_reduce_amenities:
        session.preferences.amenities = []
        updated_pref = session.preferences
        explanations = ["đã lược bớt các yêu cầu tiện ích bắt buộc để mở rộng tập ứng viên"]
        multipliers = state.get("multipliers") or {"price": 1.2, "location": 1.2, "amenity": 1.0, "safety": 1.0}
    # Nếu người dùng MỞ RỘNG BÁN KÍNH LÂN CẬN
    elif is_broaden_search:
        session.preferences.lat = None
        session.preferences.lng = None
        updated_pref = session.preferences
        explanations = ["mở rộng phạm vi tìm kiếm sang các khu vực lân cận theo yêu cầu của bạn"]
        multipliers = state.get("multipliers") or {"price": 1.2, "location": 1.0, "amenity": 1.0, "safety": 1.0}
    else:
        # Trường hợp bình thường hoặc nhập thông tin tùy chỉnh mới: bóc tách qua LLM
        model = _get_llm()
        updated_pref = memory_manager.update_preferences_from_text(session, user_text, model=model)
        accumulated_m = state.get("multipliers") or session.multipliers
        multipliers, explanations = detect_intent_multipliers(user_text, accumulated_multipliers=accumulated_m)
        if updated_pref.amenities and multipliers.get("amenity", 1.0) < 1.5:
            multipliers["amenity"] = 1.8
            explanations.append("ưu tiên tiện nghi theo yêu cầu người dùng (boost 1.8x)")
        session.multipliers = dict(multipliers)

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
    has_loc = bool(updated_pref.location_text or (updated_pref.lat and updated_pref.lng))
    has_budget = bool(updated_pref.max_price or updated_pref.min_price)

    if (
        matched_skill
        or is_contract
        or is_relax_budget
        or is_broaden_search
        or is_keep_criteria
        or is_dormitory_choice
        or is_reduce_amenities
    ):
        needs_clarification = False
    else:
        # Bắt buộc hỏi làm rõ khi người dùng chưa cung cấp cả Vị trí lẫn Ngân sách
        # Ví dụ: "Tìm phòng trọ giúp tôi", "Có phòng nào không", "Tìm phòng trọ có máy lạnh", "Tìm phòng sinh viên"
        # Kể cả có tiện nghi nhưng chưa có khu vực/ngân sách thì vẫn phải hỏi làm rõ để tránh gợi ý lan man!
        needs_clarification = (not has_loc and not has_budget)

    return {
        "preferences": updated_pref,
        "multipliers": multipliers,
        "computed_weights": computed_weights,
        "weight_explanations": explanations,
        "needs_clarification": needs_clarification,
        "matched_skill": matched_skill,
        "is_contract_query": is_contract,
        "is_keep_criteria": False,
    }


def clarification_node(state: HousingAgentState) -> dict[str, Any]:
    """Node 3: Hỏi làm rõ khi truy vấn người dùng chưa đủ tiêu chí lọc cơ bản (Vị trí & Ngân sách).
    Scope: 0 Tools.
    """
    pref = state.get("preferences") or UserPreferenceState()

    parts = []
    if pref.amenities:
        parts.append(f"Homigo đã ghi nhận bạn đang tìm phòng ưu tiên: **{', '.join(pref.amenities)}**.")

    parts.append(
        "Chào bạn! Để Homigo có thể lọc và đề xuất phòng trọ chính xác và tối ưu nhất cho bạn, "
        "bạn vui lòng chia sẻ thêm một vài thông tin nhé:\n"
    )

    questions = []
    if not (pref.location_text or (pref.lat and pref.lng)):
        questions.append("1. **Khu vực bạn muốn ở:** Bạn muốn ở quận/huyện nào hoặc gần trường học/công ty nào (ví dụ: gần ĐH Bách Khoa, gần UIT, Quận Bình Thạnh)?")
    if not (pref.max_price or pref.min_price):
        q_num = len(questions) + 1
        questions.append(f"{q_num}. **Mức ngân sách dự kiến:** Khoảng bao nhiêu triệu/tháng (ví dụ: dưới 3.5 triệu)?")
    if not pref.amenities:
        q_num = len(questions) + 1
        questions.append(f"{q_num}. **Tiện nghi ưu tiên:** Máy lạnh, gác lửng, WC riêng, giờ giấc tự do, cho nuôi thú cưng...?")

    parts.append("\n".join(questions))
    parts.append("\n\nHomigo sẽ quét cơ sở dữ liệu và đề xuất ngay danh sách phòng tốt nhất cho bạn!")
    clarification_text = "\n".join(parts)

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
    Tuân thủ Context Grounding: Không tự động nới lỏng ngân sách ngầm khi rỗng phòng.
    """
    user_text = state.get("user_message", "")
    pref = state.get("preferences") or UserPreferenceState()
    weights = state.get("computed_weights") or {}
    multipliers = state.get("multipliers") or {}
    retry_count = state.get("retry_count", 0)
    retry_notes = list(state.get("retry_notes") or [])

    # 1. Xác định vị trí: Địa điểm cụ thể -> geocode (lat, lng); Đơn vị hành chính -> get_location_hierarchy (ID)
    city_id: Optional[int] = None
    district_id: Optional[int] = None
    ward_id: Optional[int] = None
    admin_not_found = False

    if pref.location_text and (pref.lat is None or pref.lng is None):
        try:
            geo_raw = geocode_location.invoke({"query": pref.location_text})
            geo_data = json.loads(geo_raw)
            is_admin = bool(
                geo_data.get("is_administrative")
                or (isinstance(geo_data.get("data"), dict) and geo_data["data"].get("is_administrative"))
            )
            if is_admin:
                from tools.housing_tools import get_location_hierarchy
                hier_raw = get_location_hierarchy.invoke({"city_name": pref.location_text})
                hier_data = json.loads(hier_raw)
                items = hier_data.get("data") if isinstance(hier_data, dict) else None
                if isinstance(items, list) and len(items) > 0:
                    first = items[0]
                    if hier_data.get("level") == "district" or "city_id" in first:
                        district_id = first.get("id")
                        city_id = first.get("city_id")
                    elif "district_id" in first:
                        ward_id = first.get("id")
                        district_id = first.get("district_id")
                    else:
                        city_id = first.get("id")
                else:
                    admin_not_found = True
            elif isinstance(geo_data, dict) and geo_data.get("ok"):
                inner = geo_data.get("data") if isinstance(geo_data.get("data"), dict) else geo_data
                pref.lat = inner.get("lat")
                pref.lng = inner.get("lng") if inner.get("lng") is not None else inner.get("lon")
                weights = compute_normalized_weights(pref, multipliers)
        except Exception as e:
            logger.warning(f"Lỗi xử lý vị trí {pref.location_text}: {e}")

    # 2. Sử dụng chính xác tiêu chí từ người dùng
    eff_min_price = pref.min_price
    eff_max_price = pref.max_price
    eff_amenities = pref.amenities if pref.amenities else None

    # 3. Gọi công cụ search_rooms kết hợp Rerank với Custom Weights (bỏ qua nếu khu vực hành chính chưa có trong DB)
    rooms: list[RoomItem] = []
    if not admin_not_found:
        try:
            search_args: dict[str, Any] = {
                "query": user_text,
                "lat": pref.lat,
                "lng": pref.lng,
                "min_price": eff_min_price,
                "max_price": eff_max_price,
                "amenities": eff_amenities,
                "weights": weights,
                "limit": 5,
            }
            if city_id is not None:
                search_args["city_id"] = city_id
            if district_id is not None:
                search_args["district_id"] = district_id
            if ward_id is not None:
                search_args["ward_id"] = ward_id
            if pref.room_type is not None:
                search_args["room_type"] = pref.room_type
            if pref.room_type_id is not None:
                search_args["room_type_id"] = pref.room_type_id

            res_json = search_rooms.invoke(search_args)
            data = json.loads(res_json)
            if isinstance(data, dict) and data.get("ok"):
                raw_items = data.get("data", [])
                for idx, raw in enumerate(raw_items, 1):
                    rooms.append(
                        RoomItem.from_backend_result(
                            raw,
                            rank=idx,
                            target_lat=pref.lat,
                            target_lng=pref.lng,
                        )
                    )
        except Exception as e:
            logger.warning(f"Lỗi truy vấn search_rooms: {e}")

    # 4. Kiểm định Context Grounding
    if not admin_not_found:
        ctx_check = verify_context_grounding(
            rooms,
            pref,
            retry_count=retry_count,
            last_search_args=search_args if "search_args" in locals() else None,
            area_name=pref.location_text,
        )
    else:
        from grounding import ContextGroundingResult
        ctx_check = ContextGroundingResult(
            is_grounded=True,
            context_score=1.0,
            needs_user_consent=False,
            hitl_proposal=None,
        )

    session = memory_manager.get_or_create_session(state.get("session_id", "default_session"))
    session.proposed_budget = ctx_check.proposed_budget

    if rooms:
        session.hitl_streak = 0
    elif state.get("is_keep_criteria"):
        session.hitl_streak = 0
    elif not admin_not_found:
        session.hitl_streak += 1

    return {
        "retrieved_rooms": rooms,
        "preferences": pref,
        "computed_weights": weights,
        "context_grounded": ctx_check.is_grounded,
        "retry_strategy": None,
        "retry_count": retry_count,
        "retry_notes": retry_notes,
        "needs_user_consent": ctx_check.needs_user_consent,
        "proposed_budget": ctx_check.proposed_budget,
        "proposed_budget_str": ctx_check.proposed_budget_str,
        "hitl_proposal": ctx_check.hitl_proposal,
        "admin_not_found": admin_not_found,
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
        if state.get("admin_not_found"):
            loc = (state.get("preferences") or UserPreferenceState()).location_text or "khu vực này"
            reply = (
                f"Hiện tại Homigo chưa có dữ liệu phòng trọ tại khu vực **{loc}**.\n\n"
                "Bạn vui lòng chọn một khu vực khác tại TP. Hồ Chí Minh (ví dụ: Thủ Đức, Bình Thạnh, Quận 1, v.v.) nhé!"
            )
            return {"insights": None, "final_text": reply}

        session = memory_manager.get_or_create_session(state.get("session_id", "default_session"))
        if session.hitl_streak > 2:
            reply = (
                "Homigo đã quét toàn bộ hệ thống và hỗ trợ nới lỏng nhiều tiêu chí nhưng vẫn chưa tìm thấy phòng trọ phù hợp.\n\n"
                "💡 **Khuyến nghị:** Bạn vui lòng thử đổi sang khu vực quận/huyện lân cận hoặc nhập lại yêu cầu tìm kiếm mới nhé!"
            )
        else:
            hitl = state.get("hitl_proposal")
            prop_str = state.get("proposed_budget_str")
            if hitl and hitl.message:
                reply = (
                    "Homigo đã quét toàn bộ cơ sở dữ liệu nhưng hiện chưa tìm thấy phòng trọ nào khớp 100% "
                    "với các điều kiện lọc hiện tại của bạn.\n\n"
                    f"💡 **Thực tế thị trường từ Homigo:** {hitl.message}\n\n"
                    "👉 Bạn có muốn Homigo điều chỉnh theo phương án nào dưới đây không?"
                )
            elif prop_str:
                reply = (
                    "Homigo đã quét toàn bộ cơ sở dữ liệu nhưng hiện chưa tìm thấy phòng trọ nào khớp 100% "
                    "với các điều kiện lọc hiện tại của bạn.\n\n"
                    f"💡 **Đề xuất từ Homigo:** Bạn có thể cân nhắc nới ngân sách lên khoảng **{prop_str}** "
                    "hoặc mở rộng phạm vi tìm kiếm sang các khu vực lân cận để có thêm lựa chọn tốt.\n\n"
                    "👉 Bạn có muốn Homigo điều chỉnh theo phương án nào dưới đây không?"
                )
            else:
                reply = (
                    "Homigo đã quét toàn bộ cơ sở dữ liệu nhưng hiện chưa tìm thấy phòng trọ nào khớp 100% "
                    "với các điều kiện lọc hiện tại của bạn.\n\n"
                    "💡 **Đề xuất từ Homigo:** Bạn có thể cân nhắc nới rộng ngân sách hoặc mở rộng phạm vi tìm kiếm sang các khu vực lân cận.\n\n"
                    "👉 Bạn có muốn Homigo điều chỉnh theo phương án nào dưới đây không?"
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
    next_ans_retry = ans_retry + 1 if not ans_check.is_grounded else ans_retry

    if not ans_check.is_grounded:
        retry_notes.append(f"Answer Grounding Retry #{next_ans_retry}: Phát hiện sai lệch {ans_check.issues} -> Tái tạo phản hồi chuẩn.")

    report = {
        "is_grounded": ans_check.is_grounded,
        "groundedness_score": ans_check.groundedness_score,
        "context_grounded": state.get("context_grounded", bool(rooms)),
        "needs_user_consent": state.get("needs_user_consent", False),
        "proposed_budget": state.get("proposed_budget"),
        "proposed_budget_str": state.get("proposed_budget_str"),
        "context_retries": ctx_retries,
        "answer_retries": min(next_ans_retry, MAX_GROUNDING_RETRIES),
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
    hitl_proposal = state.get("hitl_proposal")
    session = memory_manager.get_or_create_session(session_id)
    streak = session.hitl_streak

    # Tạo câu hỏi gợi mở / các nút tương tác
    if state.get("admin_not_found"):
        follow_up = [
            "🔍 Thử tìm khu vực khác (Thủ Đức, Quận 9...)",
            "✏️ Tùy chỉnh tiêu chí (Nhập thông tin mới)",
        ]
        hitl_proposal = None
        rooms = []
        insights = None
        grounding_report = {
            "is_grounded": True,
            "groundedness_score": 1.0,
            "context_grounded": False,
            "needs_user_consent": False,
            "hitl_streak": 0,
        }
    elif state.get("is_keep_criteria"):
        follow_up = [
            "🔍 Thử tìm khu vực khác",
            "✏️ Tùy chỉnh tiêu chí (Nhập thông tin mới)",
        ]
        hitl_proposal = None
        rooms = []
        insights = None
        grounding_report = {
            "is_grounded": True,
            "groundedness_score": 1.0,
            "context_grounded": False,
            "needs_user_consent": False,
            "hitl_streak": 0,
            "hitl_concluded": True,
        }
    elif need_clarification:
        follow_up = [
            "Ngân sách tối đa của bạn là bao nhiêu triệu/tháng?",
            "Bạn muốn tìm phòng gần trường học hay công ty nào?",
        ]
    elif rooms:
        follow_up = [
            "Bạn có muốn xem chi tiết thông tin liên hệ của phòng Top 1 không?",
            "Bạn có muốn so sánh chi tiết hơn với phòng Top 2 không?",
        ]
    elif streak > 2:  # MAX_HITL_STREAK = 2
        follow_up = [
            "🔄 Đổi sang khu vực tìm kiếm khác",
            "✏️ Nhập lại nhu cầu mới từ đầu",
        ]
        hitl_proposal = None
        grounding_report = {
            "is_grounded": True,
            "context_grounded": False,
            "needs_user_consent": False,
            "hitl_streak": streak,
            "hitl_limit_reached": True,
        }
    else:
        # Không tìm thấy phòng -> Cung cấp lựa chọn tương tác thông minh
        if hitl_proposal and hitl_proposal.options:
            follow_up = [opt.action_text for opt in hitl_proposal.options]
        else:
            prop_str = state.get("proposed_budget_str")
            if prop_str:
                budget_label = f"👍 Đồng ý nới ngân sách lên {prop_str} (+15%)"
            else:
                budget_label = "👍 Đồng ý nới ngân sách (+15%)"

            follow_up = [
                budget_label,
                "🧭 Mở rộng bán kính tìm kiếm lân cận",
                "❌ Giữ nguyên tiêu chí của tôi",
                "✏️ Tùy chỉnh tiêu chí (Nhập thông tin mới)",
            ]
        if hitl_proposal:
            if grounding_report is None:
                grounding_report = {}
            grounding_report["needs_user_consent"] = True
            grounding_report["hitl_streak"] = streak
            grounding_report["hitl_max_streak"] = 2

    response = AgentResponse(
        session_id=session_id,
        text_reply=final_text,
        rooms=rooms,
        insights=insights,
        current_preferences=pref,
        need_clarification=need_clarification,
        follow_up_questions=follow_up,
        grounding_report=grounding_report,
        hitl_proposal=hitl_proposal if not rooms else None,
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
    - Nếu chọn giữ nguyên tiêu chí -> Chuyển thẳng tới formatter_node.
    - Nếu khớp Kỹ năng chuyên sâu -> Chuyển thẳng tới advisory_node.
    - Nếu quá mơ hồ -> Chuyển tới clarification_node.
    - Nếu đủ thông tin tìm phòng -> Chuyển tới retrieval_node.
    """
    if state.get("is_keep_criteria"):
        return "formatter_node"
    if state.get("matched_skill") or state.get("is_contract_query"):
        return "advisory_node"
    if state.get("needs_clarification"):
        return "clarification_node"
    return "retrieval_node"


def route_after_retrieval(state: HousingAgentState) -> str:
    """Rẽ nhánh sau Retrieval:
    Luôn chuyển sang decision_node để tổng hợp kết quả (hoặc hỏi ý kiến người dùng nếu rỗng phòng).
    Tuyệt đối không tự ý quay lại retrieval_node nới lỏng ngầm.
    """
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
            "formatter_node": "formatter_node",
        },
    )

    workflow.add_conditional_edges(
        "retrieval_node",
        route_after_retrieval,
        {
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
