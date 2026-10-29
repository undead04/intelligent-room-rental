"""RAG Grounding (CRAG / Self-RAG) cho Homigo.



Hai chốt chặn:

  1. verify_context_grounding  (sau retrieval): KIỂM RÀNG BUỘC CỨNG bằng code (giá, diện tích, loại phòng bị loại trừ) rồi

     mới quyết định có cần hỏi người dùng nới lỏng (HITL). Trước đây hàm này chỉ kiểm "rỗng hay không".

  2. verify_answer_grounding   (sau decision): kiểm ID, SỐ TIỀN (triệu/tr/k/nghìn/đ, 2tr5, 3 triệu rưỡi, 2.500.000đ), diện tích,

     định dạng; tập bằng chứng gồm cả kết quả công cụ (get_listing_detail). Có hàm critic LLM tuỳ chọn cho phát biểu định tính.



Nghiệp vụ ngân sách nằm ở domain/budget.py (thuần). File này chỉ ghép dữ liệu + trình bày.

"""



from __future__ import annotations



import json

import logging

import re

from dataclasses import dataclass, field

from typing import Any, Iterable, Optional, Sequence



from pydantic import BaseModel, Field



from intelligence.payload_builder import compact_room

from domain.budget import (

    BudgetProposal,

    MarketFetcher,

    fetch_market_stats,

    propose_budget,

)

from domain.enums import HitlAction, RoomType, amenity_label, normalize_room_type

from domain.filters import renumber

from domain.schemas import HitlOption, HitlProposal, RoomItem, UserPreferenceState, format_vnd_million



logger = logging.getLogger(__name__)



MAX_GROUNDING_RETRIES = 2

PRICE_FILTER_TOLERANCE = 0.02      # backend có thể làm tròn; cho phép lệch 2% khi kiểm ràng buộc giá

AMOUNT_TOLERANCE_VND = 50_000      # số tiền trong câu trả lời được lệch tối đa ngần này so với dữ liệu ("2.8 triệu" vs 2.75tr)

AREA_TOLERANCE_M2 = 1.0

MIN_CLAIM_VND = 10_000             # số nhỏ hơn coi là nhiễu (điểm, %, số thứ tự)





# ===========================================================================

# 1) CONTEXT GROUNDING

# ===========================================================================

@dataclass

class ContextGroundingResult:

    is_grounded: bool

    context_score: float

    retry_strategy: Optional[str] = None

    reason: str = ""

    needs_user_consent: bool = False

    proposed_budget: Optional[float] = None

    proposed_budget_str: Optional[str] = None

    hitl_proposal: Optional[HitlProposal] = None

    is_market_gap: bool = False

    valid_rooms: list[RoomItem] = field(default_factory=list)

    dropped: list[tuple[str, str]] = field(default_factory=list)   # (room_id, lý do)





def check_hard_constraints(rooms: Sequence[RoomItem], pref: Optional[UserPreferenceState]) -> tuple[list[RoomItem], list[tuple[str, str]]]:

    """Loại phòng vi phạm ràng buộc cứng. Dữ liệu thiếu (giá 0, không rõ diện tích/loại) KHÔNG bị loại vì không có căn cứ."""

    if pref is None:

        return renumber(rooms), []

    valid: list[RoomItem] = []

    dropped: list[tuple[str, str]] = []

    excluded = set(pref.excluded_room_types)

    for r in rooms:

        reason = None

        if r.priceNum > 0 and pref.max_price and r.priceNum > pref.max_price * (1 + PRICE_FILTER_TOLERANCE):

            reason = f"giá {format_vnd_million(r.priceNum)} vượt ngân sách"

        elif r.priceNum > 0 and pref.min_price and r.priceNum < pref.min_price * (1 - PRICE_FILTER_TOLERANCE):

            reason = f"giá {format_vnd_million(r.priceNum)} thấp hơn mức tối thiểu"

        elif r.area_m2 and pref.min_area and r.area_m2 < pref.min_area:

            reason = f"diện tích {r.area_m2:g}m² nhỏ hơn yêu cầu"

        elif r.area_m2 and pref.max_area and r.area_m2 > pref.max_area:

            reason = f"diện tích {r.area_m2:g}m² lớn hơn yêu cầu"

        elif r.room_type is not None and r.room_type in excluded:

            reason = f"loại phòng {r.room_type.label_vi} đã bị loại trừ"

        elif pref.amenities and r.concept_scores:

            missing_ams = []

            for am in pref.amenities:

                score = r.concept_scores.get(am.value)

                if score is not None and score < 0.5:

                    missing_ams.append(am.label_vi)

            if missing_ams:

                reason = f"thiếu tiện ích bắt buộc ({', '.join(missing_ams)})"

        if reason:

            dropped.append((r.id, reason))

        else:

            valid.append(r)

    return renumber(valid), dropped





