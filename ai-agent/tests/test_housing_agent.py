"""Unit tests cho Homigo AI Agent: Tools, Schemas và Decision Support Service."""

import pytest
from agent import TOOLS, capabilities, system_prompt
from schemas import AgentResponse, DecisionInsight, RoomItem
from service import HousingAgentService


def test_registered_tools_include_housing_tools():
    tool_names = [t.name for t in TOOLS]
    assert "geocode_location" in tool_names
    assert "get_location_hierarchy" in tool_names
    assert "search_rooms" in tool_names
    assert "get_listing_detail" in tool_names
    assert "read_file" in tool_names
    assert "write_file" in tool_names


def test_system_prompt_persona():
    prompt = system_prompt()
    assert "Homigo AI" in prompt
    assert "Hỗ trợ ra quyết định" in prompt
    assert "geocode_location" in prompt
    assert "search_rooms" in prompt


def test_room_item_from_backend_result():
    backend_raw = {
        "listing": {
            "id": "nhatot_123456",
            "title": "Phòng trọ cao cấp Linh Xuân full nội thất",
            "price_vnd": 2800000,
            "area_m2": 25.0,
            "address_raw": "Đường số 11, Phường Linh Xuân, TP Thủ Đức",
            "lat": 10.875,
            "lng": 106.790,
            "main_image": "https://example.com/img.jpg",
            "url": "https://nhatot.com/123456",
        },
        "match_score": 0.865,
        "explain_match": {
            "score": 0.865,
            "top_factors": [
                {"name": "price", "fit": 0.95, "weight": 0.25, "contribution": 0.237},
                {"name": "location", "fit": 0.90, "weight": 0.25, "contribution": 0.225},
                {"name": "safety", "fit": 0.85, "weight": 0.20, "contribution": 0.170},
            ],
            "weak_factors": [],
        },
    }

    room = RoomItem.from_backend_result(backend_raw, rank=1)
    assert room.id == "nhatot_123456"
    assert room.rank == 1
    assert room.matchScore == 0.865
    assert room.price == "2.8 triệu/tháng"
    assert room.priceNum == 2800000
    assert "25.0 m²" in room.tags
    assert "Giá tốt" in room.tags


def test_decision_insight_generation():
    service = HousingAgentService.__new__(HousingAgentService)
    room1 = RoomItem(
        id="room-1",
        rank=1,
        title="Phòng Linh Xuân rộng 25m2",
        price="2.8 triệu/tháng",
        priceNum=2800000,
        address="Linh Xuân",
        matchScore=0.88,
        explain_match={
            "top_factors": [
                {"name": "price", "fit": 0.95},
                {"name": "location", "fit": 0.90},
            ]
        },
    )
    room2 = RoomItem(
        id="room-2",
        rank=2,
        title="Phòng Linh Trung 18m2",
        price="3.2 triệu/tháng",
        priceNum=3200000,
        address="Linh Trung",
        matchScore=0.79,
        explain_match={"top_factors": [{"name": "safety", "fit": 0.88}]},
    )

    insight = service._build_decision_insights([room1, room2])
    assert insight is not None
    assert insight.selected_top_1_id == "room-1"
    assert "Top 1" in insight.top_1_reason
    assert len(insight.trade_offs) == 1
    assert "Top 2" in insight.trade_offs[0].compared_with
    assert len(insight.verification_checklist) >= 3
