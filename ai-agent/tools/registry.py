"""Quản lý và phân vùng công cụ (Tool Partitioning / Scoping) cho Homigo AI Agent.
Ngăn chặn Context Bloat và Tool Hallucination bằng cách giới hạn phạm vi công cụ cho từng Node trong LangGraph.
"""

from __future__ import annotations

from typing import Dict, List
from langchain_core.tools import BaseTool

from tools.housing_tools import (
    consult_housing_skill,
    geocode_location,
    get_listing_detail,
    get_location_hierarchy,
    list_housing_skills,
    search_rooms,
)

# 1. Phân vùng công cụ tìm kiếm và định vị (Dành cho retrieval_node)
RETRIEVAL_TOOLS: List[BaseTool] = [
    geocode_location,
    get_location_hierarchy,
    search_rooms,
]

# 2. Phân vùng công cụ phân tích sâu thông tin phòng (Dành cho decision_node)
DETAIL_TOOLS: List[BaseTool] = [
    get_listing_detail,
]

# 3. Phân vùng công cụ tham vấn kỹ năng & cẩm nang chuyên sâu (Dành cho advisory_node)
ADVISORY_TOOLS: List[BaseTool] = [
    list_housing_skills,
    consult_housing_skill,
]

# Tập hợp toàn bộ công cụ của Homigo Housing Agent
ALL_TOOLS: List[BaseTool] = RETRIEVAL_TOOLS + DETAIL_TOOLS + ADVISORY_TOOLS

TOOL_SCOPES: Dict[str, List[BaseTool]] = {
    "retrieval": RETRIEVAL_TOOLS,
    "detail": DETAIL_TOOLS,
    "advisory": ADVISORY_TOOLS,
    "all": ALL_TOOLS,
}


def get_tools_for_scope(scope: str) -> List[BaseTool]:
    """Lấy danh sách công cụ được cấp quyền cho một phân vùng (Scope) cụ thể."""
    return TOOL_SCOPES.get(scope.lower(), [])
