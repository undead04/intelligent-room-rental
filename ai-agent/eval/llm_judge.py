"""Gemini Flash-Lite LLM-as-a-Judge cho Hệ thống Gợi ý Phòng trọ Thông minh (Homigo).

Cung cấp:
- RecommendationJudgeReport: Schema Pydantic thẩm định 3 chiều (Relevance, Ranking, Faithfulness).
- get_judge_llm: Khởi tạo mô hình Judge LLM (ưu tiên gemini-2.5-flash-lite qua OpenAI-compatible endpoint).
- _rule_based_recommendation_judge: Thẩm định dự phòng khách quan bằng luật khi offline/không có LLM.
- evaluate_recommendation_quality: Hàm đánh giá chính thức kết hợp LLM Judge và tự động fallback.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional, Sequence

from pydantic import BaseModel, Field, model_validator

# Khởi tạo logger
logger = logging.getLogger(__name__)

# Dual-import cho GroundTruthExpectation và evaluate_room_satisfaction
from eval.ir_metrics import evaluate_room_satisfaction

# Thử import verify_answer_grounding để kiểm tra tính trung thực số liệu
from safety.grounding import verify_answer_grounding


# ============================================================================
# 1. PYDANTIC SCHEMA: RecommendationJudgeReport
# ============================================================================


class RecommendationJudgeReport(BaseModel):
    """Báo cáo thẩm định chất lượng gợi ý phòng trọ của Homigo AI Agent (thang 1.0 đến 5.0)."""

    relevance_score: float = Field(
        ...,
        ge=1.0,
        le=5.0,
        description="Độ phù hợp của các phòng gợi ý so với nhu cầu và ràng buộc (1.0 đến 5.0).",
    )
    ranking_score: float = Field(
        ...,
        ge=1.0,
        le=5.0,
        description="Chất lượng xếp hạng (1.0 đến 5.0): Top 1 có thực sự vượt trội hơn các phòng bên dưới không?",
    )
    faithfulness_score: float = Field(
        ...,
        ge=1.0,
        le=5.0,
        description="Tính trung thực (1.0 đến 5.0) của lời giải thích/so sánh so với số liệu thực tế của phòng.",
    )
    overall_score: float = Field(
        ...,
        ge=1.0,
        le=5.0,
        description="Điểm tổng thể kết hợp (0.4 * relevance + 0.3 * ranking + 0.3 * faithfulness).",
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="Danh sách các điểm mạnh của kết quả gợi ý và lời tư vấn.",
    )
    weaknesses: list[str] = Field(
        default_factory=list,
        description="Danh sách các điểm yếu, vi phạm ràng buộc hoặc khía cạnh chưa tối ưu.",
    )
    rationale: str = Field(
        ...,
        description="Lý giải chi tiết, khách quan của thẩm định viên cho điểm số được chấm.",
    )

    @staticmethod
    def compute_overall_score(
        relevance: float,
        ranking: float,
        faithfulness: float,
    ) -> float:
        """Tính điểm overall chuẩn hóa theo trọng số 0.4 / 0.3 / 0.3."""
        score = 0.4 * float(relevance) + 0.3 * float(ranking) + 0.3 * float(faithfulness)
        return max(1.0, min(5.0, round(score, 2)))

    @model_validator(mode="before")
    @classmethod
    def populate_overall_score_if_missing(cls, data: Any) -> Any:
        """Tự động tính overall_score nếu người dùng không truyền vào."""
        if isinstance(data, dict):
            if data.get("overall_score") is None:
                rel = data.get("relevance_score")
                rk = data.get("ranking_score")
                ft = data.get("faithfulness_score")
                if rel is not None and rk is not None and ft is not None:
                    try:
                        data["overall_score"] = cls.compute_overall_score(rel, rk, ft)
                    except (ValueError, TypeError):
                        pass
        return data


# ============================================================================
# 2. KHỞI TẠO JUDGE LLM: get_judge_llm
# ============================================================================


def get_judge_llm(
    model_name: str = "gemini-3.5-flash-lite",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Optional[Any]:
    """Khởi tạo mô hình LLM-as-a-Judge.

    Ưu tiên sử dụng model dòng Flash-Lite: 'gemini-3.5-flash-lite'
    gọi qua OpenAI-compatible endpoint của Google:
    `https://generativelanguage.googleapis.com/v1beta/openai/`.

    Args:
        model_name: Tên mô hình LLM, mặc định 'gemini-2.5-flash-lite'.
        api_key: Khóa API tuỳ chọn (nếu không truyền sẽ tự đọc từ biến môi trường).
        base_url: Endpoint URL tuỳ chọn.

    Returns:
        ChatOpenAI instance nếu khởi tạo thành công, hoặc None nếu thiếu cấu hình.
    """
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.warning("get_judge_llm: Thư viện langchain_openai chưa được cài đặt.")
        return None

    # Tìm API Key từ các biến môi trường phổ biến (hỗ trợ cả GEMINI_API_KEY và GEMINI_API_KEYS phân tách bằng phẩy)
    gemini_keys_env = os.getenv("GEMINI_API_KEYS", "").strip()
    first_gemini_key = gemini_keys_env.split(",")[0].strip() if gemini_keys_env else ""

    resolved_key = (
        api_key
        or os.getenv("GEMINI_API_KEY")
        or first_gemini_key
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
    )

    # Nếu là mô hình Gemini và chưa cấu hình base_url, trỏ về Google Gemini OpenAI endpoint
    resolved_base_url = base_url
    if not resolved_base_url:
        if "gemini" in model_name.lower():
            resolved_base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        else:
            resolved_base_url = os.getenv("LLM_BASE_URL")

    # Nếu đã có key hợp lệ
    if resolved_key:
        try:
            return ChatOpenAI(
                model=model_name,
                api_key=resolved_key,
                base_url=resolved_base_url,
                temperature=0.0,
                timeout=60,
                max_retries=3,
            )
        except Exception as e:
            logger.warning("get_judge_llm: Không thể khởi tạo ChatOpenAI với key: %s", e)

    # Fallback sang core.llm nếu có sẵn trong hệ thống
    try:
        from core.llm import get_llm
        fallback_llm = get_llm("fast")
        if fallback_llm is not None:
            return fallback_llm
    except Exception:
        pass

    return None


# ============================================================================
# 3. THẨM ĐỊNH DỰ PHÒNG BẰNG LUẬT: _rule_based_recommendation_judge
# ============================================================================


def _extract_price_and_area_from_text(text: str) -> list[float]:
    """Trích xuất các con số liên quan đến giá tiền hoặc diện tích trong text bằng regex cơ bản."""
    amounts: list[float] = []
    # Khớp các dạng '3.5 triệu', '3tr5', '2.8tr', '3000000'
    for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(?:triệu|trieu|tr)", text, re.IGNORECASE):
        try:
            val = float(m.group(1).replace(",", ".")) * 1_000_000.0
            amounts.append(val)
        except ValueError:
            pass
    return amounts


def _rule_based_recommendation_judge(
    user_query: str,
    expectation: Any,
    rooms: Sequence[Any],
    text_reply: str,
    insights: Optional[Any] = None,
    budget_tolerance_pct: float = 0.0,
) -> RecommendationJudgeReport:
    """Đánh giá chất lượng khuyến nghị bằng luật dựa trên các chỉ số IR và Grounding.

    Được kích hoạt khi chạy offline hoặc khi LLM Judge gặp sự cố mạng/hết quota.
    """
    n = len(rooms)

    # 1. Trường hợp không trả về phòng nào
    if n == 0:
        ans_lower = (text_reply or "").lower()
        has_explanation = any(
            w in ans_lower
            for w in ("không tìm thấy", "chưa tìm thấy", "nới lỏng", "ngân sách", "khu vực", "tiếc")
        )
        relevance_score = 1.5 if has_explanation else 1.0
        ranking_score = 1.0
        faithfulness_score = 4.5 if has_explanation else 2.0
        overall = round(0.4 * relevance_score + 0.3 * ranking_score + 0.3 * faithfulness_score, 2)

        strengths = ["Phản hồi trung thực thông báo không tìm thấy phòng"] if has_explanation else []
        weaknesses = ["Hệ thống không trả về phòng trọ nào đáp ứng tiêu chí người dùng"]
        rationale = (
            "Hệ thống trả về danh sách 0 phòng. Câu trả lời có giải thích lý do "
            if has_explanation
            else "Hệ thống trả về 0 phòng và không có lý giải thỏa đáng."
        )

        return RecommendationJudgeReport(
            relevance_score=relevance_score,
            ranking_score=ranking_score,
            faithfulness_score=faithfulness_score,
            overall_score=overall,
            strengths=strengths,
            weaknesses=weaknesses,
            rationale=rationale,
        )

    # 2. Đánh giá từng phòng bằng evaluate_room_satisfaction
    room_evals = []
    if evaluate_room_satisfaction is not None and expectation is not None:
        for r in rooms:
            try:
                ev = evaluate_room_satisfaction(r, expectation, budget_tolerance_pct=budget_tolerance_pct)
                room_evals.append(ev)
            except Exception:
                room_evals.append({
                    "price_ok": True,
                    "distance_ok": True,
                    "room_type_ok": True,
                    "area_ok": True,
                    "amenities_ok": True,
                    "is_fully_satisfied": True,
                    "relevance_level": 3,
                })
    else:
        room_evals = [{
            "price_ok": True,
            "distance_ok": True,
            "room_type_ok": True,
            "area_ok": True,
            "amenities_ok": True,
            "is_fully_satisfied": True,
            "relevance_level": 3,
        } for _ in rooms]

    hard_ok_count = sum(1 for e in room_evals if e["price_ok"] and e["distance_ok"] and e["room_type_ok"])
    full_ok_count = sum(1 for e in room_evals if e["is_fully_satisfied"])
    hard_ratio = hard_ok_count / n
    full_ratio = full_ok_count / n

    # --- A. RELEVANCE SCORE (1.0 -> 5.0) ---
    if hard_ratio == 1.0 and full_ratio >= 0.8:
        relevance_score = 5.0
    elif hard_ratio == 1.0 and full_ratio >= 0.5:
        relevance_score = 4.5
    elif hard_ratio == 1.0:
        relevance_score = 4.0
    elif hard_ratio >= 0.6:
        relevance_score = round(3.0 + 1.0 * full_ratio, 1)
    elif hard_ratio >= 0.3:
        relevance_score = round(2.0 + 1.0 * hard_ratio, 1)
    else:
        relevance_score = round(1.0 + 1.0 * hard_ratio, 1)
    relevance_score = max(1.0, min(5.0, relevance_score))

    # --- B. RANKING SCORE (1.0 -> 5.0) ---
    e1 = room_evals[0]
    if n == 1:
        if e1["is_fully_satisfied"]:
            ranking_score = 4.5
        elif e1["price_ok"] and e1["distance_ok"] and e1["room_type_ok"]:
            ranking_score = 4.0
        else:
            ranking_score = 2.0
    else:
        e2 = room_evals[1]
        e1_hard = e1["price_ok"] and e1["distance_ok"] and e1["room_type_ok"]
        e2_hard = e2["price_ok"] and e2["distance_ok"] and e2["room_type_ok"]

        if e1["is_fully_satisfied"] and not e2["is_fully_satisfied"]:
            # Top 1 vượt trội
            ranking_score = 5.0
        elif e1["is_fully_satisfied"] and e2["is_fully_satisfied"]:
            # Cả hai đều hoàn hảo: kiểm tra khoảng cách/giá
            d1 = e1.get("distance_km")
            d2 = e2.get("distance_km")
            if d1 is not None and d2 is not None and d1 <= d2:
                ranking_score = 4.9
            else:
                ranking_score = 4.6
        elif e1_hard and not e2_hard:
            # Top 1 thỏa mãn ràng buộc cứng trong khi Top 2 vi phạm
            ranking_score = 4.5
        elif e1_hard and e2_hard:
            # Cả 2 đều thỏa ràng buộc cứng
            if e1["relevance_level"] >= e2["relevance_level"]:
                ranking_score = 4.0
            else:
                ranking_score = 3.2
        elif not e1_hard and e2_hard:
            # Lỗi xếp hạng: đưa phòng vi phạm lên trước phòng hợp lệ
            ranking_score = 1.5
        else:
            # Cả 2 đều vi phạm
            ranking_score = 2.0
    ranking_score = max(1.0, min(5.0, ranking_score))

    # --- C. FAITHFULNESS SCORE (1.0 -> 5.0) ---
    faithfulness_score = 5.0
    faithfulness_issues: list[str] = []

    if verify_answer_grounding is not None:
        try:
            gr = verify_answer_grounding(
                answer_text=text_reply,
                rooms=rooms,
                user_text=user_query,
            )
            if gr.is_grounded or gr.groundedness_score >= 0.95:
                faithfulness_score = 5.0
            elif gr.groundedness_score >= 0.75:
                faithfulness_score = 4.0
            elif gr.groundedness_score >= 0.50:
                faithfulness_score = 3.0
            else:
                faithfulness_score = 2.0 if gr.groundedness_score > 0 else 1.5
            faithfulness_issues = list(gr.issues or [])
        except Exception:
            faithfulness_score = 4.5
    else:
        # Kiểm tra nhanh số tiền nêu trong câu trả lời có khớp với giá phòng không
        claimed_amounts = _extract_price_and_area_from_text(text_reply)
        actual_prices = []
        for r in rooms:
            if isinstance(r, dict):
                p = r.get("priceNum") or r.get("price_vnd") or 0.0
            else:
                p = getattr(r, "priceNum", getattr(r, "price_vnd", 0.0))
            if p:
                actual_prices.append(float(p))

        if claimed_amounts and actual_prices:
            mismatches = 0
            for ca in claimed_amounts:
                # Cho phép lệch trong khoảng 100k
                if not any(abs(ca - ap) <= 100_000 for ap in actual_prices):
                    mismatches += 1
            if mismatches > 0:
                faithfulness_score = max(2.0, 5.0 - mismatches * 1.0)
                faithfulness_issues.append(f"Phát hiện {mismatches} số tiền trong câu trả lời không khớp giá phòng thực tế.")

    # --- D. OVERALL SCORE & RATIONALE ---
    overall_score = round(
        0.4 * relevance_score + 0.3 * ranking_score + 0.3 * faithfulness_score,
        2,
    )
    overall_score = max(1.0, min(5.0, overall_score))

    strengths: list[str] = []
    if hard_ratio == 1.0:
        strengths.append(f"100% ({n}/{n}) phòng đề xuất tuân thủ nghiêm ngặt các ràng buộc cứng (giá, bán kính, loại phòng).")
    elif hard_ratio >= 0.6:
        strengths.append(f"{hard_ok_count}/{n} phòng tuân thủ ràng buộc cứng.")

    if full_ok_count > 0:
        strengths.append(f"Có {full_ok_count}/{n} phòng đáp ứng trọn vẹn cả các tiện ích mong muốn.")

    if ranking_score >= 4.5:
        strengths.append("Thứ tự xếp hạng tối ưu: Top 1 là lựa chọn tốt nhất theo đa tiêu chí.")

    if faithfulness_score >= 4.5:
        strengths.append("Lời tư vấn trung thực, số liệu giá cả và thông số khớp với dữ liệu thực tế.")

    weaknesses: list[str] = []
    if hard_ratio < 1.0:
        weaknesses.append(f"Có {n - hard_ok_count}/{n} phòng vi phạm ràng buộc cứng (vượt ngân sách hoặc bán kính).")

    if ranking_score <= 2.5:
        weaknesses.append("Chất lượng xếp hạng chưa tối ưu (Top 1 có chất lượng thấp hơn các phòng bên dưới).")

    if faithfulness_issues:
        weaknesses.extend(faithfulness_issues[:2])

    rationale = (
        f"Đánh giá quy tắc IR: Độ phù hợp {relevance_score}/5.0 ({hard_ok_count}/{n} phòng đạt ràng buộc cứng, "
        f"{full_ok_count}/{n} phòng đạt tuyệt đối). Chất lượng xếp hạng {ranking_score}/5.0. "
        f"Độ trung thực thông tin {faithfulness_score}/5.0. Điểm tổng hợp: {overall_score}/5.0."
    )

    return RecommendationJudgeReport(
        relevance_score=relevance_score,
        ranking_score=ranking_score,
        faithfulness_score=faithfulness_score,
        overall_score=overall_score,
        strengths=strengths,
        weaknesses=weaknesses,
        rationale=rationale,
    )


# ============================================================================
# 4. THẨM ĐỊNH CHÍNH THỨC: evaluate_recommendation_quality
# ============================================================================


def _format_room_summary_for_prompt(rooms: Sequence[Any]) -> str:
    """Format danh sách phòng gọn gàng, trực quan để đưa vào prompt cho LLM Judge."""
    lines: list[str] = []
    for idx, r in enumerate(rooms, start=1):
        if hasattr(r, "model_dump"):
            rid = getattr(r, "id", f"room_{idx}")
            title = getattr(r, "title", "Phòng trọ")
            price_num = getattr(r, "priceNum", 0.0) or 0.0
            price_str = getattr(r, "price", f"{price_num:,.0f} đ")
            dist = getattr(r, "distance", "N/A")
            area = getattr(r, "area_m2", getattr(r, "area", "N/A"))
            tags = list(getattr(r, "tags", []) or [])
        elif isinstance(r, dict):
            rid = r.get("id", f"room_{idx}")
            title = r.get("title", "Phòng trọ")
            price_num = r.get("priceNum") or r.get("price_vnd") or 0.0
            price_str = r.get("price", f"{price_num:,.0f} đ")
            dist = r.get("distance", "N/A")
            area = r.get("area_m2") or r.get("area", "N/A")
            tags = list(r.get("tags") or [])
        else:
            rid = getattr(r, "id", f"room_{idx}")
            title = getattr(r, "title", "Phòng trọ")
            price_num = getattr(r, "priceNum", 0.0)
            price_str = str(price_num)
            dist = getattr(r, "distance", "N/A")
            area = getattr(r, "area_m2", "N/A")
            tags = list(getattr(r, "tags", []) or [])

        lines.append(
            f"Top {idx} [Mã: {rid}]: {title} | Giá: {price_str} ({price_num:,.0f} VNĐ) | "
            f"Khoảng cách: {dist} | Diện tích: {area} m² | Tiện ích: {', '.join(str(t) for t in tags[:6])}"
        )
    return "\n".join(lines)


def _format_expectation_for_prompt(exp: Any) -> str:
    """Format các ràng buộc của GroundTruthExpectation vào prompt."""
    if exp is None:
        return "Không có ràng buộc cụ thể."

    lines: list[str] = []
    if getattr(exp, "max_budget", None):
        lines.append(f"- Ngân sách tối đa: {exp.max_budget:,.0f} VNĐ")
    if getattr(exp, "min_budget", None):
        lines.append(f"- Ngân sách tối thiểu: {exp.min_budget:,.0f} VNĐ")
    if getattr(exp, "target_location_name", None):
        lines.append(f"- Địa điểm mục tiêu: {exp.target_location_name}")
    if getattr(exp, "max_distance_km", None):
        lines.append(f"- Bán kính tối đa: {exp.max_distance_km} km")
    if getattr(exp, "required_amenities", None):
        lines.append(f"- Tiện ích bắt buộc: {', '.join(exp.required_amenities)}")
    if getattr(exp, "allowed_room_types", None):
        lines.append(f"- Loại phòng cho phép: {', '.join(exp.allowed_room_types)}")
    if getattr(exp, "forbidden_room_types", None):
        lines.append(f"- Loại phòng bị cấm: {', '.join(exp.forbidden_room_types)}")
    if getattr(exp, "min_area_m2", None):
        lines.append(f"- Diện tích tối thiểu: {exp.min_area_m2} m²")

    return "\n".join(lines) if lines else "Không có ràng buộc cụ thể."


def evaluate_recommendation_quality(
    model: Optional[Any],
    user_query: str,
    expectation: Any,
    rooms: Sequence[Any],
    text_reply: str,
    insights: Optional[Any] = None,
    budget_tolerance_pct: float = 0.0,
) -> RecommendationJudgeReport:
    """Đánh giá chất lượng khuyến nghị phòng trọ bằng LLM-as-a-Judge (hoặc rule-based fallback).

    Thẩm định theo 3 chiều:
    1. relevance_score (1.0 - 5.0): Mức độ phù hợp với nhu cầu và ràng buộc.
    2. ranking_score (1.0 - 5.0): Chất lượng xếp hạng đa tiêu chí, Top 1 có tối ưu nhất không.
    3. faithfulness_score (1.0 - 5.0): Tính trung thực của lời tư vấn so với dữ liệu phòng.
    4. overall_score: 0.4 * relevance + 0.3 * ranking + 0.3 * faithfulness.
    """
    if model is None:
        return _rule_based_recommendation_judge(
            user_query=user_query,
            expectation=expectation,
            rooms=rooms,
            text_reply=text_reply,
            insights=insights,
            budget_tolerance_pct=budget_tolerance_pct,
        )

    system_prompt = (
        "Bạn là Chuyên gia Đánh giá Hệ thống Khuyến nghị Phòng trọ Thông minh (LLM-as-a-Judge) "
        "thuộc Đồ án Tốt nghiệp Đại học Công nghệ Thông tin (UIT) - Dự án Homigo.\n"
        "Nhiệm vụ của bạn là thẩm định chất lượng danh sách phòng trọ gợi ý và câu trả lời tư vấn "
        "dựa trên các tiêu chí sau (chấm điểm từ 1.0 đến 5.0, bước 0.1 hoặc 0.5):\n\n"
        "1. relevance_score (1.0 - 5.0): Mức độ phù hợp của các phòng được gợi ý so với yêu cầu và kỳ vọng của người dùng.\n"
        "   - 5.0: Tất cả phòng đều thỏa mãn hoàn hảo mọi ràng buộc cứng (ngân sách, bán kính, loại phòng) và tiện ích mong muốn.\n"
        "   - 4.0: Thỏa mãn 100% ràng buộc cứng, có thể thiếu 1 tiện ích nhỏ.\n"
        "   - 3.0: Thỏa mãn phần lớn ràng buộc cứng, hoặc chỉ nới lỏng nhẹ trong phạm vi chấp nhận.\n"
        "   - 1.0 - 2.0: Vi phạm nghiêm trọng ngân sách, bán kính hoặc loại phòng bị cấm.\n\n"
        "2. ranking_score (1.0 - 5.0): Chất lượng xếp hạng danh sách phòng.\n"
        "   - 5.0: Top 1 thực sự là lựa chọn tối ưu và vượt trội nhất (rẻ nhất, gần nhất hoặc tiện nghi nhất).\n"
        "   - 4.0: Xếp hạng hợp lý, Top 1 và Top 2 tương đương về chất lượng.\n"
        "   - 1.0 - 2.0: Xếp hạng sai lệch (Top 1 kém hơn Top 2 hoặc Top 1 vi phạm tiêu chí trong khi Top 2 đạt).\n\n"
        "3. faithfulness_score (1.0 - 5.0): Tính trung thực của lời tư vấn so với thuộc tính thực tế của phòng.\n"
        "   - 5.0: Mọi số liệu (giá thuê, diện tích, khoảng cách, tiện ích) trong lời tư vấn khớp 100% với dữ liệu phòng.\n"
        "   - 3.0: Có một vài suy diễn nhỏ nhưng không làm sai lệch số liệu cốt lõi.\n"
        "   - 1.0 - 2.0: Ảo giác nghiêm trọng (bịa đặt giá rẻ hơn thực tế, nói phòng có tiện ích mà dữ liệu không có).\n\n"
        "4. overall_score: Tính theo công thức chuẩn: 0.4 * relevance_score + 0.3 * ranking_score + 0.3 * faithfulness_score.\n"
        "5. strengths: Danh sách điểm mạnh cụ thể.\n"
        "6. weaknesses: Danh sách điểm yếu hoặc điều chưa tối ưu.\n"
        "7. rationale: Đoạn giải thích chi tiết, khách quan về lý do chấm điểm."
    )

    exp_text = _format_expectation_for_prompt(expectation)
    rooms_text = _format_room_summary_for_prompt(rooms) if rooms else "Không có phòng nào được trả về."
    insights_text = str(insights) if insights else "Không có phân tích so sánh."

    human_prompt = (
        f"<user_query>\n{user_query}\n</user_query>\n\n"
        f"<ground_truth_expectation>\n{exp_text}\n</ground_truth_expectation>\n\n"
        f"<suggested_rooms>\n{rooms_text}\n</suggested_rooms>\n\n"
        f"<agent_text_reply>\n{text_reply}\n</agent_text_reply>\n\n"
        f"<agent_insights>\n{insights_text}\n</agent_insights>"
    )

    try:
        judge_chain = model.with_structured_output(RecommendationJudgeReport)
        report = judge_chain.invoke([
            ("system", system_prompt),
            ("human", human_prompt),
        ])

        if isinstance(report, RecommendationJudgeReport):
            # Tính lại overall_score để đảm bảo trọng số chuẩn xác 0.4 / 0.3 / 0.3
            computed_overall = round(
                0.4 * report.relevance_score + 0.3 * report.ranking_score + 0.3 * report.faithfulness_score,
                2,
            )
            report.overall_score = max(1.0, min(5.0, computed_overall))
            return report

        if isinstance(report, dict):
            rel = float(report.get("relevance_score", 3.0))
            rk = float(report.get("ranking_score", 3.0))
            ft = float(report.get("faithfulness_score", 3.0))
            ov = round(0.4 * rel + 0.3 * rk + 0.3 * ft, 2)
            return RecommendationJudgeReport(
                relevance_score=max(1.0, min(5.0, rel)),
                ranking_score=max(1.0, min(5.0, rk)),
                faithfulness_score=max(1.0, min(5.0, ft)),
                overall_score=max(1.0, min(5.0, ov)),
                strengths=[str(s) for s in report.get("strengths", []) if str(s).strip()],
                weaknesses=[str(w) for w in report.get("weaknesses", []) if str(w).strip()],
                rationale=str(report.get("rationale", "")),
            )

        return _rule_based_recommendation_judge(
            user_query=user_query,
            expectation=expectation,
            rooms=rooms,
            text_reply=text_reply,
            insights=insights,
            budget_tolerance_pct=budget_tolerance_pct,
        )

    except Exception as e:
        logger.warning("evaluate_recommendation_quality: Lỗi khi gọi LLM Judge, fallback rule-based: %s", e)
        return _rule_based_recommendation_judge(
            user_query=user_query,
            expectation=expectation,
            rooms=rooms,
            text_reply=text_reply,
            insights=insights,
            budget_tolerance_pct=budget_tolerance_pct,
        )


compute_overall_score = RecommendationJudgeReport.compute_overall_score

__all__ = [
    "RecommendationJudgeReport",
    "compute_overall_score",
    "get_judge_llm",
    "evaluate_recommendation_quality",
    "_rule_based_recommendation_judge",
]