def _search_arg(args: Optional[dict[str, Any]], key: str) -> Any:

    return (args or {}).get(key)





def _market_for(pref: Optional[UserPreferenceState], args: Optional[dict[str, Any]], fetcher: Optional[MarketFetcher]):

    city = _search_arg(args, "city_id") or (pref.city_id if pref else None)

    district = _search_arg(args, "district_id") or (pref.district_id if pref else None)

    rt = normalize_room_type(_search_arg(args, "room_type")) or (pref.room_type if pref else None)

    return fetch_market_stats(fetcher, city_id=city, district_id=district, room_type_id=rt.type_id if rt else None)





def _explanation(bp: BudgetProposal) -> str:

    prop = format_vnd_million(bp.proposed_budget)

    user = format_vnd_million(bp.user_budget)

    area = bp.area_name or "khu vực bạn chọn"

    if bp.is_market_gap and bp.market:

        avg = f" (trung bình ~{format_vnd_million(bp.market.avg_price)})" if bp.market.avg_price else ""

        return f"Tại {area}, giá phòng thấp nhất ghi nhận từ {format_vnd_million(bp.market.min_price)}{avg}. Ngân sách {user} hiện chưa đủ để tiếp cận phòng tại đây."

    return f"Có thể cân nhắc nới ngân sách lên khoảng {prop} (+15%) để tiếp cận thêm các lựa chọn tốt."





