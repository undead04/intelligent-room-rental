import pytest

from utils.text import contains_phrase, norm_key, strip_accents, tokens


def test_strip_accents():
    assert strip_accents("Đại Học Công Nghệ") == "dai hoc cong nghe"
    assert strip_accents(None) == ""
    assert strip_accents("đường D2") == "duong d2"


def test_norm_key_collapses_spaces():
    assert norm_key("  Máy   Lạnh ") == "may lanh"


def test_tokens():
    assert tokens("Phòng 25m2, gần UIT!") == ["phong", "25m2", "gan", "uit"]


@pytest.mark.parametrize(
    "text,phrase,expected",
    [
        ("tìm phòng cọc thấp", "cọc", True),
        ("hop dong thue tro", "hợp đồng", True),       # gõ không dấu vẫn khớp
        ("chere hon", "re hon", False),                 # không khớp chuỗi con
        ("phòng rẻ hơn nữa", "rẻ hơn", True),
        ("bảo vệ môi trường", "bảo vệ", True),
        ("xem phòng", "xe", False),                     # 'xe' không khớp trong 'xem'
        ("", "abc", False),
        ("abc", "", False),
    ],
)
def test_contains_phrase(text, phrase, expected):
    assert contains_phrase(text, phrase) is expected
