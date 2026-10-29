"""Module đánh giá độ phù hợp của câu trả lời so với câu hỏi của người dùng (Answer Relevance - RAG Triad).

Cung cấp:
- RelevanceJudgeReport: Kết quả thẩm định (score, unaddressed_aspects, reason)
- evaluate_answer_relevance: Hàm đánh giá (chạy LLM-as-a-judge khi có model, hoặc rule-based semantic coverage khi offline)
- RELEVANCE_CASES: Bộ dữ liệu kiểm thử chuẩn hoá các tình huống hỏi phòng trọ thực tế của sinh viên.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RelevanceJudgeReport(BaseModel):
    score: float = Field(..., ge=0.0, le=1.0, description="Điểm đánh giá độ phù hợp (0.0 đến 1.0)")
    unaddressed_aspects: list[str] = Field(default_factory=list, description="Các khía cạnh hoặc câu hỏi người dùng nêu nhưng câu trả lời bỏ qua")
    reason: str = Field("", description="Lý do ngắn gọn giải thích điểm số")


@dataclass(frozen=True)
class RelevanceCase:
    user_query: str
    answer: str
    expected_relevant: bool
    description: str
    target_topics: tuple[str, ...] = ()


TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "thú cưng": ("thú cưng", "thu cung", "chó", "mèo", "meo", "pet", "nuôi chó", "nuôi mèo", "nuôi pet"),
    "tiền cọc": ("tiền cọc", "tien coc", "đặt cọc", "dat coc", "cọc"),
    "an ninh": ("an ninh", "an toan", "an toàn", "camera", "bảo vệ", "bao ve", "trộm", "trom"),
    "giờ giấc": ("giờ giấc", "gio giac", "tự do", "tu do", "24/24", "24/7", "khóa vân tay", "khoa van tay", "cổng riêng", "cong rieng", "cửa cuốn", "cua cuon", "về muộn", "ve muon"),
    "điện nước": ("điện", "dien", "nước", "nuoc", "kwh", "số điện", "so dien", "khối nước", "khoi nuoc"),
    "gửi xe": ("xe", "bãi xe", "bai xe", "nhà xe", "nha xe", "gửi xe", "gui xe", "để xe", "de xe"),
    "ở ghép": ("ở ghép", "o ghep", "ở chung", "o chung", "2 người", "hai người", "2 bạn", "o 2", "ở 2"),
}


RELEVANCE_CASES: tuple[RelevanceCase, ...] = (
    RelevanceCase(
        user_query="Phòng này có cho nuôi thú cưng không và cọc mấy tháng?",
        answer="Về thắc mắc của bạn đối với phòng nhatot_101: Phòng cho phép nuôi thú cưng nhỏ (mèo/cún nhỏ) và tiền cọc là 1 tháng tiền phòng (3.5 triệu).",
        expected_relevant=True,
        description="Đầy đủ: trả lời cả thú cưng và tiền cọc",
        target_topics=("thú cưng", "tiền cọc"),
    ),
    RelevanceCase(
        user_query="Phòng này có cho nuôi thú cưng không và cọc mấy tháng?",
        answer="Phòng nhatot_101 có giá 3.5 triệu một tháng, diện tích 22m2, có ban công thoáng mát và gần trạm xe buýt.",
        expected_relevant=False,
        description="Lạc đề/bỏ sót: người hỏi thú cưng và cọc nhưng chỉ trả lời diện tích và ban công",
        target_topics=("thú cưng", "tiền cọc"),
    ),
    RelevanceCase(
        user_query="Khu vực này an ninh thế nào, ban đêm đi làm về muộn có giờ giấc tự do không?",
        answer="Khu trọ có hệ thống camera an ninh 24/7 và cổng ra vào sử dụng khóa vân tay nên giờ giấc hoàn toàn tự do cho bạn đi làm về muộn.",
        expected_relevant=True,
        description="Đầy đủ: trả lời an ninh và giờ giấc tự do",
        target_topics=("an ninh", "giờ giấc"),
    ),
    RelevanceCase(
        user_query="Khu vực này an ninh thế nào, ban đêm đi làm về muộn có giờ giấc tự do không?",
        answer="Phòng trọ này được trang bị sẵn máy lạnh Inverter, tủ quần áo gỗ và giường nệm mới 100%.",
        expected_relevant=False,
        description="Lạc đề/bỏ sót: người hỏi an ninh và giờ giấc nhưng chỉ trả lời nội thất",
        target_topics=("an ninh", "giờ giấc"),
    ),
    RelevanceCase(
        user_query="Cho mình hỏi tiền điện nước tính thế nào và có tốn phí gửi xe máy không?",
        answer="Chi phí dịch vụ tại phòng gồm: điện 3.500đ/kWh, nước 20.000đ/m3, và có chỗ để xe máy miễn phí ở tầng trệt.",
        expected_relevant=True,
        description="Đầy đủ: trả lời biểu phí điện nước và chỗ để xe",
        target_topics=("điện nước", "gửi xe"),
    ),
    RelevanceCase(
        user_query="Cho mình hỏi tiền điện nước tính thế nào và có tốn phí gửi xe máy không?",
        answer="Phòng trọ có diện tích 20m2 sạch sẽ, nằm ở khu dân cư đông đúc và gần chợ.",
        expected_relevant=False,
        description="Lạc đề/bỏ sót: người hỏi điện nước và xe nhưng chỉ mô tả vị trí chung chung",
        target_topics=("điện nước", "gửi xe"),
    ),
    RelevanceCase(
        user_query="Tìm phòng trọ gần Đại học Quốc Gia dưới 3 triệu cho sinh viên",
        answer="Homigo gợi ý cho bạn 2 phòng trọ gần Đại học Quốc Gia với giá dưới 3 triệu: Top 1 phòng nhatot_101 giá 2.8 triệu và Top 2 phòng nhatot_102 giá 3 triệu, cả hai đều có an ninh tốt.",
        expected_relevant=True,
        description="Đầy đủ: câu tìm phòng được đề xuất đúng danh sách phòng phù hợp tiêu chí",
    ),
    RelevanceCase(
        user_query="Tìm phòng trọ gần Đại học Quốc Gia dưới 3 triệu cho sinh viên",
        answer="Thị trường bất động sản quý này có nhiều biến động, bạn nên tìm hiểu kỹ thủ tục pháp lý trước khi ký hợp đồng mua bán nhà đất.",
        expected_relevant=False,
        description="Lạc đề: người dùng tìm phòng sinh viên nhưng bot nói về thị trường bất động sản mua bán",
    ),
)


def _rule_based_relevance_judge(user_query: str, answer_text: str) -> RelevanceJudgeReport:
    """Đánh giá offline dựa trên độ phủ ý định và chủ đề khi không có LLM."""
    uq_lower = (user_query or "").lower()
    ans_lower = (answer_text or "").lower()

    if not ans_lower.strip():
        return RelevanceJudgeReport(score=0.0, unaddressed_aspects=["Câu trả lời rỗng"], reason="Không có nội dung trả lời")

    # Xác định các chủ đề cụ thể xuất hiện trong câu hỏi
    present_topics: list[str] = []
    for topic, kws in TOPIC_KEYWORDS.items():
        if any(kw in uq_lower for kw in kws):
            present_topics.append(topic)

    # Nếu câu hỏi có chủ đề cụ thể (thú cưng, giờ giấc, cọc...)
    if present_topics:
        missing: list[str] = []
        for topic in present_topics:
            kws = TOPIC_KEYWORDS[topic]
            if not any(kw in ans_lower for kw in kws):
                missing.append(topic)

        if not missing:
            return RelevanceJudgeReport(
                score=1.0,
                unaddressed_aspects=[],
                reason=f"Câu trả lời bao quát đầy đủ các chủ đề được hỏi: {', '.join(present_topics)}",
            )
        matched_count = len(present_topics) - len(missing)
        score = round(matched_count / len(present_topics), 2)
        # Nếu bị bỏ lỡ hoàn toàn các chủ đề cốt lõi thì điểm không vượt quá 0.2
        if matched_count == 0:
            score = 0.1
        return RelevanceJudgeReport(
            score=score,
            unaddressed_aspects=missing,
            reason=f"Bỏ sót các chủ đề người dùng yêu cầu: {', '.join(missing)}",
        )

    # Câu tìm kiếm phòng thông thường
    housing_terms = ("phòng", "phong", "trọ", "tro", "thuê", "thue", "nhatot", "top 1", "top 2", "triệu", "trieu")
    ans_has_housing = sum(1 for term in housing_terms if term in ans_lower)
    is_off_topic = any(w in ans_lower for w in ("bất động sản mua bán", "nhà đất", "chứng khoán", "thị trường bất động sản"))

    if is_off_topic:
        return RelevanceJudgeReport(score=0.1, unaddressed_aspects=["Lạc đề sang bất động sản mua bán"], reason="Câu trả lời lạc đề")

    if ans_has_housing >= 2:
        return RelevanceJudgeReport(score=0.95, unaddressed_aspects=[], reason="Câu trả lời đáp ứng trực tiếp nhu cầu tìm phòng")

    return RelevanceJudgeReport(score=0.3, unaddressed_aspects=["Chưa cung cấp thông tin phòng"], reason="Câu trả lời không chứa thông tin phòng phù hợp")


def evaluate_answer_relevance(
    model: Any,
    user_query: str,
    answer_text: str,
) -> RelevanceJudgeReport:
    """Đánh giá độ phù hợp (Answer Relevance - RAG Triad).

    Nếu model != None: gọi LLM Judge.
    Nếu model == None: dùng rule-based coverage judge.
    """
    if model is None:
        return _rule_based_relevance_judge(user_query, answer_text)

    system_prompt = (
        "Bạn là chuyên gia thẩm định chất lượng câu trả lời (LLM-as-a-Judge) theo chuẩn RAG Triad.\n"
        "Nhiệm vụ: Chấm điểm Answer Relevance (0.0 đến 1.0) xem <answer> có giải quyết trực tiếp, "
        "đầy đủ các câu hỏi hoặc nhu cầu trong <user_query> không.\n\n"
        "Tiêu chí chấm điểm:\n"
        "- 0.85 - 1.0: Trả lời trực tiếp, đầy đủ mọi câu hỏi hoặc nhu cầu trong câu hỏi.\n"
        "- 0.5 - 0.8: Trả lời được câu hỏi chính nhưng bỏ sót câu hỏi phụ hoặc tiêu chí kèm theo.\n"
        "- 0.0 - 0.4: Lạc đề, né tránh, nói chung chung hoặc bỏ qua hoàn toàn câu hỏi cốt lõi của người dùng.\n\n"
        "Nếu có câu hỏi/tiêu chí bị bỏ sót, liệt kê cụ thể vào 'unaddressed_aspects'."
    )
    human_prompt = f"<user_query>\n{user_query}\n</user_query>\n<answer>\n{answer_text}\n</answer>"

    try:
        rep = model.with_structured_output(RelevanceJudgeReport).invoke([
            ("system", system_prompt),
            ("human", human_prompt),
        ])
        if isinstance(rep, RelevanceJudgeReport):
            return rep
        if isinstance(rep, dict):
            return RelevanceJudgeReport(
                score=float(rep.get("score", 0.0)),
                unaddressed_aspects=[str(x) for x in rep.get("unaddressed_aspects", []) if str(x).strip()],
                reason=str(rep.get("reason", "")),
            )
        return _rule_based_relevance_judge(user_query, answer_text)
    except Exception:
        logger.warning("evaluate_answer_relevance: gọi LLM Judge lỗi, fallback rule-based", exc_info=True)
        return _rule_based_relevance_judge(user_query, answer_text)