def build_hitl_proposal(

    preferences: Optional[UserPreferenceState] = None,

    last_search_args: Optional[dict[str, Any]] = None,

    area_name: Optional[str] = None,

    market_fetcher: Optional[MarketFetcher] = None,

) -> HitlProposal:

    """Danh sách lựa chọn nới lỏng. Mỗi lựa chọn có `action` (HitlAction) để frontend gửi lại trực tiếp."""

    pref = preferences or UserPreferenceState()

    args = last_search_args or {}

    market = _market_for(pref, args, market_fetcher)

    bp = propose_budget(pref.max_price, market, area_name=area_name or pref.location_text, excluded_room_types=pref.excluded_room_types)



    options: list[HitlOption] = []

    if bp:

        prop = format_vnd_million(bp.proposed_budget)

        label = f"👍 Đồng ý nới ngân sách lên {prop} (giá sàn {bp.area_name})" if bp.is_market_gap else f"👍 Đồng ý nới ngân sách lên {prop} (+15%)"

        options.append(HitlOption(

            id="adjust_budget", action=HitlAction.RELAX_BUDGET, type="budget",

            title="Điều chỉnh ngân sách theo thị trường" if bp.is_market_gap else "Nới nhẹ ngân sách (+15%)",

            description=(f"Nâng ngân sách lên ~{prop} (giá sàn thực tế tại {bp.area_name})" if bp.is_market_gap

                         else f"Nới ngân sách lên {prop} để tiếp cận các phòng tốt hơn một chút"),

            badge="Đề xuất tối ưu" if bp.is_market_gap else "Nới lỏng giá", badge_color="emerald",

            action_text=label, highlight=True,

        ))



    has_loc = bool(pref.location_text or pref.has_point or pref.has_admin or args.get("ward_id") or args.get("district_id") or args.get("lat") is not None)

    if args.get("ward_id") is not None or (not args and pref.ward_id is not None):

        options.append(HitlOption(

            id="broaden_location", action=HitlAction.BROADEN, type="location", title="Mở rộng ra toàn Quận/Huyện",

            description="Tìm kiếm trên phạm vi toàn quận thay vì chỉ giới hạn trong một phường",

            badge="Giữ ngân sách", badge_color="blue", action_text="🧭 Mở rộng ra toàn Quận/Huyện thay vì chỉ 1 Phường"))

    elif has_loc:   # chỉ gợi ý mở rộng khi THỰC SỰ có vị trí để mở rộng (bản cũ gần như luôn hiện nút này)

        options.append(HitlOption(

            id="broaden_location", action=HitlAction.BROADEN, type="location", title="Mở rộng bán kính tìm kiếm",

            description="Tìm kiếm ở các khu vực lân cận có mức giá mềm hơn và nhiều phòng trống hơn",

            badge="Giữ ngân sách", badge_color="blue", action_text="🧭 Mở rộng bán kính tìm kiếm lân cận"))



    if bp and bp.suggest_dormitory:

        options.append(HitlOption(

            id="dormitory", action=HitlAction.DORMITORY, type="room_type", title="Chuyển sang Ký túc xá / Ở ghép / Sleepbox",

            description="Lựa chọn khả thi nhất cho mức ngân sách sinh viên dưới 2 triệu/tháng",

            badge="Tiết kiệm chi phí", badge_color="amber", action_text="🛌 Tìm ký túc xá hoặc ở ghép (Sleepbox)"))



    amenities = pref.amenities or [a for a in (args.get("amenities") or [])]

    if amenities:

        preview = ", ".join(amenity_label(a) for a in amenities[:2])

        options.append(HitlOption(

            id="reduce_amenities", action=HitlAction.REDUCE_AMENITIES, type="amenity", title=f"Lược bớt yêu cầu tiện ích ({preview})",

            description="Bớt các tiêu chí khắt khe để tìm kiếm các phòng trọ cơ bản với giá tốt hơn",

            badge="Tối ưu bộ lọc", badge_color="purple", action_text=f"🪄 Lược bớt yêu cầu tiện ích ({preview})"))



    options.append(HitlOption(

        id="keep_criteria", action=HitlAction.KEEP, type="keep", title="Giữ nguyên tiêu chí của tôi",

        description="Không thay đổi điều kiện lọc, Homigo sẽ lưu nhu cầu và cập nhật khi có phòng mới",

        badge="Chờ tin mới", badge_color="slate", action_text="❌ Giữ nguyên tiêu chí của tôi"))

    options.append(HitlOption(

        id="custom_criteria", action=HitlAction.CUSTOM, type="custom", title="Tùy chỉnh tiêu chí khác",

        description="Tự nhập lại khu vực mới, khoảng giá hoặc các yêu cầu đặc thù vào ô chat",

        badge="Linh hoạt", badge_color="orange", action_text="✏️ Tùy chỉnh tiêu chí (Nhập thông tin mới)"))



    m = bp.market if bp else None

    return HitlProposal(

        needed=True,

        area_name=bp.area_name if bp else (area_name or pref.location_text),

        user_budget=bp.user_budget if bp else None, user_budget_str=format_vnd_million(bp.user_budget) if bp else None,

        market_min_price=m.min_price if m else None, market_min_price_str=format_vnd_million(m.min_price) if m else None,

        market_avg_price=m.avg_price if m else None, market_avg_price_str=format_vnd_million(m.avg_price) if m and m.avg_price else None,

        proposed_budget=bp.proposed_budget if bp else None, proposed_budget_str=format_vnd_million(bp.proposed_budget) if bp else None,

        is_market_gap=bool(bp and bp.is_market_gap),

        message=_explanation(bp) if bp else "Bạn có thể cân nhắc nới ngân sách hoặc mở rộng phạm vi tìm kiếm.",

        options=options,

    )





