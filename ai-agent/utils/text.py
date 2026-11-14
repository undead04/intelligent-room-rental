"""Tiện ích xử lý văn bản dùng chung (thay cho 4 bản `_strip_accents` rải rác)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def strip_accents(text: str | None) -> str:
    """Bỏ dấu tiếng Việt + hạ chữ thường. 'Đại Học' -> 'dai hoc'."""
    text = unicodedata.normalize("NFC", text or "").lower().replace("đ", "d")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def norm_key(text: str | None) -> str:
    """Khoá so khớp: bỏ dấu, gộp khoảng trắng. Dùng cho alias/lookup."""
    return " ".join(strip_accents(text).split())


def tokens(text: str | None) -> list[str]:
    """Tách từ không dấu (chữ+số). 'Phòng 25m2, gần UIT!' -> ['phong','25m2','gan','uit']."""
    return _NON_ALNUM.sub(" ", strip_accents(text)).split()


def extract_message_text(msg: Any) -> str:
    """Trích xuất chuỗi văn bản thuần từ đối tượng LangChain Message hoặc string."""
    content = getattr(msg, "content", msg)
    if isinstance(content, str):
        return content
    return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in (content or []))


TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "thú cưng": ("thú cưng", "thu cung", "chó", "mèo", "cho meo", "nuôi chó", "nuoi cho", "nuôi mèo", "nuoi meo", "nuôi pet", "nuoi pet", "pet"),
    "tiền cọc": ("tiền cọc", "tien coc", "đặt cọc", "dat coc", "cọc", "coc"),
    "an ninh": ("an ninh", "an toàn", "an toan", "camera", "bảo vệ", "bao ve", "trộm", "trom"),
    "giờ giấc": ("giờ giấc", "gio giac", "tự do", "tu do", "24/24", "24/7", "khóa vân tay", "khoa van tay", "cổng riêng", "cong rieng", "cửa cuốn", "cua cuon", "về muộn", "ve muon"),
    "điện nước": ("điện", "tien dien", "so dien", "gia dien", "dien nuoc", "nước", "tien nuoc", "khoi nuoc", "kwh"),
    "gửi xe": ("bãi xe", "bai xe", "nhà xe", "nha xe", "gửi xe", "gui xe", "để xe", "de xe", "xe máy", "xe may"),
    "ở ghép": ("ở ghép", "o ghep", "ở chung", "o chung", "2 người", "2 nguoi", "hai người", "hai nguoi", "2 bạn", "2 ban", "o 2", "ở 2"),
}
