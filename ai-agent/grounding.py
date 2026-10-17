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
from typing import Optional

from schemas import RoomItem, UserPreferenceState

MAX_GROUNDING_RETRIES = 2
MIN_ACCEPTABLE_MATCH_SCORE = 0.30


@dataclass
class ContextGroundingResult:
    """Kết quả kiểm định ngữ cảnh truy xuất (Retrieval Context Grounding)."""

    is_grounded: bool
    context_score: float
    retry_strategy: Optional[str] = None  # "relax_budget" | "broaden_search" | None
    reason: str = ""


@dataclass
class AnswerGroundingResult:
    """Kết quả kiểm định tính xác thực của câu trả lời (Answer Faithfulness / Groundedness)."""

    is_grounded: bool
    groundedness_score: float
    issues: list[str] = field(default_factory=list)
    corrected_text: Optional[str] = None


def verify_context_grounding(
    rooms: list[RoomItem],
    preferences: Optional[UserPreferenceState] = None,
    retry_count: int = 0,
) -> ContextGroundingResult:
    """Kiểm tra danh sách phòng từ Hybrid Search & Rerank có đạt chuẩn Grounding không.
    Nếu không tìm thấy phòng nào hoặc điểm matchScore quá thấp trong khi còn lượt retry,
    đề xuất chiến lược nới lỏng điều kiện (Corrective RAG).
    """
    if not rooms:
        if retry_count == 0 and preferences and (preferences.max_price or preferences.min_price):
            return ContextGroundingResult(
                is_grounded=False,
                context_score=0.0,
                retry_strategy="relax_budget",
                reason="Không tìm thấy phòng khớp ngân sách cứng -> Tự động nới biên độ ngân sách ±15% và thử lại.",
            )
        if retry_count <= 1:
            return ContextGroundingResult(
                is_grounded=False,
                context_score=0.0,
                retry_strategy="broaden_search",
                reason="Không tìm thấy phòng với bộ lọc hiện tại -> Mở rộng phạm vi tìm kiếm ngữ nghĩa.",
            )
        return ContextGroundingResult(
            is_grounded=False,
            context_score=0.0,
            retry_strategy=None,
            reason="Đã thử lại tối đa nhưng cơ sở dữ liệu không có phòng khớp yêu cầu.",
        )

    top_score = max((r.matchScore for r in rooms), default=0.0)
    if top_score < MIN_ACCEPTABLE_MATCH_SCORE and retry_count < MAX_GROUNDING_RETRIES:
        return ContextGroundingResult(
            is_grounded=False,
            context_score=round(top_score, 3),
            retry_strategy="relax_budget" if retry_count == 0 else "broaden_search",
            reason=f"Điểm phù hợp cao nhất ({top_score:.2f}) thấp hơn ngưỡng chuẩn ({MIN_ACCEPTABLE_MATCH_SCORE}) -> Thử lại với điều kiện mở rộng.",
        )

    return ContextGroundingResult(
        is_grounded=True,
        context_score=round(top_score, 3),
        retry_strategy=None,
        reason="Ngữ cảnh phòng trọ hợp lệ và đạt ngưỡng chất lượng.",
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
