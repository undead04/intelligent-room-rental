"""Guardrail lớp 0 + 1 (code, xác định, rẻ). Lớp 2 (off-topic / injection tinh vi) do NLU (intent) đảm nhiệm.

  Lớp 0: chuẩn hoá (NFKC, bỏ ký tự ẩn/zero-width, gộp homoglyph Cyrillic, bỏ dấu), giới hạn độ dài.
  Lớp 1: luật độ tin cậy CAO, chạy trên văn bản đã bỏ dấu => 'bo qua chi dan truoc' cũng bị bắt.
  scan_untrusted_text(): cùng bộ luật cho dữ liệu bên thứ ba (tiêu đề/mô tả tin đăng) - đường injection gián tiếp.

Đã gỡ OFF_TOPIC_PATTERNS và cờ `has_housing_context` (từ khoá chung như 'giá', 'xe' khiến câu "giá bitcoin" lọt qua).
Các luật cố tình chặt để tránh chặn nhầm câu hợp lệ ("bỏ qua quy tắc cũ của nhà trọ" KHÔNG bị chặn).
SQL injection KHÔNG phải việc của lớp này (backend tham số hoá truy vấn); chỉ giữ để log payload đáng ngờ.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Optional

from pydantic import BaseModel

from utils.text import strip_accents

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 4000


class GuardrailResult(BaseModel):
    allowed: bool
    reason: Optional[str] = None
    safe_response: Optional[str] = None


_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\u2061\u2062\u2063\u2064\ufeff\u00ad\u180e"), None)
# homoglyph Cyrillic/Greek thường dùng để lách bộ lọc -> chữ Latin tương ứng
_CONFUSABLES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "һ": "h",
    "ο": "o", "ν": "v", "ι": "i", "α": "a", "ε": "e", "ρ": "p",
})


def normalize_for_guard(text: str) -> str:
    """Văn bản đã chuẩn hoá để khớp luật: không dấu, chữ thường, không ký tự ẩn/điều khiển, khoảng trắng gọn."""
    t = unicodedata.normalize("NFKC", text or "").translate(_INVISIBLE)
    t = "".join(c for c in t if unicodedata.category(c)[0] != "C" or c in "\n\t ")
    t = t.lower().translate(_CONFUSABLES)
    return " ".join(strip_accents(t).split())


_P = lambda s: re.compile(s)  # noqa: E731

# name -> pattern (trên văn bản đã bỏ dấu)
INJECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "override_vi": _P(r"\b(bo qua|quen|huy bo|huy|phot lo|vo hieu hoa)\b\s+(het\s+|tat ca\s+|toan bo\s+)?(cac\s+|nhung\s+)?(chi dan|huong dan|lenh|prompt)\b"),
    "override_vi_rules": _P(r"\b(bo qua|quen|huy bo|huy|phot lo)\b\s+(het\s+|tat ca\s+|toan bo\s+)?(cac\s+)?(quy tac|luat)\s+(he thong|cua ban|ban dau|da duoc cai dat)"),
    "override_en": _P(r"\b(ignore|disregard|forget|override|bypass)\b\W+(\w+\W+){0,4}(instructions?|directions?|prompts?|rules?|guidelines?|above|previous|prior)\b"),
    "reveal_prompt": _P(r"\b(system|developer|hidden|internal)\s*(prompt|message|instructions?)\b"),
    "reveal_vi": _P(r"\b(tiet lo|in ra|hien thi|cho xem|lap lai|doc lai)\b.{0,30}\b(prompt|chi dan he thong|huong dan he thong)\b"),
    "reveal_en": _P(r"\b(reveal|show|print|repeat|leak)\b.{0,30}\b(prompt|instructions?)\b"),
    "role_hijack": _P(r"\b(you are now|from now on you|tu bay gio ban la|tu gio ban la)\b"),
    "jailbreak": _P(r"\b(jailbreak|dan mode|developer mode|do anything now)\b"),
}

UNSAFE_PATTERNS: dict[str, re.Pattern[str]] = {
    "roleplay_hacker": _P(r"\bdong vai\b\s+(la\s+)?(mot\s+)?(hacker|toi pham)"),
    "malware": _P(r"\bviet\b\s+(ma|code)\s+(doc|virus|trojan|exploit|ransomware|keylogger)"),
    "hack_howto": _P(r"\bhuong dan\b\s+hack\b"),
}

# Chỉ để log/gắn cờ, không chặn (xem docstring)
PAYLOAD_PATTERNS: dict[str, re.Pattern[str]] = {
    "sql_union": _P(r"\bunion\s+(all\s+)?select\b"),
    "sql_drop": _P(r"\bdrop\s+(table|database|view)\b"),
    "sql_comment": _P(r";\s*--"),
}

_SAFE_INJECTION = (
    "Xin lỗi, tôi là Homigo AI - Cố vấn chuyên hỗ trợ tìm kiếm phòng trọ và nhà ở. "
    "Tôi được thiết lập để từ chối các yêu cầu can thiệp vào chỉ dẫn hệ thống. "
    "Bạn có cần tôi hỗ trợ tìm phòng trọ ở khu vực nào không?"
)
_SAFE_UNSAFE = (
    "Xin lỗi, tôi chỉ hỗ trợ tìm kiếm phòng trọ và tư vấn thuê nhà nên không thể giúp yêu cầu này. "
    "Bạn muốn tìm phòng ở khu vực nào để mình hỗ trợ nhé?"
)
_SAFE_EMPTY = "Bạn chưa nhập câu hỏi. Hãy cho tôi biết nhu cầu tìm phòng trọ của bạn nhé!"
_SAFE_LONG = "Tin nhắn của bạn quá dài. Bạn có thể rút gọn nhu cầu (khu vực, ngân sách, tiện ích) để Homigo hỗ trợ nhé!"


def scan_untrusted_text(text: str) -> list[str]:
    """Tên các luật injection khớp trong văn bản bên thứ ba (tiêu đề/mô tả tin đăng). [] = sạch."""
    t = normalize_for_guard(text)
    return [n for n, p in {**INJECTION_PATTERNS, **UNSAFE_PATTERNS}.items() if p.search(t)]


def check_guardrails(user_text: str) -> GuardrailResult:
    raw = user_text or ""
    if not raw.strip():
        return GuardrailResult(allowed=False, reason="EMPTY_INPUT", safe_response=_SAFE_EMPTY)
    if len(raw) > MAX_INPUT_CHARS:
        return GuardrailResult(allowed=False, reason="INPUT_TOO_LONG", safe_response=_SAFE_LONG)

    t = normalize_for_guard(raw)
    if not t:   # toàn ký tự ẩn
        return GuardrailResult(allowed=False, reason="EMPTY_INPUT", safe_response=_SAFE_EMPTY)

    for name, p in INJECTION_PATTERNS.items():
        if p.search(t):
            logger.warning("Guardrail: injection (%s)", name)
            return GuardrailResult(allowed=False, reason="PROMPT_INJECTION_DETECTED", safe_response=_SAFE_INJECTION)
    for name, p in UNSAFE_PATTERNS.items():
        if p.search(t):
            logger.warning("Guardrail: unsafe (%s)", name)
            return GuardrailResult(allowed=False, reason="UNSAFE_REQUEST_DETECTED", safe_response=_SAFE_UNSAFE)
    for name, p in PAYLOAD_PATTERNS.items():
        if p.search(t):
            logger.warning("Guardrail: payload đáng ngờ (%s) - không chặn, backend phải tham số hoá truy vấn", name)
    return GuardrailResult(allowed=True)
