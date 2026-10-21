"""Tools đăng ký và Phân vùng công cụ cho AI Agent của Smart Housing Decision Support System."""

from skills.skills_discovery import (
    SkillMetadata,
    discover_housing_skills,
    skills_catalog_for_prompt,
)
from tools.housing_tools import (
    consult_housing_skill,
    geocode_location,
    get_listing_detail,
    get_location_hierarchy,
    get_market_price_stats,
    list_housing_skills,
    search_rooms,
)
from tools.http import get_client, set_client, unwrap_response
from tools.location_service import (
    AdminLookup,
    Geocode,
    Kind,
    LocationResolution,
    resolve_location,
)
from tools.registry import (
    ADVISORY_TOOLS,
    ALL_TOOLS,
    DETAIL_TOOLS,
    RETRIEVAL_TOOLS,
    TOOL_SCOPES,
    get_tools_for_scope,
)

get_http_client = get_client

__all__ = [
    # http
    "get_client",
    "get_http_client",
    "set_client",
    "unwrap_response",
    # housing tools
    "geocode_location",
    "get_location_hierarchy",
    "search_rooms",
    "get_listing_detail",
    "get_market_price_stats",
    "list_housing_skills",
    "consult_housing_skill",
    # location service
    "resolve_location",
    "LocationResolution",
    "Kind",
    "AdminLookup",
    "Geocode",
    # scopes
    "RETRIEVAL_TOOLS",
    "DETAIL_TOOLS",
    "ADVISORY_TOOLS",
    "ALL_TOOLS",
    "TOOL_SCOPES",
    "get_tools_for_scope",
    # skills discovery
    "SkillMetadata",
    "discover_housing_skills",
    "skills_catalog_for_prompt",
]
