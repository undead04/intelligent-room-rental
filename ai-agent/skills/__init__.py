"""Dynamic Skills discovery và registry cho Homigo AI Agent."""

from skills.skills_discovery import (
    SKILL_DIRS,
    SkillMetadata,
    clear_cache,
    discover_housing_skills,
    get_skill,
    match_skill_by_query,
    parse_frontmatter,
    skills_catalog_for_prompt,
)

# Alias for backward compatibility
clear_skills_cache = clear_cache
get_skill_by_slug = get_skill

__all__ = [
    "SKILL_DIRS",
    "SkillMetadata",
    "clear_cache",
    "clear_skills_cache",
    "discover_housing_skills",
    "get_skill",
    "get_skill_by_slug",
    "match_skill_by_query",
    "parse_frontmatter",
    "skills_catalog_for_prompt",
]