def verify_context_grounding(

    rooms: Sequence[RoomItem],

    preferences: Optional[UserPreferenceState] = None,

    retry_count: int = 0,

    last_search_args: Optional[dict[str, Any]] = None,

    area_name: Optional[str] = None,

    market_fetcher: Optional[MarketFetcher] = None,

) -> ContextGroundingResult:

    """Kiểm ràng buộc cứng rồi quyết định. KHÔNG tự retry ngầm làm đổi ngân sách của người dùng."""

    valid, dropped = check_hard_constraints(rooms, preferences)

    if dropped:

        logger.info("Context grounding loại %d phòng: %s", len(dropped), dropped)



    if not valid:

        proposal = build_hitl_proposal(preferences, last_search_args, area_name, market_fetcher)

        why = "Không tìm thấy phòng khớp chính xác tiêu chí." if not rooms else "Mọi phòng truy xuất đều vi phạm ràng buộc cứng."

        return ContextGroundingResult(

            is_grounded=False, context_score=0.0, needs_user_consent=True,

            proposed_budget=proposal.proposed_budget, proposed_budget_str=proposal.proposed_budget_str,

            hitl_proposal=proposal, is_market_gap=proposal.is_market_gap,

            reason=f"{why} Cần hỏi ý kiến người dùng để nới lỏng hoặc tùy chỉnh.", valid_rooms=[], dropped=dropped,

        )

    return ContextGroundingResult(

        is_grounded=True, context_score=round(max(r.matchScore for r in valid), 3),

        reason="Ngữ cảnh phòng trọ hợp lệ." + (f" Đã loại {len(dropped)} phòng vi phạm ràng buộc." if dropped else ""),

        valid_rooms=valid, dropped=dropped,

    )





def backend_market_fetcher(**kw: Any) -> Optional[dict[str, Any]]:

    """Cầu nối tới backend (import trong hàm để tránh vòng phụ thuộc grounding <-> tools). Thiếu city_id hoặc lỗi -> None."""

    from tools.housing_tools import fetch_price_stats



    return fetch_price_stats(kw.get("city_id"), kw.get("district_id"), kw.get("room_type_id"))





# ===========================================================================

# 2) ANSWER GROUNDING

# ===========================================================================

@dataclass

class AnswerGroundingResult:

    is_grounded: bool

    groundedness_score: float

    issues: list[str] = field(default_factory=list)

    checked: int = 0

    verified: int = 0

    corrected_text: Optional[str] = None





_AMOUNT_RE = re.compile(

    r"(?<![\w.,])(?:"

    r"(?P<grp>\d{1,3}(?:[.,]\d{3})+)(?:\s*(?P<gunit>đ|vnđ|vnd|đồng)(?![A-Za-zÀ-ỹ]))?"

    r"|(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>triệu|trieu|tr|củ|cu|nghìn|nghin|ngàn|ngan|k|đ|vnđ|vnd|đồng)(?![A-Za-zÀ-ỹ])"

    r"(?:\s*(?P<half>rưỡi|ruoi)|(?P<tail>\d{1,2})(?!\d))?"

    r")",

    re.IGNORECASE,

)

_AREA_RE = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s*(?:m²|m2|m\^2|mét vuông|met vuong)", re.IGNORECASE)

_RAW_INT_RE = re.compile(r"(?<![\w.,])\d{5,10}(?!\d)")

# '450m', '1.2 km', '300 mét'; KHÔNG khớp '25 m²', '25m2', '40 mét vuông'

_DIST_RE = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s*(km|kilomet|ki-lô-mét|mét|met|m)(?![\w²A-Za-zÀ-ỹ])(?!\s*(?:vuông|vuong))", re.IGNORECASE)

MIN_DISTANCE_M = 30.0

DISTANCE_REL_TOL = 0.15

DISTANCE_ABS_TOL_M = 50.0





