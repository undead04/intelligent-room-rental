"""Module RAG Grounding & Corrective Retry (CRAG / Self-RAG) cho Homigo AI Agent.

Đảm bảo 2 chốt chặn chất lượng trong runtime trước khi trả kết quả về cho người dùng:
1. Context Grounding (Sau Retrieval): Kiểm tra danh sách phòng lấy về có hợp lệ và đạt ngưỡng phù hợp không.
   Nếu rỗng hoặc quá thấp do bộ lọc cứng quá chặt -> Kích hoạt Corrective Retry (nới biên độ giá ±15% hoặc mở rộng phạm vi).
2. Answer Grounding / Anti-Hallucination (Sau Decision): Kiểm tra văn bản tư vấn có trung thực 100% với
   dữ liệu phòng trong Context không (không bịa ID phòng, không bịa mức giá). Nếu vi phạm -> Retry / Sanitize.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from schemas import HitlOption, HitlProposal, RoomItem, UserPreferenceState
import json
import logging
import time

logger = logging.getLogger(__name__)

_PRICE_STATS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
CACHE_TTL_SECONDS: float = 600.0  # Cache 10 phút


def fetch_market_price_stats(
    city_id: int = 79,
    district_id: Optional[int] = None,
    room_type_id: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """Tra cứu thống kê giá phòng trực tiếp từ Backend API với in-memory cache TTL 10 phút."""
    cache_key = f"{city_id}:{district_id}:{room_type_id}"
    now = time.time()
    if cache_key in _PRICE_STATS_CACHE:
        cached_time, cached_data = _PRICE_STATS_CACHE[cache_key]
        if now - cached_time < CACHE_TTL_SECONDS:
            return cached_data

    try:
        from tools.housing_tools import get_market_price_stats
        raw_res = get_market_price_stats.invoke({
            "city_id": city_id,
            "district_id": district_id,
            "room_type_id": room_type_id,
        })
        res = json.loads(raw_res)
        if res.get("ok") and isinstance(res.get("data"), dict):
            data = res["data"]
            general = data.get("price_stats_general") or {}
            _PRICE_STATS_CACHE[cache_key] = (now, general)
            return general
    except Exception as e:
        logger.warning(f"Không thể tra cứu giá live từ Backend /price-stats: {e}")
    return None


MAX_GROUNDING_RETRIES = 2
MIN_ACCEPTABLE_MATCH_SCORE = 0.30

# Bảng tham chiếu giá sàn thị trường thực tế (VNĐ) theo khu vực để tránh nới lỏng phi thực tế
DISTRICT_PRICE_FLOORS: dict[str, dict[str, Any]] = {
    # Khu vực đắt đỏ / trung tâm TP.HCM
    "quận 1": {"min": 3500000, "avg": 5500000, "name": "Quận 1"},
    "q1": {"min": 3500000, "avg": 5500000, "name": "Quận 1"},
    "quận 3": {"min": 3500000, "avg": 5200000, "name": "Quận 3"},
    "q3": {"min": 3500000, "avg": 5200000, "name": "Quận 3"},
    "quận 10": {"min": 3000000, "avg": 4500000, "name": "Quận 10"},
    "q10": {"min": 3000000, "avg": 4500000, "name": "Quận 10"},
    "phú nhuận": {"min": 3200000, "avg": 4800000, "name": "Phú Nhuận"},
    "bình thạnh": {"min": 2800000, "avg": 4200000, "name": "Bình Thạnh"},
    "quận 7": {"min": 3000000, "avg": 4800000, "name": "Quận 7"},
    "q7": {"min": 3000000, "avg": 4800000, "name": "Quận 7"},
    "quận 5": {"min": 2800000, "avg": 4200000, "name": "Quận 5"},
    "tân bình": {"min": 2600000, "avg": 3800000, "name": "Tân Bình"},
    "tân phú": {"min": 2300000, "avg": 3400000, "name": "Tân Phú"},
    "gò vấp": {"min": 2200000, "avg": 3300000, "name": "Gò Vấp"},
    # Khu vực sinh viên & ngoại thành
    "thủ đức": {"min": 2000000, "avg": 3200000, "name": "TP. Thủ Đức"},
    "linh trung": {"min": 1800000, "avg": 2800000, "name": "Linh Trung, Thủ Đức"},
    "linh xuân": {"min": 1800000, "avg": 2600000, "name": "Linh Xuân, Thủ Đức"},
    "tăng nhơn phú": {"min": 1800000, "avg": 2700000, "name": "Tăng Nhơn Phú, Thủ Đức"},
    "làng đại học": {"min": 1600000, "avg": 2400000, "name": "Làng Đại học (ĐHQG)"},
    "uit": {"min": 1800000, "avg": 2700000, "name": "Khu vực ĐH UIT"},
    "dĩ an": {"min": 1500000, "avg": 2500000, "name": "Dĩ An, Bình Dương"},
    "quận 12": {"min": 1800000, "avg": 2800000, "name": "Quận 12"},
    "bình tân": {"min": 1800000, "avg": 2700000, "name": "Bình Tân"},
    "hóc môn": {"min": 1500000, "avg": 2400000, "name": "Hóc Môn"},
}


@dataclass
class ContextGroundingResult:
    """Kết quả kiểm định ngữ cảnh truy xuất (Retrieval Context Grounding)."""

    is_grounded: bool
    context_score: float
    retry_strategy: Optional[str] = None
    reason: str = ""
    needs_user_consent: bool = False
    proposed_budget: Optional[float] = None
    proposed_budget_str: Optional[str] = None
    hitl_proposal: Optional[HitlProposal] = None
    is_market_gap: bool = False


@dataclass
class AnswerGroundingResult:
    """Kết quả kiểm định tính xác thực của câu trả lời (Answer Faithfulness / Groundedness)."""

    is_grounded: bool
    groundedness_score: float
    issues: list[str] = field(default_factory=list)
    corrected_text: Optional[str] = None


def calculate_smart_budget_proposal(
    preferences: Optional[UserPreferenceState] = None,
    backend_lowest_price: Optional[float] = None,
    backend_avg_price: Optional[float] = None,
    area_name: Optional[str] = None,
    city_id: Optional[int] = None,
    district_id: Optional[int] = None,
    room_type_id: Optional[int] = None,
) -> dict[str, Any]:
    """Tính toán đề xuất ngân sách thông minh dựa trên dữ liệu thị trường thực tế thay vì cộng máy móc +15%."""
    if not preferences or not preferences.max_price or preferences.max_price <= 0:
        return {}

    user_max = float(preferences.max_price)
    loc_text = (preferences.location_text or area_name or "").lower().strip()

    market_min: Optional[float] = None
    market_avg: Optional[float] = None
    resolved_area: str = area_name or preferences.location_text or "khu vực bạn chọn"

    # 1. Thử lấy giá sàn thực tế từ live Backend API /price-stats
    if (not backend_lowest_price or backend_lowest_price <= 0):
        eff_city = city_id or getattr(preferences, "city_id", None) or 79
        eff_district = district_id or getattr(preferences, "district_id", None)
        eff_room_type = room_type_id or getattr(preferences, "room_type_id", None)
        if eff_district or eff_room_type:
            live_stats = fetch_market_price_stats(city_id=eff_city, district_id=eff_district, room_type_id=eff_room_type)
            if live_stats and live_stats.get("minimum_price_vnd"):
                market_min = float(live_stats["minimum_price_vnd"])
                market_avg = float(live_stats.get("average_price_vnd") or (market_min * 1.4))

    if not market_min and backend_lowest_price and backend_lowest_price > 0:
        market_min = float(backend_lowest_price)
        market_avg = float(backend_avg_price) if backend_avg_price else round(market_min * 1.4, 0)
    elif market_min is None:
        # 2. Fallback ngoại tuyến: Tra cứu từ điển DISTRICT_PRICE_FLOORS
        for k, v in DISTRICT_PRICE_FLOORS.items():
            if k in loc_text:
                market_min = float(v["min"])
                market_avg = float(v["avg"])
                resolved_area = v["name"]
                break

    if market_min is None:
        if user_max < 1500000:
            market_min = 2000000.0
            market_avg = 3200000.0
        else:
            market_min = user_max
            market_avg = round(user_max * 1.3, 0)

    is_market_gap = (user_max < market_min * 0.85)

    if is_market_gap:
        proposed_budget = market_min
        prop_val = proposed_budget / 1000000.0
        prop_str = f"{prop_val:.2f} triệu/tháng".replace(".00", "")
        label = f"👍 Đồng ý nới ngân sách lên {prop_str} (giá sàn {resolved_area})"
        suggest_dormitory = (user_max <= 2000000)
        explanation = (
            f"Tại {resolved_area}, giá phòng thấp nhất ghi nhận từ {prop_str} "
            f"(trung bình ~{market_avg / 1000000.0:.1f} triệu/tháng). "
            f"Ngân sách {user_max / 1000000.0:.2f} triệu/tháng hiện chưa đủ để tiếp cận phòng tại đây."
        )
    else:
        proposed_budget = round(user_max * 1.15, 0)
        prop_val = proposed_budget / 1000000.0
        prop_str = f"{prop_val:.2f} triệu/tháng".replace(".00", "")
        label = f"👍 Đồng ý nới ngân sách lên {prop_str} (+15%)"
        suggest_dormitory = False
        explanation = f"Có thể cân nhắc nới ngân sách lên khoảng {prop_str} (+15%) để tiếp cận thêm các lựa chọn tốt."

    return {
        "proposed_budget": proposed_budget,
        "proposed_budget_str": prop_str,
        "is_market_gap": is_market_gap,
        "area_name": resolved_area,
        "market_min_price": market_min,
        "market_min_price_str": f"{market_min / 1000000.0:.2f} triệu/tháng".replace(".00", ""),
        "market_avg_price": market_avg,
        "market_avg_price_str": f"{market_avg / 1000000.0:.1f} triệu/tháng".replace(".0", ""),
        "proposal_label": label,
        "suggest_dormitory": suggest_dormitory,
        "explanation": explanation,
        "user_budget": user_max,
        "user_budget_str": f"{user_max / 1000000.0:.2f} triệu/tháng".replace(".00", ""),
    }


def build_hitl_proposal(
    rooms: list[RoomItem],
    preferences: Optional[UserPreferenceState] = None,
    last_search_args: Optional[dict[str, Any]] = None,
    backend_lowest_price: Optional[float] = None,
    backend_avg_price: Optional[float] = None,
    area_name: Optional[str] = None,
) -> HitlProposal:
    """Tạo đối tượng HitlProposal với các tùy chọn tương tác chuyên nghiệp chuẩn Claude UI."""
    c_id = (last_search_args.get("city_id") if last_search_args else None) or (preferences.city_id if preferences else None)
    d_id = (last_search_args.get("district_id") if last_search_args else None) or (preferences.district_id if preferences else None)
    rt_id = (last_search_args.get("room_type_id") if last_search_args else None) or (preferences.room_type_id if preferences else None)

    smart = calculate_smart_budget_proposal(
        preferences=preferences,
        backend_lowest_price=backend_lowest_price,
        backend_avg_price=backend_avg_price,
        area_name=area_name,
        city_id=c_id,
        district_id=d_id,
        room_type_id=rt_id,
    )

    options: list[HitlOption] = []

    # 1. Option Điều chỉnh ngân sách
    if smart.get("proposed_budget_str"):
        if smart.get("is_market_gap"):
            options.append(
                HitlOption(
                    id="adjust_budget",
                    type="budget",
                    title="Điều chỉnh ngân sách theo thị trường",
                    description=f"Nâng ngân sách lên ~{smart['proposed_budget_str']} (giá sàn thực tế tại {smart['area_name']})",
                    badge="Đề xuất tối ưu",
                    badge_color="emerald",
                    action_text=smart["proposal_label"],
                    highlight=True,
                )
            )
        else:
            options.append(
                HitlOption(
                    id="adjust_budget",
                    type="budget",
                    title="Nới nhẹ ngân sách (+15%)",
                    description=f"Nới ngân sách lên {smart['proposed_budget_str']} để tiếp cận các phòng tốt hơn một chút",
                    badge="Nới lỏng giá",
                    badge_color="emerald",
                    action_text=smart["proposal_label"],
                    highlight=True,
                )
            )

    # 2. Option Mở rộng khu vực
    if last_search_args and last_search_args.get("ward_id") is not None:
        options.append(
            HitlOption(
                id="broaden_location",
                type="location",
                title="Mở rộng ra toàn Quận/Huyện",
                description="Tìm kiếm trên phạm vi toàn quận thay vì chỉ giới hạn trong một phường",
                badge="Giữ ngân sách",
                badge_color="blue",
                action_text="🧭 Mở rộng ra toàn Quận/Huyện thay vì chỉ 1 Phường",
            )
        )
    elif (
        (last_search_args and (last_search_args.get("district_id") is not None or last_search_args.get("lat") is not None))
        or (preferences and preferences.location_text)
        or not last_search_args
    ):
        options.append(
            HitlOption(
                id="broaden_location",
                type="location",
                title="Mở rộng bán kính tìm kiếm",
                description="Tìm kiếm ở các khu vực lân cận có mức giá mềm hơn và nhiều phòng trống hơn",
                badge="Giữ ngân sách",
                badge_color="blue",
                action_text="🧭 Mở rộng bán kính tìm kiếm lân cận",
            )
        )

    # 3. Option Ký túc xá / Ở ghép / Sleepbox nếu ngân sách thấp
    if smart.get("suggest_dormitory"):
        options.append(
            HitlOption(
                id="dormitory",
                type="room_type",
                title="Chuyển sang Ký túc xá / Ở ghép / Sleepbox",
                description="Lựa chọn khả thi nhất cho mức ngân sách sinh viên dưới 2 triệu/tháng",
                badge="Tiết kiệm chi phí",
                badge_color="amber",
                action_text="🛌 Tìm ký túc xá hoặc ở ghép (Sleepbox)",
            )
        )

    # 4. Option Lược bớt tiện ích nếu có
    req_amenities = (last_search_args.get("amenities") if last_search_args else None) or (preferences.amenities if preferences else None)
    if req_amenities:
        am_preview = ", ".join(str(a) for a in req_amenities[:2])
        options.append(
            HitlOption(
                id="reduce_amenities",
                type="amenity",
                title=f"Lược bớt yêu cầu tiện ích ({am_preview})",
                description="Bớt các tiêu chí khắt khe để tìm kiếm các phòng trọ cơ bản với giá tốt hơn",
                badge="Tối ưu bộ lọc",
                badge_color="purple",
                action_text=f"🪄 Lược bớt yêu cầu tiện ích ({am_preview})",
            )
        )

    # 5. Option Giữ nguyên tiêu chí
    options.append(
        HitlOption(
            id="keep_criteria",
            type="keep",
            title="Giữ nguyên tiêu chí của tôi",
            description="Không thay đổi điều kiện lọc, Homigo sẽ lưu nhu cầu và cập nhật khi có phòng mới",
            badge="Chờ tin mới",
            badge_color="slate",
            action_text="❌ Giữ nguyên tiêu chí của tôi",
        )
    )

    # 6. Option Tùy chỉnh tiêu chí
    options.append(
        HitlOption(
            id="custom_criteria",
            type="custom",
            title="Tùy chỉnh tiêu chí khác",
            description="Tự nhập lại khu vực mới, khoảng giá hoặc các yêu cầu đặc thù vào ô chat",
            badge="Linh hoạt",
            badge_color="orange",
            action_text="✏️ Tùy chỉnh tiêu chí (Nhập thông tin mới)",
        )
    )

    return HitlProposal(
        needed=True,
        area_name=smart.get("area_name"),
        user_budget=smart.get("user_budget"),
        user_budget_str=smart.get("user_budget_str"),
        market_min_price=smart.get("market_min_price"),
        market_min_price_str=smart.get("market_min_price_str"),
        market_avg_price=smart.get("market_avg_price"),
        market_avg_price_str=smart.get("market_avg_price_str"),
        is_market_gap=smart.get("is_market_gap", False),
        message=smart.get("explanation"),
        options=options,
    )


def verify_context_grounding(
    rooms: list[RoomItem],
    preferences: Optional[UserPreferenceState] = None,
    retry_count: int = 0,
    last_search_args: Optional[dict[str, Any]] = None,
    backend_lowest_price: Optional[float] = None,
    backend_avg_price: Optional[float] = None,
    area_name: Optional[str] = None,
) -> ContextGroundingResult:
    """Kiểm tra danh sách phòng từ Hybrid Search & Rerank có đạt chuẩn Grounding không.
    Tuyệt đối KHÔNG tự ý retry ngầm làm thay đổi ngân sách của người dùng.
    Khi kết quả rỗng, đánh dấu needs_user_consent = True để hỏi ý kiến người dùng trước.
    """
    if not rooms:
        proposal = build_hitl_proposal(
            rooms=rooms,
            preferences=preferences,
            last_search_args=last_search_args,
            backend_lowest_price=backend_lowest_price,
            backend_avg_price=backend_avg_price,
            area_name=area_name,
        )
        return ContextGroundingResult(
            is_grounded=False,
            context_score=0.0,
            retry_strategy=None,  # Không tự động lặp ngầm, chuyển sang hỏi ý kiến người dùng
            needs_user_consent=True,
            proposed_budget=proposal.market_min_price if proposal.is_market_gap else (round(preferences.max_price * 1.15, 0) if preferences and preferences.max_price else None),
            proposed_budget_str=proposal.market_min_price_str if proposal.is_market_gap else (f"{(preferences.max_price * 1.15) / 1000000:.2f} triệu/tháng".replace(".00", "") if preferences and preferences.max_price else None),
            hitl_proposal=proposal,
            is_market_gap=proposal.is_market_gap,
            reason="Không tìm thấy phòng khớp chính xác tiêu chí. Cần hỏi ý kiến người dùng để nới lỏng hoặc tùy chỉnh.",
        )

    top_score = max((r.matchScore for r in rooms), default=0.0)
    return ContextGroundingResult(
        is_grounded=True,
        context_score=round(top_score, 3),
        retry_strategy=None,
        needs_user_consent=False,
        reason="Ngữ cảnh phòng trọ hợp lệ và đạt chuẩn.",
    )



def verify_answer_grounding(
    answer_text: str,
    rooms: list[RoomItem],
    preferences: Optional[UserPreferenceState] = None,
) -> AnswerGroundingResult:
    """Kiểm tra câu trả lời của Agent có bị ảo giác (Hallucination) về mã phòng hoặc mức giá không."""
    if not answer_text.strip():
        return AnswerGroundingResult(
            is_grounded=False,
            groundedness_score=0.0,
            issues=["Câu trả lời rỗng."],
        )

    issues: list[str] = []
    known_ids = {r.id for r in rooms}
    known_prices = [r.priceNum for r in rooms if r.priceNum > 0]
    if preferences:
        if preferences.max_price:
            known_prices.append(preferences.max_price)
        if preferences.min_price:
            known_prices.append(preferences.min_price)

    # 1. Nếu không có phòng nào trong context, Agent tuyệt đối không được tự bịa ra mã phòng hoặc báo giá phòng ảo
    if not rooms:
        mentioned_ids = re.findall(r"nhatot_\d+|room-\d+", answer_text)
        if mentioned_ids:
            issues.append(f"Ảo giác mã phòng khi context rỗng: {mentioned_ids}")
        if "lựa chọn tối ưu nhất:" in answer_text.lower():
            issues.append("Ảo giác đề xuất phòng Top 1 khi danh sách phòng rỗng.")

        score = 1.0 if not issues else 0.0
        return AnswerGroundingResult(
            is_grounded=(len(issues) == 0),
            groundedness_score=score,
            issues=issues,
        )

    # 2. Kiểm tra mọi mã phòng xuất hiện trong câu trả lời phải nằm trong retrieved_rooms
    mentioned_ids = re.findall(r"nhatot_\d+", answer_text)
    for mid in mentioned_ids:
        if mid not in known_ids:
            issues.append(f"Ảo giác ID: Mã phòng '{mid}' không tồn tại trong danh sách phòng truy xuất.")

    # 3. Kiểm tra các con số giá tiền (triệu/tr) xuất hiện trong câu trả lời
    price_matches = re.findall(r"(\d+(?:[.,]\d+)?)\s*(?:triệu|tr)(?:/tháng)?", answer_text, re.IGNORECASE)
    unverified_prices: list[str] = []
    for p_str in price_matches:
        val_vnd = float(p_str.replace(",", ".")) * 1_000_000
        # Hợp lệ nếu khớp với giá của một phòng trong context, hoặc khớp với độ chênh lệch giá (trade-off diff), hoặc ngân sách user
        diffs = [
            abs(rooms[0].priceNum - r.priceNum)
            for r in rooms[1:]
            if rooms[0].priceNum > 0 and r.priceNum > 0
        ]
        all_valid_refs = known_prices + diffs
        if all_valid_refs and not any(abs(val_vnd - ref) <= 150_000 for ref in all_valid_refs):
            unverified_prices.append(f"{p_str} triệu")

    if unverified_prices:
        issues.append(f"Phát hiện mức giá không khớp dữ liệu gốc: {', '.join(unverified_prices)}")

    score = max(0.0, round(1.0 - 0.35 * len(issues), 3))
    return AnswerGroundingResult(
        is_grounded=(len(issues) == 0 and score >= 0.8),
        groundedness_score=score,
        issues=issues,
    )
