"""Black-box Unit & Integration Tests cho Geo-filtering và HTTP Retry Resilience (MỐC 2).

Kiểm thử độc lập theo 4 nhóm test cases:
- Nhóm 1 (Happy Path): HTTP Request gọi thành công, Geo-filter áp đặt max_distance_km=5.0.
- Nhóm 2 (HTTP Retry): Server lỗi 503 hoặc ConnectError -> tự động retry thành công sau lần thử tiếp theo.
- Nhóm 3 (Edge Cases): admin_lookup chuỗi rỗng không gửi search='', fetch_nearby_locations không vị trí trả về [].
- Nhóm 4 (Integration): retrieval_node tích hợp search_args kẹp max_distance_km và district_id chặt chẽ.
"""

from __future__ import annotations

import httpx
import pytest

from domain.schemas import UserPreferenceState
from graph.deps import default_deps
from graph.nodes.retrieval import make_retrieval_node
from tools.housing_tools import admin_lookup, fetch_nearby_locations
from tools.http import request, set_client


# =============================================================================
# NHÓM 1: HAPPY PATH - GEO FILTER TRONG RETRIEVAL NODE
# =============================================================================


def test_retrieval_node_enforces_5km_radius_when_has_point():
    """Khi có toạ độ mốc, retrieval_node luôn kẹp max_distance_km = 5.0."""
    pref = UserPreferenceState(location_text="ĐHQG Thủ Đức", location_kind="place", lat=10.87, lng=106.80)
    assert pref.has_point is True

    captured_args = {}

    def mock_search_rooms(args):
        captured_args.update(args)
        return {"ok": True, "data": []}

    deps = default_deps()
    deps.search_rooms = mock_search_rooms
    node = make_retrieval_node(deps)

    state = {
        "session_id": "test_s1",
        "preferences": pref,
        "user_message": "tìm phòng gần ĐHQG",
    }
    node(state)

    assert captured_args.get("lat") == 10.87
    assert captured_args.get("lng") == 106.80
    assert captured_args.get("max_distance_km") == 5.0


def test_retrieval_node_passes_district_id_when_admin_location():
    """Khi tìm theo quận hành chính (không có toạ độ), truyền district_id vào search_args."""
    pref = UserPreferenceState(location_text="Quận 1", location_kind="admin", district_id=760)
    assert pref.has_point is False

    captured_args = {}

    def mock_search_rooms(args):
        captured_args.update(args)
        return {"ok": True, "data": []}

    deps = default_deps()
    deps.search_rooms = mock_search_rooms
    node = make_retrieval_node(deps)

    state = {
        "session_id": "test_s2",
        "preferences": pref,
        "user_message": "tìm studio Quận 1",
    }
    node(state)

    assert captured_args.get("district_id") == 760
    assert captured_args.get("max_distance_km") is None


# =============================================================================
# NHÓM 2: HTTP RETRY RESILIENCE (TỰ ĐỘNG THỬ LẠI KHI 503 HOẶC LỖI KẾT NỐI)
# =============================================================================


def test_http_request_retries_on_503_and_succeeds():
    """Khi server trả về 503 ở lần 1, retry lần 2 thành công 200 -> trả kết quả ok."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(200, json={"success": True, "data": [{"id": "room_1"}]})

    mock_transport = httpx.MockTransport(handler)
    mock_client = httpx.Client(base_url="http://testserver/api/v1", transport=mock_transport)

    set_client(mock_client)
    try:
        res = request("GET", "/listings/test")
        assert res.get("ok") is True
        assert res.get("data") == [{"id": "room_1"}]
        assert call_count == 2
    finally:
        set_client(None)


def test_http_request_retries_on_network_connect_error():
    """Khi gặp lỗi kết nối mạng (ConnectError) ở lần 1, retry lần 2 thành công -> trả kết quả ok."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("Connection refused by target", request=request)
        return httpx.Response(200, json={"success": True, "data": [{"id": "room_2"}]})

    mock_transport = httpx.MockTransport(handler)
    mock_client = httpx.Client(base_url="http://testserver/api/v1", transport=mock_transport)

    set_client(mock_client)
    try:
        res = request("GET", "/listings/test")
        assert res.get("ok") is True
        assert res.get("data") == [{"id": "room_2"}]
        assert call_count == 2
    finally:
        set_client(None)


# =============================================================================
# NHÓM 3: EDGE CASES - THAM SỐ TOOL VÀ TRÁNH 422
# =============================================================================


def test_admin_lookup_empty_name_omits_search_param():
    """admin_lookup với tên rỗng không gửi search='' tránh lỗi 422 Unprocessable Content."""
    captured_request = None

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = req
        return httpx.Response(200, json={"success": True, "data": []})

    mock_transport = httpx.MockTransport(handler)
    mock_client = httpx.Client(base_url="http://testserver/api/v1", transport=mock_transport)

    set_client(mock_client)
    try:
        admin_lookup("city", "")
        assert captured_request is not None
        # URL params không được chứa 'search='
        assert "search=" not in str(captured_request.url)
    finally:
        set_client(None)


def test_fetch_nearby_locations_without_any_coords_or_admin_returns_empty():
    """fetch_nearby_locations khi không có bất kỳ mốc toạ độ hay quận nào thì trả về [] ngay lập tức."""
    res = fetch_nearby_locations()
    assert res == []