def parse_vnd_amounts(text: str) -> list[tuple[str, float]]:

    """[(đoạn khớp, số VND)]: '2tr5'->2.5e6, '3 triệu rưỡi'->3.5e6, '800k'->8e5, '2.500.000đ'->2.5e6, '2.500.000'->2.5e6."""

    out: list[tuple[str, float]] = []

    for m in _AMOUNT_RE.finditer(text or ""):

        if m.group("grp"):

            raw = m.group("grp")

            groups = len(re.split(r"[.,]", raw)) - 1

            if not m.group("gunit") and groups < 2:   # '2.500' trần: mơ hồ (2,5?) -> bỏ qua

                continue

            val = float(re.sub(r"[.,]", "", raw))

        else:

            n = float(m.group("num").replace(",", "."))

            unit = m.group("unit").lower()

            if unit in ("triệu", "trieu", "tr", "củ", "cu"):

                val = n * 1e6 + (5e5 if m.group("half") else (float("0." + m.group("tail")) * 1e6 if m.group("tail") else 0.0))

            elif unit in ("nghìn", "nghin", "ngàn", "ngan", "k"):

                val = n * 1e3

            else:

                val = n

        val = float(round(val))                      # 2.05 triệu -> 2050000 (không phải 2049999.9999999998)

        if val >= MIN_CLAIM_VND:

            out.append((m.group(0).strip(), val))

    return out





def parse_distances(text: str) -> list[tuple[str, float]]:

    """[(đoạn khớp, mét)]: '450m'->450, '1.2 km'->1200, '300 mét'->300. Bỏ qua giá trị < 30m (nhiễu)."""

    out = []

    for m in _DIST_RE.finditer(text or ""):

        v = float(m.group(1).replace(",", "."))

        meters = v * 1000 if m.group(2).lower() in ("km", "kilomet", "ki-lô-mét") else v

        if meters >= MIN_DISTANCE_M:

            out.append((m.group(0).strip(), round(meters, 1)))

    return out





def parse_areas(text: str) -> list[tuple[str, float]]:

    return [(m.group(0).strip(), float(m.group(1).replace(",", "."))) for m in _AREA_RE.finditer(text or "")]





def _evidence_amounts(rooms: Sequence[RoomItem], pref: Optional[UserPreferenceState], extra_texts: Iterable[str], extra_amounts: Iterable[float], user_text: str = "") -> list[float]:
    ev: list[float] = []
    prices = [r.priceNum for r in rooms if r.priceNum > 0]
    ev.extend(prices)
    ev.extend(abs(a - b) for i, a in enumerate(prices) for b in prices[i + 1:])        # chênh lệch giá giữa mọi cặp
    user_lower = (user_text or "").lower()
    if any(w in user_lower for w in ("2 người", "hai người", "gấp đôi", "nhân đôi", "ở 2", "3 người", "ba người", "gấp ba")):
        for p in prices:                                                                # hỗ trợ bội số người ở khi người dùng hỏi
            ev.append(p * 2)
            ev.append(p * 3)
    for r in rooms:

        for field_text in (r.price, r.title, r.address):      # code render nguyên văn các trường này

            ev.extend(v for _, v in parse_vnd_amounts(field_text))

    if pref:

        ev.extend(v for v in (pref.max_price, pref.min_price) if v)

    ev.extend(float(a) for a in extra_amounts if a)

    for t in extra_texts:                                                              # kết quả công cụ (tiền cọc, phí dịch vụ...)

        ev.extend(v for _, v in parse_vnd_amounts(t))

        ev.extend(float(x.group(0)) for x in _RAW_INT_RE.finditer(t))

    return [v for v in ev if v >= MIN_CLAIM_VND]





def _evidence_areas(rooms: Sequence[RoomItem], pref: Optional[UserPreferenceState], extra_texts: Iterable[str]) -> list[float]:

    ev = [r.area_m2 for r in rooms if r.area_m2]

    base = list(ev)                                                                   # chụp trước: không extend khi đang lặp chính nó

    ev.extend(abs(a - b) for i, a in enumerate(base) for b in base[i + 1:])           # chênh lệch diện tích giữa mọi cặp

    for r in rooms:

        for field_text in (r.title, r.address):

            ev.extend(v for _, v in parse_areas(field_text))

    if pref:

        ev.extend(v for v in (pref.min_area, pref.max_area) if v)

    for t in extra_texts:

        ev.extend(v for _, v in parse_areas(t))

    return ev





def _evidence_distances(rooms: Sequence[RoomItem], extra_texts: Iterable[str]) -> list[float]:

    ev = [v for r in rooms for _, v in parse_distances(r.distance)]

    for t in extra_texts:

        ev.extend(v for _, v in parse_distances(t))

    return ev





