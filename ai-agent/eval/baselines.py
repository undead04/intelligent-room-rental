"""Bản cũ của guardrail và kiểm chứng câu trả lời (port NGUYÊN VĂN logic từ code gốc) để so sánh công bằng trong ablation."""

from __future__ import annotations

import re
import unicodedata
from typing import Optional, Sequence

from domain.schemas import RoomItem, UserPreferenceState

# ---------------------------------------------------------------- guardrail cũ
_OLD_INJECTION = [
    r"bỏ\s*qua\s*(toàn\s*bộ\s*)?(các\s*)?(chỉ\s*dẫn|hướng\s*dẫn|quy\s*tắc|lệnh)\s*(trước|cũ)",
    r"quên\s*(hết|đi)\s*(các\s*)?(chỉ\s*dẫn|vai\s*trò|quy\s*tắc)",
    r"ignore\s+(all\s+)?(previous\s+)?(instructions|directions|prompts)",
    r"disregard\s+(all\s+)?previous",
    r"system\s*prompt",
    r"reveal\s+(the\s+)?(system|internal)\s+(prompt|instructions)",
    r"in\s*(ra\s*)?(toàn\s*bộ\s*)?system\s*prompt",
    r"jailbreak", r"dan\s*mode", r"developer\s*mode",
    r"hãy\s*đóng\s*vai\s*(một\s*)?(hacker|tội\s*phạm)",
    r"viết\s*(mã|code)\s*(độc|virus|trojan|exploit)",
    r"hướng\s*dẫn\s*hack",
    r"\b(union\s+(all\s+)?select)\b", r"\b(drop\s+(table|database|view))\b",
    r"(?:[\'\"]\s*(?:or|and)\b\s*[\'\"]?\w+[\'\"]?\s*=\s*[\'\"]?\w+|\b(?:or|and)\b\s+[\'\"]?\w+[\'\"]?\s*=\s*[\'\"]?\w+[\'\"]?\s*(?:--|#|/\*))",
    r";\s*--",
]
_OLD_HOUSING = [
    "phòng", "trọ", "nhà", "căn hộ", "thuê", "chung cư", "chỗ ở", "ktx", "ký túc xá", "giá", "triệu", "vnd", "tiền", "diện tích", "m2", "gác",
    "máy lạnh", "nội thất", "vị trí", "đường", "quận", "phường", "thành phố", "gần", "uit", "đại học", "làng đại học", "an ninh", "wifi", "xe",
    "bếp", "thú cưng", "mèo", "chó", "chủ", "cọc", "homigo",
]
_OLD_HOUSING_RE = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(k) for k in sorted(_OLD_HOUSING, key=len, reverse=True)) + r")(?!\w)", re.IGNORECASE)
_OLD_OFF_TOPIC = [
    r"giải\s*(?:bài\s*toán|phương\s*trình|đề\s*thi|hóa\s*học|vật\s*lý)",
    r"thơ\s*tình|bài\s*thơ|đoạn\s*văn|tiểu\s*thuyết|viết\s+(?:một\s+)?(?:bài\s+)?thơ",
    r"dịch\s*(?:đoạn\s*văn\s*)?sang\s*tiếng\s*(?:anh|pháp|trung|nhật)",
    r"chơi\s*(?:game|cờ\s*vua|cờ\s*tướng|đố\s*vui)",
    r"thời\s*tiết\s*ngày\s*mai",
    r"chứng\s*khoán|tiền\s*ảo|bitcoin|crypto",
]


def old_guardrail(text: str) -> tuple[bool, Optional[str]]:
    """(allowed, reason) theo guardrails.py CŨ."""
    clean = unicodedata.normalize("NFC", (text or "").strip().lower())
    if not clean:
        return False, "EMPTY_INPUT"
    for p in _OLD_INJECTION:
        if re.search(p, clean, re.IGNORECASE):
            return False, "PROMPT_INJECTION_DETECTED"
    if not _OLD_HOUSING_RE.search(clean):
        for p in _OLD_OFF_TOPIC:
            if re.search(p, clean, re.IGNORECASE):
                return False, "OFF_TOPIC_QUERY"
    return True, None


# ---------------------------------------------------------------- kiểm chứng câu trả lời cũ
_OLD_PRICE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:triệu|tr)(?![A-Za-zÀ-ỹ])(?:\s*(rưỡi)|(\d{1,2})(?!\d))?", re.IGNORECASE)


def old_verify_answer(answer_text: str, rooms: Sequence[RoomItem], preferences: Optional[UserPreferenceState] = None) -> tuple[bool, list[str]]:
    """(is_grounded, issues) theo grounding.verify_answer_grounding CŨ: chỉ kiểm mã nhatot_/room- và số tiền dạng 'triệu/tr'."""
    if not answer_text.strip():
        return False, ["Câu trả lời rỗng."]
    issues: list[str] = []
    known_ids = {r.id for r in rooms}
    known_prices = [r.priceNum for r in rooms if r.priceNum > 0]
    if preferences:
        known_prices += [p for p in (preferences.max_price, preferences.min_price) if p]
    mentioned = re.findall(r"(?:nhatot_\d+|room-\d+)", answer_text, re.IGNORECASE)
    if not rooms:
        if mentioned:
            issues.append("id khi context rỗng")
        return (not issues), issues
    for mid in mentioned:
        if mid.lower() not in {k.lower() for k in known_ids}:
            issues.append(f"id lạ {mid}")
    priced = [r.priceNum for r in rooms if r.priceNum > 0]
    diffs = [abs(a - b) for i, a in enumerate(priced) for b in priced[i + 1:]]
    refs = known_prices + diffs
    bad = []
    for m in _OLD_PRICE.finditer(answer_text):
        v = float(m.group(1).replace(",", ".")) * 1_000_000
        if m.group(2):
            v += 500_000
        elif m.group(3):
            v += float("0." + m.group(3)) * 1_000_000
        if refs and not any(abs(v - r) <= 150_000 for r in refs):
            bad.append(m.group(0).strip())
    if bad:
        issues.append(f"giá lạ {bad}")
    score = max(0.0, round(1.0 - 0.35 * len(issues), 3))
    return (len(issues) == 0 and score >= 0.8), issues
