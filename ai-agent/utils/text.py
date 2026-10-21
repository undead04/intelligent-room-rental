"""Tiện ích xử lý văn bản dùng chung (thay cho 4 bản `_strip_accents` rải rác)."""

from __future__ import annotations

import re
import unicodedata

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


def contains_phrase(text: str | None, phrase: str | None) -> bool:
    """Khớp theo RANH GIỚI TỪ, bỏ dấu cả hai phía.
    contains_phrase('tìm phòng cọc thấp', 'cọc') -> True
    contains_phrase('chere hon', 're hon')         -> False  (không còn khớp chuỗi con)
    """
    t = f" {' '.join(tokens(text))} "
    p = " ".join(tokens(phrase))
    return bool(p) and f" {p} " in t
