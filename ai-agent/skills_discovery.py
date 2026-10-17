"""Dynamic Skill Discovery cho Homigo AI Agent.
Tự động quét, phát hiện và lập chỉ mục các Kỹ năng (Skills) từ thư mục workspace/skills và fixtures/skills.
Cho phép mở rộng năng lực nghiệp vụ cho Agent chỉ bằng cách thêm file SKILL.md mà không cần sửa code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SkillMetadata:
    """Thông tin cấu hình được bóc tách từ SKILL.md."""
    name: str
    description: str = ""
    triggers: List[str] = field(default_factory=list)
    path: str = ""


# Bộ nhớ đệm danh mục kỹ năng để tránh đọc đĩa liên tục
_SKILL_CACHE: Optional[Dict[str, SkillMetadata]] = None


def _parse_yaml_frontmatter(content: str) -> dict:
    """Bóc tách YAML frontmatter nằm giữa hai dấu '---'."""
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    frontmatter_lines = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        frontmatter_lines.append(line)

    result = {}
    current_list_key = None

    for line in frontmatter_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- ") and current_list_key:
            item = stripped[2:].strip().strip('"').strip("'")
            result[current_list_key].append(item)
            continue

        if ":" in line:
            parts = line.split(":", 1)
            key = parts[0].strip()
            val = parts[1].strip().strip('"').strip("'")

            if not val:
                current_list_key = key
                result[key] = []
            else:
                current_list_key = None
                result[key] = val

    return result


def discover_housing_skills(force_reload: bool = False) -> Dict[str, SkillMetadata]:
    """Tự động quét và phát hiện toàn bộ các Kỹ năng chuyên sâu trong hệ thống Homigo.

    Quét theo thứ tự ưu tiên:
    1. ai-agent/workspace/skills/*/SKILL.md
    2. ai-agent/fixtures/skills/*/SKILL.md

    Returns:
        Dictionary ánh xạ {skill_name: SkillMetadata}.
    """
    global _SKILL_CACHE
    if _SKILL_CACHE is not None and not force_reload:
        return _SKILL_CACHE

    base_dirs = [
        Path(__file__).resolve().parent / "skills",
        Path(__file__).resolve().parent / "workspace" / "skills",
        Path(__file__).resolve().parent / "fixtures" / "skills",
    ]

    discovered: Dict[str, SkillMetadata] = {}

    for b in base_dirs:
        if not b.exists():
            continue
        for skill_file in sorted(b.glob("*/SKILL.md")):
            skill_name = skill_file.parent.name
            if skill_name in discovered:
                continue

            try:
                content = skill_file.read_text(encoding="utf-8")
                metadata_dict = _parse_yaml_frontmatter(content)

                name = metadata_dict.get("name") or skill_name
                desc = metadata_dict.get("description", "")
                raw_triggers = metadata_dict.get("triggers", [])

                if isinstance(raw_triggers, str):
                    triggers = [t.strip().lower() for t in raw_triggers.split(",") if t.strip()]
                elif isinstance(raw_triggers, list):
                    triggers = [str(t).strip().lower() for t in raw_triggers if str(t).strip()]
                else:
                    triggers = []

                # Nếu chưa khai báo triggers, tự tạo từ khóa mặc định từ tên skill
                if not triggers:
                    triggers = [skill_name.lower().replace("-", " ")]

                discovered[skill_name] = SkillMetadata(
                    name=name,
                    description=desc,
                    triggers=triggers,
                    path=str(skill_file),
                )
            except Exception as e:
                logger.warning(f"Lỗi khi đọc metadata kỹ năng từ {skill_file}: {e}")

    _SKILL_CACHE = discovered
    return discovered


def match_skill_by_query(user_text: str) -> Optional[SkillMetadata]:
    """So khớp câu hỏi của người dùng với danh sách Kỹ năng khả dụng dựa trên triggers.

    Args:
        user_text: Câu hỏi hoặc tin nhắn của người dùng.

    Returns:
        SkillMetadata nếu tìm thấy kỹ năng phù hợp, ngược lại trả về None.
    """
    if not user_text:
        return None

    query_lower = user_text.lower()
    skills = discover_housing_skills()

    for skill in skills.values():
        for trigger in skill.triggers:
            if trigger in query_lower:
                return skill

    return None
