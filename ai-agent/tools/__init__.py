"""Tools đăng ký và Phân vùng công cụ cho AI Agent của Smart Housing Decision Support System."""

from tools.files import read_file, write_file
from tools.housing_tools import (
    consult_housing_skill,
    geocode_location,
    get_listing_detail,
    get_location_hierarchy,
    list_housing_skills,
    search_rooms,
)
from tools.registry import (
    ADVISORY_TOOLS,
    ALL_TOOLS,
    DETAIL_TOOLS,
    RETRIEVAL_TOOLS,
    SYSTEM_TOOLS,
    TOOL_SCOPES,
    get_tools_for_scope,
)

__all__ = [
    "read_file",
    "write_file",
    "geocode_location",
    "get_location_hierarchy",
    "search_rooms",
    "get_listing_detail",
    "list_housing_skills",
    "consult_housing_skill",
    "RETRIEVAL_TOOLS",
    "DETAIL_TOOLS",
    "ADVISORY_TOOLS",
    "SYSTEM_TOOLS",
    "ALL_TOOLS",
    "TOOL_SCOPES",
    "get_tools_for_scope",
]
