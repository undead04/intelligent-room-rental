import pytest

from skills import skills_discovery as sd

SKILL_MD = """---
name: Rental Contract Advisor
description: >
  Tư vấn hợp đồng thuê trọ,
  tiền cọc và quyền lợi
triggers: [hợp đồng, đặt cọc, hoàn cọc]
follow_ups:
  - Mẫu biên bản bàn giao phòng
  - Cách kiểm tra công tơ điện nước
---
# Nội dung
Chi tiết...
"""


@pytest.fixture
def skills_dir(tmp_path, monkeypatch):
    d = tmp_path / "skills"
    (d / "Rental-Contract-Advisor").mkdir(parents=True)
    (d / "Rental-Contract-Advisor" / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    (d / "electric").mkdir()
    (d / "electric" / "SKILL.md").write_text("---\nname: electric\ndescription: Điện nước\ntriggers: hợp đồng điện, công tơ điện\n---\nx", encoding="utf-8")
    (d / "broken").mkdir()
    (d / "broken" / "SKILL.md").write_text("---\nname: [unclosed\n---\n", encoding="utf-8")
    (d / "nofm").mkdir()
    (d / "nofm" / "SKILL.md").write_text("# không có frontmatter", encoding="utf-8")
    monkeypatch.setattr(sd, "SKILL_DIRS", [d])
    sd.clear_cache()
    yield d
    sd.clear_cache()


def test_parse_frontmatter_variants():
    fm = sd.parse_frontmatter(SKILL_MD)
    assert fm["triggers"] == ["hợp đồng", "đặt cọc", "hoàn cọc"] and "tiền cọc" in fm["description"]
    assert sd.parse_frontmatter("không có") == {} and sd.parse_frontmatter("---\nname: x") == {}
    assert sd.parse_frontmatter("\ufeff---\nname: x\n---\n") == {"name": "x"}


def test_discover_uses_lowercase_dirname_slug(skills_dir):
    skills = sd.discover_housing_skills()
    assert set(skills) == {"rental-contract-advisor", "electric", "broken", "nofm"}
    s = skills["rental-contract-advisor"]
    assert s.slug == "rental-contract-advisor" and s.name == "Rental Contract Advisor"      # name khác slug vẫn tra được
    assert s.description == "Tư vấn hợp đồng thuê trọ, tiền cọc và quyền lợi"
    assert s.follow_ups == ["Mẫu biên bản bàn giao phòng", "Cách kiểm tra công tơ điện nước"]
    assert skills["electric"].triggers == ["hợp đồng điện", "công tơ điện"]
    assert skills["broken"].name == "broken" and skills["broken"].triggers == []             # frontmatter hỏng không làm sập
    assert sd.get_skill("  Rental-Contract-Advisor ") is s
    assert sd.get_skill("nope") is None and sd.get_skill(None) is None


def test_public_dict_hides_path(skills_dir):
    d = sd.get_skill("electric").public_dict()
    assert set(d) == {"slug", "name", "description"}


def test_cache_refreshes_on_file_change(skills_dir):
    assert sd.get_skill("electric").description == "Điện nước"
    f = skills_dir / "electric" / "SKILL.md"
    f.write_text("---\nname: electric\ndescription: Mô tả mới\n---\nx", encoding="utf-8")
    import os, time
    os.utime(f, ns=(time.time_ns() + 10**9, time.time_ns() + 10**9))
    assert sd.get_skill("electric").description == "Mô tả mới"


def test_duplicate_slug_first_dir_wins(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    for d, desc in ((a, "bản A"), (b, "bản B")):
        (d / "x").mkdir(parents=True)
        (d / "x" / "SKILL.md").write_text(f"---\ndescription: {desc}\n---\n", encoding="utf-8")
    monkeypatch.setattr(sd, "SKILL_DIRS", [a, b])
    sd.clear_cache()
    assert sd.get_skill("x").description == "bản A"
    sd.clear_cache()


def test_catalog_for_prompt(skills_dir):
    c = sd.skills_catalog_for_prompt()
    assert "- rental-contract-advisor: Tư vấn hợp đồng" in c and "- broken: broken" in c


def test_fallback_match(skills_dir):
    m = sd.match_skill_by_query
    assert m("chủ nhà không hoàn cọc thì sao").slug == "rental-contract-advisor"
    assert m("hop dong thue tro can luu y gi").slug == "rental-contract-advisor"           # không dấu
    assert m("hợp đồng điện nước thế nào").slug == "electric"                               # trigger dài hơn thắng
    assert m("tìm phòng gần UIT") is None
    assert m("") is None and m("   ") is None
    assert m("hợpđồng") is None                                                             # không khớp chuỗi con
