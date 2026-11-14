import pytest

from utils.text import extract_message_text, norm_key, strip_accents, tokens


def test_strip_accents():
    assert strip_accents("Đại Học Công Nghệ") == "dai hoc cong nghe"
    assert strip_accents(None) == ""
    assert strip_accents("đường D2") == "duong d2"


def test_norm_key_collapses_spaces():
    assert norm_key("  Máy   Lạnh ") == "may lanh"


def test_tokens():
    assert tokens("Phòng 25m2, gần UIT!") == ["phong", "25m2", "gan", "uit"]


def test_extract_message_text():
    from types import SimpleNamespace

    assert extract_message_text("hello") == "hello"
    assert extract_message_text(SimpleNamespace(content="hi")) == "hi"
    assert extract_message_text(SimpleNamespace(content=[{"text": "a"}, "b"])) == "ab"