def _id_pattern(known_ids: Iterable[str]) -> re.Pattern[str]:

    prefixes = {"nhatot", "room"}

    for i in known_ids:

        m = re.match(r"([A-Za-z]+)(?=[_-]\d)", i)

        if m:

            prefixes.add(m.group(1).lower())

    return re.compile(r"(?<![\w-])(?:" + "|".join(sorted(map(re.escape, prefixes))) + r")[_-]\d+\b", re.IGNORECASE)





def find_format_violations(text: str) -> list[str]:

    """Prompt cấm bảng Markdown và đường kẻ ngang: kiểm bằng code thay vì tin LLM."""

    issues = []

    for line in (text or "").splitlines():

        s = line.strip()

        if s in ("---", "***", "___"):

            issues.append("Định dạng: dùng đường kẻ ngang")

        elif s.startswith("|") and s.endswith("|") and s.count("|") >= 2:

            issues.append("Định dạng: dùng bảng Markdown")

    return list(dict.fromkeys(issues))





def verify_answer_grounding(

    answer_text: str,

    rooms: Sequence[RoomItem],

    preferences: Optional[UserPreferenceState] = None,

    *,

    extra_texts: Iterable[str] = (),

    extra_amounts: Iterable[float] = (),

    user_text: str = "",

) -> AnswerGroundingResult:

    """Kiểm câu trả lời bằng CODE: mã phòng, số tiền, diện tích, định dạng.



    extra_texts: nội dung ToolMessage trong lượt (get_listing_detail...) -> số liệu từ đó là hợp lệ.

    user_text: câu của người dùng; số họ tự nêu ("trong bán kính 1km") được phép lặp lại trong câu trả lời.

    extra_amounts: các số tiền hệ thống vừa đề xuất (ví dụ proposed_budget) -> được phép xuất hiện.

    """

    if not (answer_text or "").strip():

        return AnswerGroundingResult(False, 0.0, ["Câu trả lời rỗng."])

    extra_texts = list(extra_texts) + ([user_text] if user_text else [])

    issues: list[str] = []

    checked = verified = 0



    # --- mã phòng

    known = {r.id.lower() for r in rooms}

    for mid in dict.fromkeys(x.group(0) for x in _id_pattern(r.id for r in rooms).finditer(answer_text)):

        checked += 1

        if mid.lower() in known:

            verified += 1

        else:

            issues.append(f"Ảo giác mã phòng: '{mid}' không có trong dữ liệu truy xuất.")



    # --- số tiền

    refs = _evidence_amounts(rooms, preferences, extra_texts, extra_amounts, user_text=user_text)

    bad_amounts = []

    for raw, val in parse_vnd_amounts(answer_text):

        checked += 1

        if any(abs(val - r) <= AMOUNT_TOLERANCE_VND for r in refs):

            verified += 1

        else:

            bad_amounts.append(raw)

    if bad_amounts:

        issues.append(f"Số tiền không khớp dữ liệu gốc: {', '.join(dict.fromkeys(bad_amounts))}")



    # --- diện tích

    area_refs = _evidence_areas(rooms, preferences, extra_texts)

    bad_areas = []

    for raw, val in parse_areas(answer_text):

        checked += 1

        if any(abs(val - a) <= AREA_TOLERANCE_M2 for a in area_refs):

            verified += 1

        else:

            bad_areas.append(raw)

    if bad_areas:

        issues.append(f"Diện tích không khớp dữ liệu gốc: {', '.join(dict.fromkeys(bad_areas))}")



    # --- khoảng cách

    dist_refs = _evidence_distances(rooms, extra_texts)

    bad_dist = []

    for raw, val in parse_distances(answer_text):

        checked += 1

        if any(abs(val - d) <= max(DISTANCE_ABS_TOL_M, DISTANCE_REL_TOL * d) for d in dist_refs):

            verified += 1

        else:

            bad_dist.append(raw)

    if bad_dist:

        issues.append(f"Khoảng cách không khớp dữ liệu gốc: {', '.join(dict.fromkeys(bad_dist))}")




    # --- kiểm tra ràng buộc thuộc tính theo phạm vi thực thể (Scope Binding)
    clauses = [p.strip() for p in re.split(r"(?<!\d)[.!?\n]+(?!\d)", answer_text) if p.strip()]
    comp_keywords = ("rẻ hơn", "re hon", "đắt hơn", "dat hon", "chênh lệch", "chenh lech", "tiết kiệm", "tiet kiem", "bớt", "bot", "nhỏ hơn", "nho hon", "rộng hơn", "rong hon")
    scope_issues = []
    for clause in clauses:
        sub_clauses = [clause] if "," not in clause else [c.strip() for c in clause.split(",") if c.strip()]
        for sub in sub_clauses:
            m_rooms = [r for r in rooms if r.id.lower() in sub.lower()]
            if len(m_rooms) == 1:
                target = m_rooms[0]
                has_comp = any(k in sub.lower() for k in comp_keywords)
                for raw, val in parse_vnd_amounts(sub):
                    matches_target = abs(val - target.priceNum) <= AMOUNT_TOLERANCE_VND
                    if not matches_target and not has_comp:
                        other_match = [r for r in rooms if r.id != target.id and abs(val - r.priceNum) <= AMOUNT_TOLERANCE_VND]
                        if other_match:
                            scope_issues.append(f"Gán nhầm số tiền: '{raw}' là giá của phòng '{other_match[0].id}', không phải của '{target.id}'.")
                for raw, val in parse_areas(sub):
                    matches_target = target.area_m2 and abs(val - target.area_m2) <= AREA_TOLERANCE_M2
                    if not matches_target and not has_comp:
                        other_match = [r for r in rooms if r.id != target.id and r.area_m2 and abs(val - r.area_m2) <= AREA_TOLERANCE_M2]
                        if other_match:
                            scope_issues.append(f"Gán nhầm diện tích: '{raw}' là diện tích của phòng '{other_match[0].id}', không phải của '{target.id}'.")
    if scope_issues:
        issues.extend(dict.fromkeys(scope_issues))

    issues.extend(find_format_violations(answer_text))

    score = 1.0 if checked == 0 else round(verified / checked, 3)

    return AnswerGroundingResult(is_grounded=not issues, groundedness_score=score if not issues else min(score, 0.99), issues=issues, checked=checked, verified=verified)





