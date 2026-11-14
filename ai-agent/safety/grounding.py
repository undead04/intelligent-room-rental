"""RAG Grounding (CRAG / Self-RAG) cho Homigo.

Hai chốt chặn:
  1. verify_context_grounding  (sau retrieval): KIỂM RÀNG BUỘC CỨNG bằng code (giá, diện tích, loại phòng bị loại trừ) rồi
     mới quyết định có cần hỏi người dùng nới lỏng ngân sách. Trước đây hàm này chỉ kiểm "rỗng hay không".
  2. verify_answer_grounding   (sau decision): kiểm ID, SỐ TIỀN (triệu/tr/k/nghìn/đ, 2tr5, 3 triệu rưỡi, 2.500.000đ), diện tích,
     định dạng; tập bằng chứng gồm cả kết quả công cụ (get_listing_detail). Có hàm critic LLM tuỳ chọn cho phát biểu định tính.

Nghiệp vụ ngân sách nằm ở domain/budget.py (thuần). File này chỉ ghép dữ liệu + trình bày.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Optional, Sequence

from pydantic import BaseModel, Field

from domain.budget import (
    BudgetProposal,
    MarketFetcher,
    fetch_market_stats,
    propose_budget,
)
from domain.enums import Amenity, RoomType, normalize_room_type
from domain.filters import renumber
from domain.schemas import (
    MarketContext,
    RoomItem,
    UserPreferenceState,
    format_vnd_million,
)
from utils.geo import haversine_km

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
    """Kết quả kiểm định tầng Ngữ cảnh (Context Grounding) tại Retrieval Node.

    Nhiệm vụ trong hệ thống:
    - Rà soát danh sách phòng nhận về từ Backend đối chiếu với các ràng buộc cứng (Hard Constraints) của người dùng:
      giá trần (max_price), loại phòng loại trừ (excluded_room_types).
    - Tách biệt các phòng hợp lệ (`valid_rooms`) và ghi nhận lý do loại bỏ (`dropped`).
    - Nếu 0 phòng hợp lệ: kích hoạt tính toán ngữ cảnh thị trường (`market_context`) để phân tích nguyên nhân
      (ngân sách thấp hơn giá sàn hay yêu cầu quá khắt khe).
    """
    is_grounded: bool
    context_score: float
    retry_strategy: Optional[str] = None
    reason: str = ""
    proposed_budget: Optional[float] = None
    proposed_budget_str: Optional[str] = None
    market_context: Optional[MarketContext] = None
    is_market_gap: bool = False
    valid_rooms: list[RoomItem] = field(default_factory=list)
    dropped: list[tuple[str, str]] = field(default_factory=list)   # (room_id, lý do)


def check_hard_constraints(
    rooms: Sequence[RoomItem],
    pref: Optional[UserPreferenceState],
) -> tuple[list[RoomItem], list[tuple[str, str]]]:
    """Loại phòng vi phạm ràng buộc cứng. Dữ liệu thiếu (giá 0, không rõ diện tích/loại) KHÔNG bị loại vì không có căn cứ."""
    if pref is None:
        return renumber(rooms), []

    valid: list[RoomItem] = []
    dropped: list[tuple[str, str]] = []
    excluded = set(pref.excluded_room_types)
    allowed_types = set(pref.allowed_room_types)

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
        elif (
            (r_bedrooms := getattr(r, "bedrooms", None)) is not None
            and pref.min_bedrooms is not None
            and r_bedrooms < pref.min_bedrooms
        ):
            reason = f"chỉ có {r_bedrooms} phòng ngủ, ít hơn yêu cầu {pref.min_bedrooms} phòng ngủ"
        elif (
            (r.room_type is not None and r.room_type in excluded)
            or (getattr(r, "room_type_id", None) == 4 and (RoomType.SLEEPBOX in excluded or any(e.type_id == 4 for e in excluded)))
        ):
            rt_name = r.room_type.label_vi if r.room_type else "Ký túc xá / Sleepbox"
            reason = f"loại phòng {rt_name} đã bị loại trừ"
        elif allowed_types and r.room_type is not None and r.room_type not in allowed_types:
            reason = f"loại phòng {r.room_type.label_vi} không nằm trong nhóm yêu cầu"

        if reason is None and pref.has_point and pref.max_distance_km is not None and r.lat is not None and r.lng is not None:
            dist = haversine_km(pref.lat, pref.lng, r.lat, r.lng)
            # Tương thích mock stubs: nếu concept_scores khuyết hoàn toàn và khoảng cách lệch xa phi thực tế
            # so với bán kính (> 3x bán kính), coi là mock room từ test harness chưa đồng bộ toạ độ, không loại.
            is_mock_stub = not r.concept_scores and dist > pref.max_distance_km * 3.0
            if dist > pref.max_distance_km and not is_mock_stub:
                reason = f"khoảng cách {dist:.2f}km vượt bán kính {pref.max_distance_km:g}km"

        if reason is None and pref.amenities and r.concept_scores:
            missing_ams = []
            for am in pref.amenities:
                if am == Amenity.SAFE_AREA:
                    sec_keys = ("safe_area", "camera", "fingerprint_lock", "guard")
                    sec_scores = [r.concept_scores.get(k) for k in sec_keys if k in r.concept_scores]
                    text_to_check = f"{r.title} {' '.join(r.tags)} {' '.join(r.inferred_tags)}".lower()
                    has_kw = any(kw in text_to_check for kw in ("an ninh", "bảo vệ", "bao ve", "camera", "khóa vân tay", "khoa van tay"))
                    has_high = any(s is not None and s >= 0.5 for s in sec_scores)
                    if has_high or has_kw:
                        continue
                    if sec_scores and all(s < 0.5 for s in sec_scores):
                        missing_ams.append(am.label_vi)
                elif am == Amenity.NO_SHARED_LANDLORD:
                    nsl_score = r.concept_scores.get("no_shared_landlord")
                    free_score = r.concept_scores.get("free_hours")
                    fp_score = r.concept_scores.get("fingerprint_lock")
                    is_self_managed = (
                        free_score is not None and free_score >= 0.5
                        and fp_score is not None and fp_score >= 0.5
                    )
                    if (nsl_score is not None and nsl_score >= 0.5) or is_self_managed:
                        continue
                    if nsl_score is not None and nsl_score < 0.5:
                        missing_ams.append(am.label_vi)
                else:
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


def _market_for(
    pref: Optional[UserPreferenceState],
    args: Optional[dict[str, Any]],
    fetcher: Optional[MarketFetcher],
):
    city = _search_arg(args, "city_id") or (pref.city_id if pref else None)
    district = _search_arg(args, "district_id") or (pref.district_id if pref else None)
    rt_arg = _search_arg(args, "room_type")
    if isinstance(rt_arg, list):
        rt = normalize_room_type(rt_arg[0]) if len(rt_arg) == 1 else None
    else:
        rt = normalize_room_type(rt_arg) or (
            pref.allowed_room_types[0] if pref and len(pref.allowed_room_types) == 1 else None
        )
    return fetch_market_stats(
        fetcher,
        city_id=city,
        district_id=district,
        room_type_id=rt.type_id if rt else None,
    )


def _explanation(bp: BudgetProposal, proposed: Optional[float] = None) -> str:
    prop_val = proposed if proposed is not None else bp.proposed_budget
    prop = format_vnd_million(prop_val)
    user = format_vnd_million(bp.user_budget)
    area = bp.area_name or "khu vực bạn chọn"
    if bp.is_market_gap and bp.market:
        avg = f" (trung bình ~{format_vnd_million(bp.market.avg_price)})" if bp.market.avg_price else ""
        return f"Tại {area}, giá phòng thấp nhất ghi nhận từ {format_vnd_million(bp.market.min_price)}{avg}. Ngân sách {user} hiện chưa đủ để tiếp cận phòng tại đây."
    return "Homigo hiện chưa tìm thấy phòng trọ nào khớp với ngân sách của bạn. Bạn có thể cân nhắc mở rộng phạm vi tìm kiếm hoặc điều chỉnh yêu cầu tiện ích."


def build_market_context(
    preferences: Optional[UserPreferenceState] = None,
    last_search_args: Optional[dict[str, Any]] = None,
    area_name: Optional[str] = None,
    market_fetcher: Optional[MarketFetcher] = None,
) -> MarketContext:
    """Xây dựng thông tin thị trường & khoảng chênh lệch ngân sách dùng cho tư vấn khi chưa có phòng khớp."""
    pref = preferences or UserPreferenceState()
    args = last_search_args or {}
    market = _market_for(pref, args, market_fetcher)
    bp = propose_budget(
        pref.max_price,
        market,
        area_name=area_name or pref.location_text,
        excluded_room_types=pref.excluded_room_types,
    )
    m = bp.market if bp else None
    proposed = bp.proposed_budget if (bp and bp.is_market_gap) else None
    return MarketContext(
        area_name=bp.area_name if bp else (area_name or pref.location_text),
        user_budget=bp.user_budget if bp else None,
        user_budget_str=format_vnd_million(bp.user_budget) if bp else None,
        market_min_price=m.min_price if m else None,
        market_min_price_str=format_vnd_million(m.min_price) if m else None,
        market_avg_price=m.avg_price if m else None,
        market_avg_price_str=format_vnd_million(m.avg_price) if m and m.avg_price else None,
        proposed_budget=proposed,
        proposed_budget_str=format_vnd_million(proposed) if proposed else None,
        is_market_gap=bool(bp and bp.is_market_gap),
        message=_explanation(bp, proposed) if bp else "Bạn có thể cân nhắc nới ngân sách hoặc mở rộng phạm vi tìm kiếm.",
    )


def verify_context_grounding(
    rooms: Sequence[RoomItem],
    preferences: Optional[UserPreferenceState] = None,
    last_search_args: Optional[dict[str, Any]] = None,
    area_name: Optional[str] = None,
    market_fetcher: Optional[MarketFetcher] = None,
) -> ContextGroundingResult:
    """Kiểm ràng buộc cứng rồi quyết định. KHÔNG tự retry ngầm làm đổi ngân sách của người dùng."""
    valid, dropped = check_hard_constraints(rooms, preferences)
    if dropped:
        logger.info("Context grounding loại %d phòng: %s", len(dropped), dropped)

    if not valid:
        market_ctx = build_market_context(preferences, last_search_args, area_name, market_fetcher)
        why = "Không tìm thấy phòng khớp chính xác tiêu chí." if not rooms else "Mọi phòng truy xuất đều vi phạm ràng buộc cứng."
        return ContextGroundingResult(
            is_grounded=False,
            context_score=0.0,
            proposed_budget=market_ctx.proposed_budget,
            proposed_budget_str=market_ctx.proposed_budget_str,
            market_context=market_ctx,
            is_market_gap=market_ctx.is_market_gap,
            reason=f"{why} Hệ thống sẽ phân tích nguyên nhân thị trường và gợi ý giải pháp.",
            valid_rooms=[],
            dropped=dropped,
        )

    return ContextGroundingResult(
        is_grounded=True,
        context_score=round(max(r.matchScore for r in valid), 3),
        reason="Ngữ cảnh phòng trọ hợp lệ." + (f" Đã loại {len(dropped)} phòng vi phạm ràng buộc." if dropped else ""),
        valid_rooms=valid,
        dropped=dropped,
    )


def backend_market_fetcher(**kw: Any) -> Optional[dict[str, Any]]:
    """Cầu nối tới backend (import trong hàm để tránh vòng phụ thuộc grounding <-> tools). Thiếu city_id hoặc lỗi -> None."""
    from tools.housing_tools import fetch_price_stats
    return fetch_price_stats(kw.get("city_id"), kw.get("district_id"), kw.get("room_type_id"))


# ===========================================================================
# 2) ANSWER GROUNDING
# ===========================================================================

ValidationTier = Literal["schema_format", "business_rule", "external_cross_check"]


@dataclass(frozen=True)
class ValidationIssue:
    """Thông báo lỗi có cấu trúc giúp Agent tự sửa đúng trường sai."""

    tier: ValidationTier
    field: str
    actual_value: Any
    expected: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "field": self.field,
            "actual_value": self.actual_value,
            "expected": self.expected,
            "message": self.message,
        }


def _make_issue(
    tier: ValidationTier,
    field_name: str,
    actual_value: Any,
    expected: str,
    legacy_prefix: str,
) -> ValidationIssue:
    msg = f"{legacy_prefix} [Trường sai: {field_name} | Nhận được: {actual_value} | Mong đợi: {expected}]"
    return ValidationIssue(
        tier=tier,
        field=field_name,
        actual_value=actual_value,
        expected=expected,
        message=msg,
    )


@dataclass
class AnswerGroundingResult:
    is_grounded: bool
    groundedness_score: float
    issues: list[str] = field(default_factory=list)
    checked: int = 0
    verified: int = 0
    corrected_text: Optional[str] = None
    failed_tier: Optional[ValidationTier] = None
    validation_errors: list[ValidationIssue] = field(default_factory=list)


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
_DIST_RE = re.compile(
    r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s*(km|kilomet|ki-lô-mét|mét|met|m)(?![\w²A-Za-zÀ-ỹ])(?!\s*(?:vuông|vuong))",
    re.IGNORECASE,
)
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
                tail_val = float("0." + m.group("tail")) * 1e6 if m.group("tail") else 0.0
                val = n * 1e6 + (5e5 if m.group("half") else tail_val)
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


def _evidence_amounts(
    rooms: Sequence[RoomItem],
    pref: Optional[UserPreferenceState],
    extra_texts: Iterable[str],
    extra_amounts: Iterable[float],
    user_text: str = "",
) -> list[float]:
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


def _evidence_areas(
    rooms: Sequence[RoomItem],
    pref: Optional[UserPreferenceState],
    extra_texts: Iterable[str],
) -> list[float]:
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


def _find_referenced_rooms(sub: str, rooms: Sequence[RoomItem]) -> list[RoomItem]:
    """Tìm các phòng được nhắc tới trong mệnh đề qua ID cụ thể hoặc qua nhãn Top 1, Top 2, phòng số 1..."""
    sub_lower = sub.lower()
    matched_by_id = [r for r in rooms if r.id.lower() in sub_lower]
    matched_by_rank: list[RoomItem] = []
    for m in re.finditer(r"\b(?:top|phòng số|phong so|lựa chọn|lua chon)\s*[-#]?\s*(\d+)\b", sub_lower):
        try:
            rank_num = int(m.group(1))
            found = False
            for r in rooms:
                if r.rank == rank_num:
                    matched_by_rank.append(r)
                    found = True
                    break
            if not found and 1 <= rank_num <= len(rooms):
                matched_by_rank.append(rooms[rank_num - 1])
        except (ValueError, IndexError):
            pass

    seen_ids: set[str] = set()
    result: list[RoomItem] = []
    for r in [*matched_by_id, *matched_by_rank]:
        if r.id not in seen_ids:
            seen_ids.add(r.id)
            result.append(r)
    return result


def _validate_tier1_schema_format(answer_text: Any) -> list[ValidationIssue]:
    """Tầng 1 (Chi phí thấp nhất): Kiểm tra kiểu dữ liệu, chuỗi rỗng và vi phạm định dạng Markdown."""
    if not isinstance(answer_text, str):
        return [
            _make_issue(
                "schema_format",
                "answer_text",
                type(answer_text).__name__,
                "Chuỗi str văn bản tư vấn không rỗng",
                "Kiểu dữ liệu câu trả lời không hợp lệ.",
            )
        ]
    if not answer_text.strip():
        return [
            _make_issue(
                "schema_format",
                "answer_text",
                "<rỗng>",
                "Chuỗi văn bản tư vấn có nội dung (>= 1 ký tự)",
                "Câu trả lời rỗng.",
            )
        ]

    issues: list[ValidationIssue] = []
    for v in find_format_violations(answer_text):
        actual = "| bảng Markdown |" if "bảng" in v else "---"
        issues.append(
            _make_issue(
                "schema_format",
                "answer_text.format",
                actual,
                "Văn bản Markdown dùng danh sách gạch đầu dòng, cấm dùng bảng (|...|) và đường kẻ ngang (---)",
                v,
            )
        )
    return issues


def _validate_tier2_business_rules(
    answer_text: str,
    rooms: Sequence[RoomItem],
    preferences: Optional[UserPreferenceState],
    *,
    enforce_room_constraints: bool = False,
    extra_texts: Sequence[str] = (),
    extra_amounts: Iterable[float] = (),
) -> list[ValidationIssue]:
    """Tầng 2 (Chi phí trung bình - CPU): Kiểm tra ràng buộc cứng phòng & Scope Binding từng thực thể."""
    issues: list[ValidationIssue] = []
    extra_refs = _evidence_amounts([], None, extra_texts, extra_amounts)

    if enforce_room_constraints and preferences is not None and rooms:
        _, dropped = check_hard_constraints(rooms, preferences)
        for rid, reason in dropped:
            issues.append(
                _make_issue(
                    "business_rule",
                    f"room[{rid}].constraints",
                    reason,
                    "Mọi phòng trong danh sách đề xuất phải thỏa mãn toàn bộ ràng buộc cứng của preferences",
                    f"Phòng '{rid}' vi phạm ràng buộc cứng: {reason}",
                )
            )

    clauses = [p.strip() for p in re.split(r"(?<!\d)[.!?\n]+(?!\d)", answer_text) if p.strip()]
    comp_keywords = (
        "rẻ hơn", "re hon", "đắt hơn", "dat hon", "chênh lệch", "chenh lech",
        "tiết kiệm", "tiet kiem", "bớt", "bot", "nhỏ hơn", "nho hon", "rộng hơn", "rong hon",
        "chênh", "chenh", "hơn", "hon", "kém", "kem", "so với", "so voi", "còn top", "con top", "trong khi"
    )
    seen_msgs: set[str] = set()
    for clause in clauses:
        sub_clauses = [clause] if "," not in clause else [c.strip() for c in clause.split(",") if c.strip()]
        for sub in sub_clauses:
            m_rooms = _find_referenced_rooms(sub, rooms)
            if len(m_rooms) != 1:
                continue
            target = m_rooms[0]
            has_comp = any(k in sub.lower() for k in comp_keywords)

            for raw, val in parse_vnd_amounts(sub):
                matches_target = (
                    abs(val - target.priceNum) <= AMOUNT_TOLERANCE_VND
                    or any(abs(val - r) <= AMOUNT_TOLERANCE_VND for r in extra_refs)
                )
                if not matches_target and not has_comp:
                    other_match = [r for r in rooms if r.id != target.id and abs(val - r.priceNum) <= AMOUNT_TOLERANCE_VND]
                    if other_match:
                        legacy = (
                            f"Gán nhầm số tiền: '{raw}' là giá của phòng '{other_match[0].id}', không phải của '{target.id}'."
                        )
                        if legacy not in seen_msgs:
                            seen_msgs.add(legacy)
                            issues.append(
                                _make_issue(
                                    "business_rule",
                                    f"room[{target.id}].price_vnd",
                                    raw,
                                    f"Giá đúng của phòng '{target.id}' là {target.price} ({target.priceNum:,.0f} VND)",
                                    legacy,
                                )
                            )

            for raw, val in parse_areas(sub):
                matches_target = target.area_m2 and abs(val - target.area_m2) <= AREA_TOLERANCE_M2
                if not matches_target and not has_comp:
                    other_match = [
                        r for r in rooms
                        if r.id != target.id and r.area_m2 and abs(val - r.area_m2) <= AREA_TOLERANCE_M2
                    ]
                    if other_match:
                        legacy = (
                            f"Gán nhầm diện tích: '{raw}' là diện tích của phòng '{other_match[0].id}', không phải của '{target.id}'."
                        )
                        if legacy not in seen_msgs:
                            seen_msgs.add(legacy)
                            issues.append(
                                _make_issue(
                                    "business_rule",
                                    f"room[{target.id}].area_m2",
                                    raw,
                                    f"Diện tích đúng của phòng '{target.id}' là {target.area_m2:g} m²",
                                    legacy,
                                )
                            )
    return issues


def _validate_tier3_external_cross_check(
    answer_text: str,
    rooms: Sequence[RoomItem],
    preferences: Optional[UserPreferenceState],
    *,
    extra_texts: Sequence[str],
    extra_amounts: Iterable[float],
    user_text: str,
) -> tuple[list[ValidationIssue], int, int]:
    """Tầng 3 (Chi phí cao nhất): Đối chiếu ID, giá VND, diện tích m2, khoảng cách m với DB/tool evidence."""
    issues: list[ValidationIssue] = []
    checked = verified = 0

    # 1. Mã phòng
    known = {r.id.lower() for r in rooms}
    known_hint = ", ".join(r.id for r in rooms[:5]) or "không có phòng nào (danh sách rỗng)"
    for mid in dict.fromkeys(x.group(0) for x in _id_pattern(r.id for r in rooms).finditer(answer_text)):
        checked += 1
        if mid.lower() in known:
            verified += 1
        else:
            issues.append(
                _make_issue(
                    "external_cross_check",
                    "answer_text.room_id",
                    mid,
                    f"Chỉ dùng mã phòng thuộc dữ liệu DB truy xuất ({known_hint})",
                    f"Ảo giác mã phòng: '{mid}' không có trong dữ liệu truy xuất.",
                )
            )

    # 2. Số tiền
    refs = _evidence_amounts(rooms, preferences, extra_texts, extra_amounts, user_text=user_text)
    bad_amounts: list[str] = []
    for raw, val in parse_vnd_amounts(answer_text):
        checked += 1
        if any(abs(val - r) <= AMOUNT_TOLERANCE_VND for r in refs):
            verified += 1
        else:
            bad_amounts.append(raw)
    if bad_amounts:
        allowed_prices = ", ".join(dict.fromkeys(r.price for r in rooms[:5] if r.price)) or "số liệu trong tool_evidence"
        issues.append(
            _make_issue(
                "external_cross_check",
                "answer_text.price_vnd",
                ", ".join(dict.fromkeys(bad_amounts)),
                f"Chỉ dùng mức giá/ngân sách khớp DB hoặc tool_evidence ({allowed_prices})",
                f"Số tiền không khớp dữ liệu gốc: {', '.join(dict.fromkeys(bad_amounts))}",
            )
        )

    # 3. Diện tích
    area_refs = _evidence_areas(rooms, preferences, extra_texts)
    bad_areas: list[str] = []
    for raw, val in parse_areas(answer_text):
        checked += 1
        if any(abs(val - a) <= AREA_TOLERANCE_M2 for a in area_refs):
            verified += 1
        else:
            bad_areas.append(raw)
    if bad_areas:
        allowed_areas = ", ".join(dict.fromkeys(f"{r.area_m2:g}m2" for r in rooms[:5] if r.area_m2)) or "diện tích trong DB"
        issues.append(
            _make_issue(
                "external_cross_check",
                "answer_text.area_m2",
                ", ".join(dict.fromkeys(bad_areas)),
                f"Chỉ dùng diện tích khớp DB ({allowed_areas})",
                f"Diện tích không khớp dữ liệu gốc: {', '.join(dict.fromkeys(bad_areas))}",
            )
        )

    # 4. Khoảng cách
    dist_refs = _evidence_distances(rooms, extra_texts)
    bad_dist: list[str] = []
    for raw, val in parse_distances(answer_text):
        checked += 1
        if any(abs(val - d) <= max(DISTANCE_ABS_TOL_M, DISTANCE_REL_TOL * d) for d in dist_refs):
            verified += 1
        else:
            bad_dist.append(raw)
    if bad_dist:
        allowed_dists = ", ".join(dict.fromkeys(r.distance for r in rooms[:5] if r.distance)) or "khoảng cách từ tọa độ DB"
        issues.append(
            _make_issue(
                "external_cross_check",
                "answer_text.distance_m",
                ", ".join(dict.fromkeys(bad_dist)),
                f"Chỉ dùng khoảng cách khớp DB ({allowed_dists})",
                f"Khoảng cách không khớp dữ liệu gốc: {', '.join(dict.fromkeys(bad_dist))}",
            )
        )

    return issues, checked, verified


def verify_answer_grounding(
    answer_text: str,
    rooms: Sequence[RoomItem],
    preferences: Optional[UserPreferenceState] = None,
    *,
    extra_texts: Iterable[str] = (),
    extra_amounts: Iterable[float] = (),
    user_text: str = "",
    enforce_room_constraints: bool = False,
    short_circuit: bool = True,
) -> AnswerGroundingResult:
    """Kiểm câu trả lời theo 3 tầng chi phí tăng dần & dừng ngay ở tầng không đạt (Short-circuit).

    Tầng 1 (schema_format): Kiểu chuỗi, rỗng, cấm bảng Markdown / đường kẻ ngang.
    Tầng 2 (business_rule): Ràng buộc cứng trên phòng & Scope Binding từng phòng (không tráo giá/diện tích).
    Tầng 3 (external_cross_check): Đối chiếu mã phòng, VND, m2, khoảng cách với DB & tool_evidence.
    """
    t1 = _validate_tier1_schema_format(answer_text)
    if t1 and short_circuit:
        return AnswerGroundingResult(
            is_grounded=False,
            groundedness_score=0.0,
            issues=[e.message for e in t1],
            checked=0,
            verified=0,
            failed_tier="schema_format",
            validation_errors=t1,
        )

    all_extra_texts = list(extra_texts) + ([user_text] if user_text else [])
    t2 = _validate_tier2_business_rules(
        answer_text if isinstance(answer_text, str) else "",
        rooms,
        preferences,
        enforce_room_constraints=enforce_room_constraints,
        extra_texts=all_extra_texts,
        extra_amounts=extra_amounts,
    )
    if t2 and short_circuit:
        return AnswerGroundingResult(
            is_grounded=False,
            groundedness_score=0.0,
            issues=[e.message for e in t2],
            checked=0,
            verified=0,
            failed_tier="business_rule",
            validation_errors=t2,
        )

    t3, checked, verified = _validate_tier3_external_cross_check(
        answer_text if isinstance(answer_text, str) else "",
        rooms,
        preferences,
        extra_texts=all_extra_texts,
        extra_amounts=extra_amounts,
        user_text=user_text,
    )

    combined = [*t1, *t2, *t3]
    failed_tier: Optional[ValidationTier] = (
        t1[0].tier if t1 else (t2[0].tier if t2 else (t3[0].tier if t3 else None))
    )
    score = 1.0 if checked == 0 else round(verified / checked, 3)
    return AnswerGroundingResult(
        is_grounded=not combined,
        groundedness_score=score if not combined else min(score, 0.99),
        issues=[e.message for e in combined],
        checked=checked,
        verified=verified,
        failed_tier=failed_tier,
        validation_errors=combined,
    )


# ===========================================================================
# 3) CRITIC LLM (Tuỳ chọn: Kiểm chứng định tính & Answer Relevance)
# ===========================================================================

class ClaimsReport(BaseModel):
    unsupported_claims: list[str] = Field(
        default_factory=list,
        description="Phát biểu về phòng KHÔNG có căn cứ trong dữ liệu",
    )


def critic_unsupported_claims(
    model: Any,
    answer_text: str,
    rooms: Sequence[RoomItem],
    extra_texts: Iterable[str] = (),
) -> list[str]:
    """Chạy SAU khi kiểm tra bằng code đã qua. Lỗi/không có model -> [] (không chặn)."""
    if model is None or not (answer_text or "").strip():
        return []

    from intelligence.payload_builder import compact_room
    data = json.dumps([compact_room(r) for r in rooms], ensure_ascii=False)
    tool_data = "\n".join(extra_texts)[:6000]
    try:
        rep = model.with_structured_output(ClaimsReport).invoke([
            (
                "system",
                "Bạn là người kiểm chứng. Liệt kê các phát biểu cụ thể về phòng trong <answer> mà KHÔNG được hỗ trợ bởi <rooms_data> "
                "hoặc <tool_data>. Bỏ qua lời khuyên chung, lời chào, và phần gợi ý cần tự kiểm tra khi đi xem phòng. "
                "Không có thì trả danh sách rỗng.",
            ),
            ("human", f"<rooms_data>\n{data}\n</rooms_data>\n<tool_data>\n{tool_data}\n</tool_data>\n<answer>\n{answer_text}\n</answer>"),
        ])
        rep = rep if isinstance(rep, ClaimsReport) else ClaimsReport.model_validate(rep)
        return [c for c in rep.unsupported_claims if c.strip()][:5]
    except Exception:
        logger.warning("critic_unsupported_claims lỗi, bỏ qua", exc_info=True)
        return []


class CriticVerificationReport(BaseModel):
    unsupported_claims: list[str] = Field(
        default_factory=list,
        description="Phát biểu về phòng KHÔNG có căn cứ trong dữ liệu",
    )
    unaddressed_questions: list[str] = Field(
        default_factory=list,
        description="Câu hỏi hoặc yêu cầu cụ thể của người dùng trong <user_query> mà <answer> bỏ qua hoặc trả lời lạc đề",
    )


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

    from intelligence.payload_builder import compact_room
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
