"""Module Guardrails: Bảo vệ AI Agent khỏi Prompt Injection, Jailbreak và câu hỏi ngoài luồng.
Phục vụ mục tiêu Security & Safety trong đề tài Khóa luận tốt nghiệp.
"""

from __future__ import annotations

import re
from typing import Optional
from pydantic import BaseModel


class GuardrailResult(BaseModel):
    allowed: bool
    reason: Optional[str] = None
    safe_response: Optional[str] = None


# Danh sách các mẫu Prompt Injection / Jailbreak phổ biến
INJECTION_PATTERNS = [
    r"bỏ\s*qua\s*(toàn\s*bộ\s*)?(các\s*)?(chỉ\s*dẫn|hướng\s*dẫn|quy\s*tắc|lệnh)\s*(trước|cũ)",
    r"quên\s*(hết|đi)\s*(các\s*)?(chỉ\s*dẫn|vai\s*trò|quy\s*tắc)",
    r"ignore\s+(all\s+)?(previous\s+)?(instructions|directions|prompts)",
    r"disregard\s+(all\s+)?previous",
    r"system\s*prompt",
    r"reveal\s+(the\s+)?(system|internal)\s+(prompt|instructions)",
    r"in\s*(ra\s*)?(toàn\s*bộ\s*)?system\s*prompt",
    r"jailbreak",
    r"dan\s*mode",
    r"developer\s*mode",
    r"hãy\s*đóng\s*vai\s*(một\s*)?(hacker|tội\s*phạm)",
    r"viết\s*(mã|code)\s*(độc|virus|trojan|exploit)",
    r"hướng\s*dẫn\s*hack",
    # SQL Injection patterns
    r"\b(union\s+(all\s+)?select)\b",
    r"\b(drop\s+(table|database|view))\b",
    r"(\b(or|and)\b\s+[\'\"]?\w+[\'\"]?\s*=\s*[\'\"]?\w+[\'\"]?)",
    r";\s*--",
]

# Từ khóa đặc thù thuộc miền Phòng trọ & Nhà ở
HOUSING_KEYWORDS = [
    "phòng", "trọ", "nhà", "căn hộ", "thuê", "chung cư", "chỗ ở", "ktx", "ký túc xá",
    "giá", "triệu", "vnd", "tiền", "diện tích", "m2", "gác", "máy lạnh", "nội thất",
    "vị trí", "đường", "quận", "phường", "thành phố", "gần", "uit", "đại học", "làng đại học",
    "an ninh", "wifi", "xe", "bếp", "thú cưng", "mèo", "chó", "chủ", "cọc", "homigo",
]

# Từ khóa chắc chắn ngoài luồng (Off-topic)
OFF_TOPIC_PATTERNS = [
    r"giải\s*(?:bài\s*toán|phương\s*trình|đề\s*thi|hóa\s*học|vật\s*lý)",
    r"thơ\s*tình|bài\s*thơ|đoạn\s*văn|tiểu\s*thuyết|viết\s+(?:một\s+)?(?:bài\s+)?thơ",
    r"dịch\s*(?:đoạn\s*văn\s*)?sang\s*tiếng\s*(?:anh|pháp|trung|nhật)",
    r"chơi\s*(?:game|cờ\s*vua|cờ\s*tướng|đố\s*vui)",
    r"thời\s*tiết\s*ngày\s*mai",
    r"chứng\s*khoán|tiền\s*ảo|bitcoin|crypto",
]


def check_guardrails(user_text: str) -> GuardrailResult:
    """Kiểm tra an toàn câu hỏi của người dùng trước khi gửi cho LLM.

    Returns:
        GuardrailResult(allowed=True) nếu an toàn.
        GuardrailResult(allowed=False, reason=..., safe_response=...) nếu phát hiện vi phạm.
    """
    clean_text = user_text.strip().lower()

    if not clean_text:
        return GuardrailResult(
            allowed=False,
            reason="EMPTY_INPUT",
            safe_response="Bạn chưa nhập câu hỏi. Hãy cho tôi biết nhu cầu tìm phòng trọ của bạn nhé!",
        )

    # 1. Kiểm tra Prompt Injection / Jailbreak
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, clean_text, re.IGNORECASE):
            return GuardrailResult(
                allowed=False,
                reason="PROMPT_INJECTION_DETECTED",
                safe_response=(
                    "Xin lỗi, tôi là Homigo AI - Cố vấn chuyên hỗ trợ tìm kiếm phòng trọ và nhà ở. "
                    "Tôi được thiết lập để từ chối các yêu cầu can thiệp vào chỉ dẫn hệ thống. "
                    "Bạn có cần tôi hỗ trợ tìm phòng trọ ở khu vực nào không?"
                ),
            )

    # 2. Kiểm tra câu hỏi ngoài luồng (Off-topic)
    has_housing_context = any(kw in clean_text for kw in HOUSING_KEYWORDS)

    if not has_housing_context:
        for off_pattern in OFF_TOPIC_PATTERNS:
            if re.search(off_pattern, clean_text, re.IGNORECASE):
                return GuardrailResult(
                    allowed=False,
                    reason="OFF_TOPIC_QUERY",
                    safe_response=(
                        "Tôi là Homigo AI - Trợ lý hỗ trợ tìm kiếm phòng trọ và căn hộ. "
                        "Tôi chỉ có thể hỗ trợ các câu hỏi liên quan đến chỗ ở, giá thuê và tiện ích sinh hoạt. "
                        "Bạn có thể cho tôi biết bạn đang muốn tìm phòng gần trường học hay khu vực nào không?"
                    ),
                )

    return GuardrailResult(allowed=True)