# ---------------------------------------------------------------------------

# Critic LLM (tuỳ chọn): phát biểu ĐỊNH TÍNH về phòng mà code không kiểm được ("yên tĩnh", "gần chợ"...)

# ---------------------------------------------------------------------------

class ClaimsReport(BaseModel):

    unsupported_claims: list[str] = Field(default_factory=list, description="Phát biểu về phòng KHÔNG có căn cứ trong dữ liệu")





def critic_unsupported_claims(model: Any, answer_text: str, rooms: Sequence[RoomItem], extra_texts: Iterable[str] = ()) -> list[str]:

    """Chạy SAU khi kiểm tra bằng code đã qua. Lỗi/không có model -> [] (không chặn)."""

    if model is None or not (answer_text or "").strip():

        return []

    data = json.dumps([compact_room(r) for r in rooms], ensure_ascii=False)

    tool_data = "\n".join(extra_texts)[:6000]

    try:

        rep = model.with_structured_output(ClaimsReport).invoke([

            ("system", "Bạn là người kiểm chứng. Liệt kê các phát biểu cụ thể về phòng trong <answer> mà KHÔNG được hỗ trợ bởi <rooms_data> "

                       "hoặc <tool_data>. Bỏ qua lời khuyên chung, lời chào, và phần gợi ý cần tự kiểm tra khi đi xem phòng. "

                       "Không có thì trả danh sách rỗng."),

            ("human", f"<rooms_data>\n{data}\n</rooms_data>\n<tool_data>\n{tool_data}\n</tool_data>\n<answer>\n{answer_text}\n</answer>"),

        ])

        rep = rep if isinstance(rep, ClaimsReport) else ClaimsReport.model_validate(rep)

        return [c for c in rep.unsupported_claims if c.strip()][:5]

    except Exception:

        logger.warning("critic_unsupported_claims lỗi, bỏ qua", exc_info=True)

        return []



