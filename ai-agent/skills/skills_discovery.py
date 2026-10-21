"""Dynamic Skill Discovery: quét SKILL.md, lập chỉ mục, cung cấp danh mục cho LLM định tuyến.

Khác bản cũ:
  - `slug` (tên thư mục, lowercase) là KHOÁ DUY NHẤT dùng ở mọi nơi (graph, tool, API) -> hết lệch name/thư mục.
  - Parse frontmatter bằng yaml.safe_load (nhận `triggers: [a, b]`, `description: >` nhiều dòng...).
  - Cache tự làm mới theo mtime (không cần force_reload / importlib.reload).
  - `skills_catalog_for_prompt()` để node NLU cho LLM chọn skill theo `description`.
  - `match_skill_by_query` chỉ còn là FALLBACK (khớp theo ranh giới từ, bỏ dấu, trigger dài thắng).
  - Không sinh trigger tiếng Anh mặc định từ tên thư mục; skill thiếu description/triggers bị cảnh báo.
  - `follow_ups`: gợi ý cuối câu trả lời khai báo ngay trong SKILL.md (formatter không cần tên skill cứng).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from core.paths import PROJECT_ROOT, SKILLS_DIR
from utils.text import contains_phrase, tokens

logger = logging.getLogger(__name__)

# Thứ tự ưu tiên khi trùng slug: thư mục đứng trước thắng
SKILL_DIRS: list[Path] = [SKILLS_DIR, PROJECT_ROOT / "fixtures" / "skills"]


@dataclass
class SkillMetadata:
    slug: str
    name: str
    description: str = ""
    triggers: list[str] = field(default_factory=list)
    follow_ups: list[str] = field(default_factory=list)
    path: str = ""

    def public_dict(self) -> dict:
        """Chỉ các trường an toàn để trả ra API (KHÔNG có path trên máy chủ)."""
        return {"slug": self.slug, "name": self.name, "description": self.description}


def parse_frontmatter(content: str) -> dict:
    content = (content or "").lstrip("\ufeff")
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end == -1:
        return {}
    try:
        data = yaml.safe_load(content[3:end])
    except yaml.YAMLError as e:
        logger.warning("Frontmatter YAML lỗi: %s", e)
        return {}
    return data if isinstance(data, dict) else {}


def _as_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        v = v.split(",")
    return [str(x).strip() for x in v if str(x).strip()]


_lock = threading.Lock()
_cache: dict[str, SkillMetadata] = {}
_cache_sig: Optional[tuple] = None


def _signature() -> tuple:
    files = []
    for d in SKILL_DIRS:
        if d.exists():
            files.extend(sorted(d.glob("*/SKILL.md")))
    return tuple((str(f), f.stat().st_mtime_ns) for f in files)


def clear_cache() -> None:
    global _cache, _cache_sig
    with _lock:
        _cache, _cache_sig = {}, None


def discover_housing_skills(force_reload: bool = False) -> dict[str, SkillMetadata]:
    """{slug: SkillMetadata}. Tự làm mới khi file SKILL.md thay đổi."""
    global _cache, _cache_sig
    sig = _signature()
    with _lock:
        if not force_reload and _cache_sig == sig and _cache_sig is not None:
            return _cache
        found: dict[str, SkillMetadata] = {}
        for d in SKILL_DIRS:
            if not d.exists():
                continue
            for f in sorted(d.glob("*/SKILL.md")):
                slug = f.parent.name.strip().lower()
                if slug in found:
                    logger.warning("Skill '%s' bị trùng, bỏ bản ở %s", slug, f)
                    continue
                try:
                    fm = parse_frontmatter(f.read_text(encoding="utf-8"))
                except OSError as e:
                    logger.warning("Không đọc được %s: %s", f, e)
                    continue
                meta = SkillMetadata(
                    slug=slug,
                    name=str(fm.get("name") or slug),
                    description=" ".join(str(fm.get("description") or "").split()),
                    triggers=_as_list(fm.get("triggers")),
                    follow_ups=_as_list(fm.get("follow_ups")),
                    path=str(f),
                )
                if not meta.description:
                    logger.warning("Skill '%s' thiếu description: LLM sẽ không định tuyến được", slug)
                if not meta.triggers:
                    logger.info("Skill '%s' không có triggers: chỉ được chọn qua LLM, không qua fallback", slug)
                found[slug] = meta
        _cache, _cache_sig = found, sig
        return _cache


def get_skill(slug: Optional[str]) -> Optional[SkillMetadata]:
    return discover_housing_skills().get((slug or "").strip().lower())


def skills_catalog_for_prompt(skills: Optional[dict[str, SkillMetadata]] = None) -> str:
    skills = discover_housing_skills() if skills is None else skills
    return "\n".join(f"- {s.slug}: {s.description or s.name}" for s in skills.values())


def match_skill_by_query(user_text: str) -> Optional[SkillMetadata]:
    """[FALLBACK khi LLM lỗi] Khớp trigger theo ranh giới từ, bỏ dấu; trigger dài nhất thắng.

    Hạn chế đã biết: trigger đơn từ như 'cọc' vẫn khớp trong 'tìm phòng cọc thấp'. Đó là lý do đường chính là LLM.
    """
    if not (user_text or "").strip():
        return None
    best: Optional[SkillMetadata] = None
    best_key = (0, 0)
    for sk in discover_housing_skills().values():
        for t in sk.triggers:
            key = (len(tokens(t)), len(t))
            if key[0] and key > best_key and contains_phrase(user_text, t):
                best, best_key = sk, key
    return best
