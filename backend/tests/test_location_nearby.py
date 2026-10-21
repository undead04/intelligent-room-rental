from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_get_nearby_locations_endpoint():
    res = client.get("/api/v1/locations/nearby", params={"lat": 10.87, "lng": 106.80, "radius_km": 15.0, "limit": 3})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    items = data["data"]
    assert isinstance(items, list)
    if items:
        first = items[0]
        assert "name" in first
        assert "distance_km" in first
        assert "min_price_vnd" in first
        assert "max_price_vnd" in first
        assert "total_listings" in first
        assert first["max_price_vnd"] >= first["min_price_vnd"]

    # Test filtering with mandatory constraint (max_price)
    res_filtered = client.get("/api/v1/locations/nearby", params={"lat": 10.87, "lng": 106.80, "radius_km": 15.0, "max_price": 4000000})
    assert res_filtered.status_code == 200
    filtered_items = res_filtered.json()["data"]
    if filtered_items:
        for it in filtered_items:
            assert it["max_price_vnd"] <= 4000000
            assert it["is_filtered"] is True


def test_get_nearby_locations_by_district():
    res = client.get("/api/v1/locations/nearby", params={"district_id": 123, "radius_km": 15.0, "limit": 3})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