class CriticVerificationReport(BaseModel):
    unsupported_claims: list[str] = Field(default_factory=list, description="Phát biểu về phòng KHÔNG có căn cứ trong dữ liệu")
    unaddressed_questions: list[str] = Field(default_factory=list, description="Câu hỏi hoặc yêu cầu cụ thể của người dùng trong <user_query> mà <answer> bỏ qua hoặc trả lời lạc đề")


def critic_answer_validation(
    model: Any,
    answer_text: str,
    rooms: Sequence[RoomItem],
    extra_texts: Iterable[str] = (),
    user_text: str = "",
) -> CriticVerificationReport:
    """Kiểm tra 2 chiều ở runtime:
    1. Groundedness/Faithfulness: Bắt các phát biểu ảo giác, bịa đặt về phòng (unsupported_claims).
    2. Answer Relevance: Bắt các câu hỏi/tiêu chí cụ thể của người dùng mà câu trả lời bỏ qua hoặc trả lời lạc đề (unaddressed_questions).
    """
    if model is None or not (answer_text or "").strip():
        return CriticVerificationReport()
    data = json.dumps([compact_room(r) for r in rooms], ensure_ascii=False)
    tool_data = "\n".join(extra_texts)[:6000]
    user_section = f"<user_query>\n{user_text}\n</user_query>\n" if (user_text or "").strip() else ""

    system_prompt = (
        "Bạn là kiểm chứng viên chất lượng câu trả lời của AI tư vấn phòng trọ Homigo.\n"
        "Nhiệm vụ của bạn:\n"
        "1. unsupported_claims: Liệt kê các phát biểu cụ thể về phòng trong <answer> mà KHÔNG được hỗ trợ bởi <rooms_data> hoặc <tool_data>. "
        "(Bỏ qua lời chào, câu xưng hô, lời khuyên chung, và gợi ý người dùng tự xác nhận khi xem phòng).\n"
        "2. unaddressed_questions: Nếu người dùng trong <user_query> có câu hỏi cụ thể hoặc thắc mắc trực tiếp "
        "(ví dụ: hỏi về cho nuôi thú cưng không, giờ giấc thế nào, tiền cọc mấy tháng, chi phí điện nước, chỗ để xe...) "
        "mà <answer> hoàn toàn bỏ qua hoặc trả lời lạc đề, hãy liệt kê câu hỏi bị bỏ sót.\n"
        "LƯU Ý: Nếu <user_query> chỉ là câu tìm kiếm phòng thông thường (ví dụ: 'tìm phòng dưới 3 triệu gần UIT') "
        "và <answer> đã đề xuất các phòng phù hợp thì unaddressed_questions là rỗng [].\n"
        "Nếu mọi tiêu chí đều đạt chuẩn, trả về 2 danh sách rỗng."
    )
    human_prompt = (
        f"<rooms_data>\n{data}\n</rooms_data>\n"
        f"<tool_data>\n{tool_data}\n</tool_data>\n"
        f"{user_section}"
        f"<answer>\n{answer_text}\n</answer>"
    )
    try:
        rep = model.with_structured_output(CriticVerificationReport).invoke([
            ("system", system_prompt),
            ("human", human_prompt),
        ])
        if isinstance(rep, CriticVerificationReport):
            return CriticVerificationReport(
                unsupported_claims=[c for c in rep.unsupported_claims if c.strip()][:5],
                unaddressed_questions=[q for q in rep.unaddressed_questions if q.strip()][:5],
            )
        elif isinstance(rep, dict):
            return CriticVerificationReport(
                unsupported_claims=[c for c in rep.get("unsupported_claims", []) if str(c).strip()][:5],
                unaddressed_questions=[q for q in rep.get("unaddressed_questions", []) if str(q).strip()][:5],
            )
        elif isinstance(rep, ClaimsReport):
            return CriticVerificationReport(
                unsupported_claims=[c for c in rep.unsupported_claims if c.strip()][:5],
                unaddressed_questions=[],
            )
        return CriticVerificationReport()
    except Exception:
        logger.warning("critic_answer_validation lỗi, bỏ qua", exc_info=True)
        return CriticVerificationReport()
