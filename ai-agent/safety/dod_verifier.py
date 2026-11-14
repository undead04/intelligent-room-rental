"""Định nghĩa Hoàn thành (DoD) và Bộ Kiểm Định Độc Lập (DoD Verifier) cho Homigo AI Agent.

Nguyên tắc thiết kế:
1. DoD được suy trực tiếp từ yêu cầu thực của tác vụ (`intent`, `preferences`, `user_message`, `matched_skill`).
2. Mỗi yêu cầu có ít nhất một `DoDCondition` hoặc ghi rõ `unverifiable_reason` + chuyển `rubric` / `human`.
3. Mọi đại lượng đo lường đều khai báo tường minh `threshold` (ngưỡng) và `unit` (đơn vị).
4. Mỗi điều kiện ghi rõ loại kiểm định `verifier_type`: `state_code` | `trace_code` | `rubric` | `human`.
5. Chống can thiệp (Anti-tampering): mọi cấu trúc DoDSpec / DoDCondition / DoDReport dùng `@dataclass(frozen=True)`,
   và toàn bộ đầu vào (`direct_system_state`, `trace_spans`) được đóng băng đệ quy trước khi kiểm định.
6. Verifier nhận trạng thái đọc trực tiếp từ hệ thống + trace bất biến; tuyệt đối không dùng lời tự báo thành công
   của Agent làm bằng chứng; trả về đầu ra cố định `{"passed": bool, "failures": [...]}`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Literal, Mapping, Optional, Sequence

from domain.enums import Amenity, RoomType
from domain.schemas import RoomItem, UserPreferenceState, format_vnd_million
from graph.tracing import deep_freeze
from safety.grounding import (
    PRICE_FILTER_TOLERANCE,
    AnswerGroundingResult,
    verify_answer_grounding,
)
from utils.geo import haversine_km
from utils.text import strip_accents

VerifierType = Literal["state_code", "trace_code", "rubric", "human"]

_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "thú cưng": ("thu cung", "cho meo", "nuoi cho", "nuoi meo", "nuoi pet", "pet"),
    "tiền cọc": ("tien coc", "dat coc", "coc"),
    "an ninh": ("an ninh", "an toan", "camera", "bao ve", "trom"),
    "giờ giấc": ("gio giac", "tu do", "24/24", "24/7", "khoa van tay", "cong rieng", "ve muon"),
    "điện nước": ("dien", "nuoc", "kwh", "so dien", "khoi nuoc"),
    "gửi xe": ("bai xe", "nha xe", "gui xe", "de xe"),
    "ở ghép": ("o ghep", "o chung", "2 nguoi", "hai nguoi", "2 ban", "o 2"),
}

_FAKE_SUCCESS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bda\s+(?:dat|giu)\s+(?:phong|lich|coc)\s+(?:thanh cong|xong)\b"),
    re.compile(r"\bda\s+tim\s+(?:duoc|thay)\s+(?:\d+\s+)?phong\s+(?:phu hop|dep|re)\b"),
    re.compile(r"\bhomigo\s+da\s+tim\s+duoc\s+\d+\s+phong\b"),
    re.compile(r"\bgoi\s+y\s+(?:\d+\s+)?phong\s+tot\s+nhat\b"),
)


@dataclass(frozen=True)
class DoDCondition:
    """Một điều kiện kiểm định cụ thể thuộc Definition of Done (bất biến)."""

    requirement_id: str
    requirement_desc: str
    condition_id: str
    description: str
    verifier_type: VerifierType
    operator: str
    threshold: Any = None
    unit: Optional[str] = None
    actual_value: Any = None
    passed: Optional[bool] = None
    unverifiable_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "requirement_desc": self.requirement_desc,
            "condition_id": self.condition_id,
            "description": self.description,
            "verifier_type": self.verifier_type,
            "operator": self.operator,
            "threshold": list(self.threshold) if isinstance(self.threshold, tuple) else self.threshold,
            "unit": self.unit,
            "actual_value": list(self.actual_value) if isinstance(self.actual_value, tuple) else self.actual_value,
            "passed": self.passed,
            "unverifiable_reason": self.unverifiable_reason,
        }


@dataclass(frozen=True)
class DoDSpec:
    """Đặc tả DoD bất biến suy từ yêu cầu của lượt chạy."""

    intent: str
    conditions: tuple[DoDCondition, ...]
    user_message: str = ""
    matched_skill: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "user_message": self.user_message,
            "matched_skill": self.matched_skill,
            "conditions": [c.to_dict() for c in self.conditions],
        }


@dataclass(frozen=True)
class DoDReport:
    """Báo cáo kết quả kiểm định DoD (bất biến, tách biệt khỏi Agent)."""

    passed: bool
    conditions: tuple[DoDCondition, ...]
    failures: tuple[Mapping[str, Any], ...]
    unverifiable_conditions: tuple[DoDCondition, ...]
    rubric_or_human_conditions: tuple[DoDCondition, ...]
    summary: str

    @property
    def all_passed(self) -> bool:
        return self.passed

    def to_verifier_output(self) -> dict[str, Any]:
        """Đầu ra cố định theo chuẩn Verifier: `{"passed": bool, "failures": [...]}`."""
        return {
            "passed": self.passed,
            "failures": [
                {
                    "condition_id": str(f["condition_id"]),
                    "actual": f.get("actual"),
                    "expected": f.get("expected"),
                    "verifier_type": f.get("verifier_type"),
                    "message": f.get("message", ""),
                }
                for f in self.failures
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        out = self.to_verifier_output()
        out.update({
            "summary": self.summary,
            "conditions": [c.to_dict() for c in self.conditions],
            "unverifiable_conditions": [c.to_dict() for c in self.unverifiable_conditions],
            "rubric_or_human_conditions": [c.to_dict() for c in self.rubric_or_human_conditions],
        })
        return out


def derive_dod_spec(
    intent: str,
    preferences: Optional[UserPreferenceState] = None,
    *,
    user_message: str = "",
    matched_skill: Optional[str] = None,
    effective_radius_km: Optional[float] = None,
    include_answer_checks: bool = True,
) -> DoDSpec:
    """Suy danh sách điều kiện DoD từ yêu cầu thực của tác vụ; không dùng dấu hiệu bề mặt."""
    pref = preferences or UserPreferenceState()
    conds: list[DoDCondition] = []

    if intent in ("new_search", "refine_search"):
        conds.append(
            DoDCondition(
                requirement_id="req_search_execution",
                requirement_desc="Thực thi công cụ tìm kiếm phòng thực tế trên hệ thống",
                condition_id="cond_search_trace",
                description="Trace của lượt chạy ghi nhận tool search_rooms thực thi với status='ok'",
                verifier_type="trace_code",
                operator="tool_executed_ok",
                threshold="search_rooms",
                unit="call",
            )
        )

    if pref.max_price is not None:
        max_vnd = round(float(pref.max_price) * (1 + PRICE_FILTER_TOLERANCE))
        conds.append(
            DoDCondition(
                requirement_id="req_max_price",
                requirement_desc=f"Giá thuê không vượt quá trần ngân sách {format_vnd_million(pref.max_price)}",
                condition_id="cond_max_price",
                description="Giá thuê của toàn bộ phòng đề xuất <= ngưỡng ngân sách (+2% dung sai)",
                verifier_type="state_code",
                operator="<=",
                threshold=max_vnd,
                unit="VND",
            )
        )

    if pref.min_price is not None:
        min_vnd = round(float(pref.min_price) * (1 - PRICE_FILTER_TOLERANCE))
        conds.append(
            DoDCondition(
                requirement_id="req_min_price",
                requirement_desc=f"Giá thuê đạt mức sàn tối thiểu {format_vnd_million(pref.min_price)}",
                condition_id="cond_min_price",
                description="Giá thuê của toàn bộ phòng đề xuất >= ngưỡng tối thiểu (-2% dung sai)",
                verifier_type="state_code",
                operator=">=",
                threshold=min_vnd,
                unit="VND",
            )
        )

    if pref.min_area is not None:
        conds.append(
            DoDCondition(
                requirement_id="req_min_area",
                requirement_desc=f"Diện tích phòng tối thiểu {pref.min_area:g} m2",
                condition_id="cond_min_area",
                description="Diện tích mọi phòng đề xuất có số liệu >= ngưỡng m2 yêu cầu",
                verifier_type="state_code",
                operator=">=",
                threshold=float(pref.min_area),
                unit="m2",
            )
        )

    if pref.max_area is not None:
        conds.append(
            DoDCondition(
                requirement_id="req_max_area",
                requirement_desc=f"Diện tích phòng tối đa {pref.max_area:g} m2",
                condition_id="cond_max_area",
                description="Diện tích mọi phòng đề xuất có số liệu <= ngưỡng m2 tối đa",
                verifier_type="state_code",
                operator="<=",
                threshold=float(pref.max_area),
                unit="m2",
            )
        )

    if pref.min_bedrooms is not None:
        conds.append(
            DoDCondition(
                requirement_id="req_min_bedrooms",
                requirement_desc=f"Số phòng ngủ tối thiểu {pref.min_bedrooms}",
                condition_id="cond_min_bedrooms",
                description="Số phòng ngủ của các phòng có số liệu >= ngưỡng yêu cầu",
                verifier_type="state_code",
                operator=">=",
                threshold=int(pref.min_bedrooms),
                unit="phòng ngủ",
            )
        )

    if pref.has_point:
        rad_km = float(pref.max_distance_km or effective_radius_km or 5.0)
        conds.append(
            DoDCondition(
                requirement_id="req_max_distance",
                requirement_desc=f"Khoảng cách địa lý <= {rad_km:g} km tính từ điểm mốc",
                condition_id="cond_max_distance",
                description="Khoảng cách Haversine thực tế tới điểm mốc <= bán kính tối đa",
                verifier_type="state_code",
                operator="<=",
                threshold=rad_km,
                unit="km",
            )
        )

    if pref.allowed_room_types:
        conds.append(
            DoDCondition(
                requirement_id="req_allowed_room_types",
                requirement_desc="Loại phòng thuộc danh sách loại được phép",
                condition_id="cond_allowed_room_types",
                description="Mã loại phòng của từng kết quả nằm trong allowed_room_types",
                verifier_type="state_code",
                operator="in",
                threshold=tuple(r.value for r in pref.allowed_room_types),
                unit="room_type",
            )
        )

    if pref.excluded_room_types:
        conds.append(
            DoDCondition(
                requirement_id="req_excluded_room_types",
                requirement_desc="Loại bỏ hoàn toàn các loại phòng bị phủ định",
                condition_id="cond_excluded_room_types",
                description="Không có phòng nào thuộc nhóm excluded_room_types",
                verifier_type="state_code",
                operator="not_in",
                threshold=tuple(r.value for r in pref.excluded_room_types),
                unit="room_type",
            )
        )

    if pref.amenities:
        conds.append(
            DoDCondition(
                requirement_id="req_amenities",
                requirement_desc="Đáp ứng đầy đủ tiện ích bắt buộc",
                condition_id="cond_amenities",
                description="Các phòng có dữ liệu concept_scores đều đạt >= 0.5 cho mọi tiện ích bắt buộc",
                verifier_type="state_code",
                operator="contains_all",
                threshold=tuple(a.value for a in pref.amenities),
                unit="amenity",
            )
        )

    if pref.special_requirements:
        conds.append(
            DoDCondition(
                requirement_id="req_special_requirements",
                requirement_desc=f"Yêu cầu định tính riêng: {', '.join(pref.special_requirements)}",
                condition_id="cond_special_requirements",
                description="Kiểm định các tiêu chí định tính không có cột cấu trúc chuẩn trong DB",
                verifier_type="human",
                operator="human_review",
                threshold=tuple(pref.special_requirements),
                unit="criterion",
                unverifiable_reason=(
                    "Yêu cầu định tính tự do (ví dụ: yên tĩnh, hẻm thoáng) chưa có cột dữ liệu chuẩn hóa "
                    "trong DB; chuyển sang người duyệt hoặc kiểm tra thực tế khi xem phòng."
                ),
            )
        )

    if intent == "skill_advice" or matched_skill:
        conds.append(
            DoDCondition(
                requirement_id="req_skill_consult",
                requirement_desc=f"Tham vấn đúng tài liệu kỹ năng '{matched_skill or 'consult_housing_skill'}'",
                condition_id="cond_skill_trace",
                description="Trace ghi nhận tool consult_housing_skill chạy thành công với status='ok'",
                verifier_type="trace_code",
                operator="tool_executed_ok",
                threshold=matched_skill or "consult_housing_skill",
                unit="call",
            )
        )

    if include_answer_checks:
        conds.append(
            DoDCondition(
                requirement_id="req_factual_grounding",
                requirement_desc="Số liệu và mã phòng trong câu trả lời khớp 100% dữ liệu hệ thống thực tế",
                condition_id="cond_factual_grounding",
                description="Điểm grounding >= 1.0 ratio và không tuyên bố tìm thấy phòng khi hệ thống rỗng",
                verifier_type="state_code",
                operator=">=",
                threshold=1.0,
                unit="ratio",
            )
        )
        conds.append(
            DoDCondition(
                requirement_id="req_answer_relevance",
                requirement_desc="Câu trả lời đi đúng trọng tâm câu hỏi và tiêu chí người dùng",
                condition_id="cond_answer_relevance",
                description="Điểm đánh giá relevance theo rubric >= 0.7 score",
                verifier_type="rubric",
                operator=">=",
                threshold=0.7,
                unit="score",
            )
        )

    return DoDSpec(
        intent=intent,
        conditions=tuple(conds),
        user_message=user_message,
        matched_skill=matched_skill,
    )


def _room_has_amenity(room: Any, am_value: str) -> Optional[bool]:
    """Kiểm tra 1 tiện ích trên dữ liệu phòng. Trả None nếu phòng không có concept_scores."""
    scores = getattr(room, "concept_scores", None) or {}
    if not scores:
        return None
    if am_value == Amenity.SAFE_AREA.value:
        sec_keys = ("safe_area", "camera", "fingerprint_lock", "guard")
        sec_scores = [scores.get(k) for k in sec_keys if k in scores]
        title = getattr(room, "title", "")
        tags = getattr(room, "tags", ()) or ()
        inferred = getattr(room, "inferred_tags", ()) or ()
        text = f"{title} {' '.join(tags)} {' '.join(inferred)}".lower()
        has_kw = any(kw in text for kw in ("an ninh", "bảo vệ", "bao ve", "camera", "khóa vân tay", "khoa van tay"))
        if has_kw or any(s is not None and s >= 0.5 for s in sec_scores):
            return True
        return False if sec_scores else None
    if am_value == Amenity.NO_SHARED_LANDLORD.value:
        nsl = scores.get("no_shared_landlord")
        free = scores.get("free_hours")
        fp = scores.get("fingerprint_lock")
        if (nsl is not None and nsl >= 0.5) or (free is not None and free >= 0.5 and fp is not None and fp >= 0.5):
            return True
        return False if nsl is not None else None
    sc = scores.get(am_value)
    if sc is None:
        return None
    return sc >= 0.5


def _coerce_rooms(raw_rooms: Any) -> list[RoomItem]:
    out: list[RoomItem] = []
    for idx, item in enumerate(raw_rooms or (), 1):
        if isinstance(item, RoomItem):
            out.append(item)
        elif isinstance(item, Mapping):
            if "listing" in item:
                out.append(RoomItem.from_backend_result(dict(item), rank=idx))
            else:
                out.append(RoomItem(**dict(item)))
        elif hasattr(item, "id"):
            out.append(item)
    return out


def _has_fake_success_claim(answer_text: str) -> bool:
    norm = " ".join(strip_accents((answer_text or "").lower()).split())
    return any(p.search(norm) for p in _FAKE_SUCCESS_PATTERNS)


def _evaluate_rubric_relevance(
    user_message: str,
    candidate_answer: str,
    rooms: Sequence[RoomItem],
    critic_result: Optional[Any],
) -> tuple[float, Optional[str]]:
    if critic_result is not None:
        unaddressed = getattr(critic_result, "unaddressed_questions", None) or []
        if unaddressed:
            return 0.0, f"Bỏ sót câu hỏi: {'; '.join(str(x) for x in unaddressed)}"

    ans_norm = " ".join(strip_accents((candidate_answer or "").lower()).split())
    if not ans_norm:
        return 0.0, "Câu trả lời rỗng"

    uq_norm = " ".join(strip_accents((user_message or "").lower()).split())
    present_topics = [
        topic for topic, kws in _TOPIC_KEYWORDS.items() if any(kw in uq_norm for kw in kws)
    ]
    if present_topics:
        missing = [t for t in present_topics if not any(kw in ans_norm for kw in _TOPIC_KEYWORDS[t])]
        if missing:
            matched = len(present_topics) - len(missing)
            score = round(matched / len(present_topics), 2) if matched > 0 else 0.1
            return score, f"Bỏ sót chủ đề người dùng hỏi: {', '.join(missing)}"
        return 1.0, None

    off_topic_markers = ("bat dong san mua ban", "chung khoan", "gia vang", "mua ban nha dat")
    if any(m in ans_norm for m in off_topic_markers):
        return 0.1, "Câu trả lời lạc đề khỏi lĩnh vực thuê trọ"

    if rooms or len(ans_norm) >= 10:
        return 1.0, None
    return 0.3, "Câu trả lời quá ngắn và thiếu thông tin hỗ trợ"


def verify_dod(
    spec: DoDSpec,
    *,
    candidate_answer: str,
    direct_system_state: Mapping[str, Any],
    trace_spans: Sequence[Mapping[str, Any]],
    preferences: Optional[UserPreferenceState] = None,
    grounding_result: Optional[AnswerGroundingResult] = None,
    relevance_score: Optional[float] = None,
    critic_result: Optional[Any] = None,
    enforce_trace: bool = True,
) -> DoDReport:
    """Thực thi mọi phép kiểm trong DoD trên trạng thái đọc trực tiếp và trace đóng băng."""
    frozen_state = deep_freeze(dict(direct_system_state or {}))
    frozen_trace = deep_freeze(list(trace_spans or ()))

    rooms = _coerce_rooms(frozen_state.get("rooms"))
    tool_evidence = list(frozen_state.get("tool_evidence") or ())
    extra_amounts = [a for a in (frozen_state.get("proposed_budget"),) if a]
    admin_not_found = bool(frozen_state.get("admin_not_found"))
    ambiguous_cands = bool(frozen_state.get("ambiguous_candidates"))
    search_error = frozen_state.get("search_error")

    g_res = grounding_result
    if g_res is None:
        g_res = verify_answer_grounding(
            candidate_answer,
            rooms,
            preferences,
            extra_texts=tool_evidence,
            extra_amounts=extra_amounts,
            user_text=spec.user_message,
        )

    evaluated: list[DoDCondition] = []
    failures: list[dict[str, Any]] = []

    def _record_failure(cond: DoDCondition, msg: str) -> None:
        failures.append({
            "condition_id": cond.condition_id,
            "actual": cond.actual_value,
            "expected": f"{cond.operator} {cond.threshold} ({cond.unit})" if cond.unit else cond.threshold,
            "verifier_type": cond.verifier_type,
            "message": msg,
        })

    for cond in spec.conditions:
        cid = cond.condition_id

        if cid == "cond_search_trace":
            if admin_not_found or ambiguous_cands:
                updated = replace(
                    cond,
                    actual_value="skipped_pre_search_location_issue",
                    passed=None,
                    unverifiable_reason="Không chạy search_rooms vì bước phân giải địa điểm trả về admin_not_found/ambiguous",
                )
                evaluated.append(updated)
                continue
            if not enforce_trace:
                updated = replace(
                    cond,
                    actual_value="trace_enforcement_disabled",
                    passed=None,
                    unverifiable_reason="Cờ enforce_trace=False trong chế độ kiểm thử đơn vị cục bộ",
                )
                evaluated.append(updated)
                continue
            search_spans = [
                sp for sp in frozen_trace
                if sp.get("type") == "tool_finished"
                and (sp.get("tool") == "search_rooms" or sp.get("tool_name") == "search_rooms")
            ]
            ok_spans = [
                sp for sp in search_spans
                if sp.get("status") == "ok"
                and str((sp.get("args") or sp.get("arguments") or {}).get("query") or "").strip() != ""
            ]
            if ok_spans:
                evaluated.append(replace(cond, actual_value=f"called({len(ok_spans)}x, status=ok)", passed=True))
            elif search_error:
                updated = replace(cond, actual_value=f"error: {search_error}", passed=False)
                evaluated.append(updated)
                _record_failure(updated, f"Tìm kiếm thất bại trên hệ thống: {search_error}")
            else:
                actual = (
                    f"status={search_spans[-1].get('status')}" if search_spans else "not_called"
                )
                updated = replace(cond, actual_value=actual, passed=False)
                evaluated.append(updated)
                _record_failure(updated, "Trace không ghi nhận lệnh search_rooms hoàn tất thành công")
            continue

        if cid == "cond_skill_trace":
            if not enforce_trace:
                evaluated.append(
                    replace(
                        cond,
                        actual_value="trace_enforcement_disabled",
                        passed=None,
                        unverifiable_reason="Cờ enforce_trace=False trong chế độ kiểm thử đơn vị",
                    )
                )
                continue
            skill_spans = [
                sp for sp in frozen_trace
                if sp.get("type") == "tool_finished"
                and (sp.get("tool") == "consult_housing_skill" or sp.get("tool_name") == "consult_housing_skill")
                and sp.get("status") == "ok"
            ]
            expected_slug = cond.threshold
            if expected_slug and expected_slug != "consult_housing_skill":
                matched_spans = [
                    sp for sp in skill_spans
                    if (sp.get("args") or sp.get("arguments") or {}).get("skill_name") == expected_slug
                ]
            else:
                matched_spans = skill_spans
            if matched_spans:
                evaluated.append(replace(cond, actual_value=expected_slug, passed=True))
            else:
                updated = replace(cond, actual_value="not_called", passed=False)
                evaluated.append(updated)
                _record_failure(updated, f"Chưa gọi tool consult_housing_skill cho '{expected_slug}'")
            continue

        if cid == "cond_max_price":
            priced = [float(r.priceNum) for r in rooms if getattr(r, "priceNum", 0) and r.priceNum > 0]
            if not priced:
                evaluated.append(
                    replace(cond, actual_value=None, passed=None, unverifiable_reason="Không có phòng có giá xác định để đối chiếu")
                )
            else:
                max_seen = max(priced)
                ok = max_seen <= float(cond.threshold)
                updated = replace(cond, actual_value=max_seen, passed=ok)
                evaluated.append(updated)
                if not ok:
                    _record_failure(updated, f"Có phòng giá {max_seen:,.0f} VND vượt ngưỡng {float(cond.threshold):,.0f} VND")
            continue

        if cid == "cond_min_price":
            priced = [float(r.priceNum) for r in rooms if getattr(r, "priceNum", 0) and r.priceNum > 0]
            if not priced:
                evaluated.append(
                    replace(cond, actual_value=None, passed=None, unverifiable_reason="Không có phòng có giá xác định để đối chiếu")
                )
            else:
                min_seen = min(priced)
                ok = min_seen >= float(cond.threshold)
                updated = replace(cond, actual_value=min_seen, passed=ok)
                evaluated.append(updated)
                if not ok:
                    _record_failure(updated, f"Có phòng giá {min_seen:,.0f} VND thấp hơn mức sàn {float(cond.threshold):,.0f} VND")
            continue

        if cid == "cond_min_area":
            areas = [float(r.area_m2) for r in rooms if getattr(r, "area_m2", None)]
            if not areas:
                evaluated.append(
                    replace(cond, actual_value=None, passed=None, unverifiable_reason="Không có phòng có diện tích xác định để đối chiếu")
                )
            else:
                min_a = min(areas)
                ok = min_a >= float(cond.threshold)
                updated = replace(cond, actual_value=min_a, passed=ok)
                evaluated.append(updated)
                if not ok:
                    _record_failure(updated, f"Có phòng diện tích {min_a:g} m2 nhỏ hơn {cond.threshold:g} m2")
            continue

        if cid == "cond_max_area":
            areas = [float(r.area_m2) for r in rooms if getattr(r, "area_m2", None)]
            if not areas:
                evaluated.append(
                    replace(cond, actual_value=None, passed=None, unverifiable_reason="Không có phòng có diện tích xác định để đối chiếu")
                )
            else:
                max_a = max(areas)
                ok = max_a <= float(cond.threshold)
                updated = replace(cond, actual_value=max_a, passed=ok)
                evaluated.append(updated)
                if not ok:
                    _record_failure(updated, f"Có phòng diện tích {max_a:g} m2 lớn hơn {cond.threshold:g} m2")
            continue

        if cid == "cond_min_bedrooms":
            beds = [int(r.bedrooms) for r in rooms if getattr(r, "bedrooms", None) is not None]
            if not beds:
                evaluated.append(
                    replace(cond, actual_value=None, passed=None, unverifiable_reason="Các phòng trả về thiếu trường bedrooms")
                )
            else:
                min_b = min(beds)
                ok = min_b >= int(cond.threshold)
                updated = replace(cond, actual_value=min_b, passed=ok)
                evaluated.append(updated)
                if not ok:
                    _record_failure(updated, f"Có phòng chỉ có {min_b} phòng ngủ (< {cond.threshold})")
            continue

        if cid == "cond_max_distance":
            ref_lat = getattr(preferences, "lat", None) if preferences else frozen_state.get("lat")
            ref_lng = getattr(preferences, "lng", None) if preferences else frozen_state.get("lng")
            dists = [
                round(haversine_km(float(ref_lat), float(ref_lng), float(r.lat), float(r.lng)), 3)
                for r in rooms
                if ref_lat is not None and ref_lng is not None and getattr(r, "lat", None) is not None and getattr(r, "lng", None) is not None
            ]
            if not dists:
                evaluated.append(
                    replace(cond, actual_value=None, passed=None, unverifiable_reason="Thiếu toạ độ điểm mốc hoặc toạ độ phòng để tính Haversine")
                )
            else:
                max_d = max(dists)
                ok = max_d <= float(cond.threshold)
                updated = replace(cond, actual_value=max_d, passed=ok)
                evaluated.append(updated)
                if not ok:
                    _record_failure(updated, f"Khoảng cách {max_d:g} km vượt bán kính {cond.threshold:g} km")
            continue

        if cid == "cond_allowed_room_types":
            typed = [r.room_type.value for r in rooms if getattr(r, "room_type", None) is not None]
            if not typed:
                evaluated.append(
                    replace(cond, actual_value=None, passed=None, unverifiable_reason="Các phòng trả về thiếu nhãn room_type")
                )
            else:
                allowed_set = set(cond.threshold or ())
                bad = [rt for rt in typed if rt not in allowed_set]
                ok = not bad
                updated = replace(cond, actual_value=tuple(typed), passed=ok)
                evaluated.append(updated)
                if not ok:
                    _record_failure(updated, f"Loại phòng {bad} không nằm trong nhóm được phép {sorted(allowed_set)}")
            continue

        if cid == "cond_excluded_room_types":
            if not rooms:
                evaluated.append(
                    replace(cond, actual_value=(), passed=True)
                )
            else:
                excluded_set = set(cond.threshold or ())
                violating: list[str] = []
                for r in rooms:
                    rt_val = r.room_type.value if getattr(r, "room_type", None) is not None else None
                    rt_id = getattr(r, "room_type_id", None)
                    if rt_val in excluded_set or (rt_id == 4 and RoomType.SLEEPBOX.value in excluded_set):
                        violating.append(f"{r.id}:{rt_val or RoomType.SLEEPBOX.value}")
                ok = not violating
                updated = replace(cond, actual_value=tuple(violating) if violating else "none_excluded", passed=ok)
                evaluated.append(updated)
                if not ok:
                    _record_failure(updated, f"Chứa loại phòng đã bị loại trừ: {', '.join(violating)}")
            continue

        if cid == "cond_amenities":
            if not rooms:
                evaluated.append(
                    replace(cond, actual_value=None, passed=None, unverifiable_reason="Không có phòng trả về để kiểm tiện ích")
                )
            else:
                missing_pairs: list[str] = []
                any_scored = False
                for r in rooms:
                    for am_val in cond.threshold or ():
                        has_am = _room_has_amenity(r, am_val)
                        if has_am is not None:
                            any_scored = True
                            if not has_am:
                                missing_pairs.append(f"{r.id} thiếu {am_val}")
                if not any_scored:
                    evaluated.append(
                        replace(
                            cond,
                            actual_value=None,
                            passed=None,
                            unverifiable_reason="Hệ thống/mock không có dữ liệu concept_scores cho tiện ích bắt buộc",
                        )
                    )
                else:
                    ok = not missing_pairs
                    updated = replace(cond, actual_value=tuple(missing_pairs) if missing_pairs else "all_matched", passed=ok)
                    evaluated.append(updated)
                    if not ok:
                        _record_failure(updated, f"Thiếu tiện ích bắt buộc: {', '.join(missing_pairs)}")
            continue

        if cid == "cond_special_requirements":
            evaluated.append(replace(cond, actual_value="pending_human_review", passed=None))
            continue

        if cid == "cond_factual_grounding":
            if not rooms and _has_fake_success_claim(candidate_answer):
                updated = replace(cond, actual_value=0.0, passed=False)
                evaluated.append(updated)
                _record_failure(
                    updated,
                    "Câu trả lời tự báo đã tìm được/đặt được phòng khi trạng thái hệ thống thực tế có 0 phòng",
                )
            else:
                score = float(g_res.groundedness_score)
                ok = bool(g_res.is_grounded and score >= float(cond.threshold))
                updated = replace(cond, actual_value=score, passed=ok)
                evaluated.append(updated)
                if not ok:
                    _record_failure(updated, "; ".join(g_res.issues) or f"Groundedness {score} < {cond.threshold}")
            continue

        if cid == "cond_answer_relevance":
            if relevance_score is not None:
                r_score = float(relevance_score)
                reason = None if r_score >= float(cond.threshold) else f"Điểm relevance {r_score} < {cond.threshold}"
            else:
                r_score, reason = _evaluate_rubric_relevance(spec.user_message, candidate_answer, rooms, critic_result)
            ok = r_score >= float(cond.threshold)
            updated = replace(cond, actual_value=r_score, passed=ok)
            evaluated.append(updated)
            if not ok:
                _record_failure(updated, reason or f"Answer relevance {r_score} < {cond.threshold}")
            continue

        evaluated.append(cond)

    unverifiable = tuple(c for c in evaluated if c.passed is None)
    rubric_or_human = tuple(c for c in evaluated if c.verifier_type in ("rubric", "human"))
    overall_passed = len(failures) == 0
    summary = (
        f"DoD đạt ({sum(1 for c in evaluated if c.passed is True)}/{len(evaluated)} điều kiện kiểm được)."
        if overall_passed
        else f"DoD KHÔNG đạt ({len(failures)} lỗi: {', '.join(f['condition_id'] for f in failures)})."
    )

    return DoDReport(
        passed=overall_passed,
        conditions=tuple(evaluated),
        failures=tuple(failures),
        unverifiable_conditions=unverifiable,
        rubric_or_human_conditions=rubric_or_human,
        summary=summary,
    )


__all__ = [
    "VerifierType",
    "DoDCondition",
    "DoDSpec",
    "DoDReport",
    "derive_dod_spec",
    "verify_dod",
]
