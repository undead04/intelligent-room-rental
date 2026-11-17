"""Black-box tests cho module Geocoding (Backend /geocode & GeocodeCache).

Bao phủ 4 nhóm theo chuẩn rigorous-testing:
1. Happy Path: 6 vùng hỗ trợ, TrackAsia (ưu tiên VN) -> Nominatim fallback, FastAPI endpoint.
2. Boundary & Edge Cases: Region Bounding-Box rejection, gom cụm 500m (<=500m vs >500m), ngoại biên VN.
3. State Mutation & Cache Isolation: Tách key (query_norm, hint_norm), không nhiễm bẩn copy, không cache lỗi.
4. Persistence & TTL: SQLite bền vững qua restart (`GeocodeCache` instance mới) và hết hạn TTL.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.geocode import GeocodeCandidate, GeocodeResponse
from app.services import geocoder
from app.services.geocoder import (
    GeocodeCache,
    REGION_BBOXES,
    infer_target_region,
    is_in_region_bbox,
    resolve_location,
)


@pytest.fixture
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GeocodeCache:
    """Tạo SQLite cache cô lập trong tmp_path để test không đụng DB thật."""
    db_file = tmp_path / "test_geocode_cache.sqlite"
    cache = GeocodeCache(db_path=db_file, ttl_seconds=3600)
    monkeypatch.setattr(geocoder, "GEOCODE_CACHE_DB_PATH", db_file)
    monkeypatch.setattr(geocoder, "_default_cache", cache)
    monkeypatch.setattr(settings, "TRACKASIA_API_KEY", None)
    return cache


def _mock_http_response(status_code: int, payload: object) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    return resp


# ==============================================================================
# NHÓM 1: HAPPY PATH
# ==============================================================================

@pytest.mark.parametrize(
    ("hint", "expected_region"),
    [
        ("TP.HCM", "TP.HCM"),
        ("Quận 10, Sài Gòn", "TP.HCM"),
        ("Hà Nội", "Hà Nội"),
        ("Cầu Giấy", "Hà Nội"),
        ("Đà Nẵng", "Đà Nẵng"),
        ("Hải Châu", "Đà Nẵng"),
        ("Bình Dương", "Bình Dương"),
        ("Dĩ An", "Bình Dương"),
        ("Đồng Nai", "Đồng Nai"),
        ("Biên Hòa", "Đồng Nai"),
        ("Cần Thơ", "Cần Thơ"),
        ("Ninh Kiều", "Cần Thơ"),
        ("Quảng Ngãi", None),
    ],
)
def test_infer_target_region_six_supported_regions(hint: str, expected_region: str | None) -> None:
    assert infer_target_region(hint) == expected_region


def test_six_regions_bbox_sanity_and_lang_dh_overlap() -> None:
    assert set(REGION_BBOXES.keys()) == {"TP.HCM", "Hà Nội", "Đà Nẵng", "Bình Dương", "Đồng Nai", "Cần Thơ"}
    # Điểm đại diện mỗi vùng đều phải lọt bbox vùng tương ứng
    assert is_in_region_bbox(10.7726, 106.6578, "TP.HCM")
    assert is_in_region_bbox(21.0050, 105.8430, "Hà Nội")
    assert is_in_region_bbox(16.0748, 108.1510, "Đà Nẵng")
    assert is_in_region_bbox(10.9804, 106.6742, "Bình Dương")
    assert is_in_region_bbox(10.9574, 106.8427, "Đồng Nai")
    assert is_in_region_bbox(10.0299, 105.7706, "Cần Thơ")
    # Làng ĐH Thủ Đức - Dĩ An (10.87, 106.80) hợp lệ ở cả TP.HCM và Bình Dương
    assert is_in_region_bbox(10.87, 106.80, "TP.HCM")
    assert is_in_region_bbox(10.87, 106.80, "Bình Dương")


def test_resolve_location_trackasia_priority_and_nominatim_fallback(
    isolated_cache: GeocodeCache, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 1. Nominatim trả 1 điểm hợp lệ trong Đà Nẵng (khi chưa bật TrackAsia)
    nominatim_ok = _mock_http_response(
        200,
        [{"lat": "16.0748", "lon": "108.1510", "name": "ĐH Bách Khoa Đà Nẵng", "display_name": "ĐH Bách Khoa, Liên Chiểu, Đà Nẵng, Việt Nam"}],
    )
    with patch("app.services.geocoder._session.get", return_value=nominatim_ok):
        res = resolve_location("ĐH Bách Khoa", "Đà Nẵng", cache=isolated_cache)
    assert res is not None
    assert not res.ambiguous
    assert res.lat == pytest.approx(16.0748)
    assert res.lon == pytest.approx(108.1510)
    assert res.provider == "Nominatim OSM"

    # 2. Khi bật TrackAsia nhưng TrackAsia lỗi 503 -> fallback sang Nominatim trả điểm ở Cần Thơ
    monkeypatch.setattr(settings, "TRACKASIA_API_KEY", "test-trackasia-key")

    def _trackasia_to_nominatim_fallback(url: str, **kwargs):
        if "maps.track-asia.com" in url:
            return _mock_http_response(503, {})
        assert "nominatim.openstreetmap.org" in url
        return _mock_http_response(
            200,
            [{"lat": "10.0299", "lon": "105.7706", "name": "ĐH Cần Thơ", "display_name": "ĐH Cần Thơ, Ninh Kiều, Cần Thơ, Việt Nam"}],
        )

    with patch("app.services.geocoder._session.get", side_effect=_trackasia_to_nominatim_fallback):
        res_ct = resolve_location("Đại học Cần Thơ", "Cần Thơ", cache=isolated_cache)
    assert res_ct is not None
    assert res_ct.provider == "Nominatim OSM"
    assert res_ct.lat == pytest.approx(10.0299)
    assert res_ct.lon == pytest.approx(105.7706)


def test_trackasia_textsearch_resolves_vn_poi_and_broad_area(
    isolated_cache: GeocodeCache, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TrackAsia Text Search v2 (new_admin=true) giải quyết cả KCN và khu vực dân gian rộng trong 1 request."""
    monkeypatch.setattr(settings, "TRACKASIA_API_KEY", "test-trackasia-key")

    def _trackasia_get(url: str, **kwargs):
        assert "maps.track-asia.com/api/v2/place/textsearch/json" in url
        assert kwargs["params"]["key"] == "test-trackasia-key"
        assert kwargs["params"]["new_admin"] == "true"
        q = kwargs["params"]["query"]
        if "Amata" in q:
            return _mock_http_response(
                200,
                {
                    "results": [
                        {
                            "name": "KCN Amata",
                            "formatted_address": "KCN Amata, Phường Long Bình, Tỉnh Đồng Nai",
                            "geometry": {"location": {"lat": 10.9542, "lng": 106.9019}},
                        }
                    ]
                },
            )
        return _mock_http_response(
            200,
            {
                "results": [
                    {
                        "name": "Làng Đại học",
                        "formatted_address": "Làng Đại học, Phường Đông Hòa, Thành phố Hồ Chí Minh",
                        "geometry": {"location": {"lat": 10.88756, "lng": 106.78085}},
                    }
                ]
            },
        )

    with patch("app.services.geocoder._session.get", side_effect=_trackasia_get):
        res_amata = resolve_location("KCN Amata", "Đồng Nai", cache=isolated_cache)
        res_lang = resolve_location("Làng Đại học Hồ Chí Minh", "TP.HCM", cache=isolated_cache)
    assert res_amata is not None and res_amata.provider == "TrackAsia"
    assert res_amata.lat == pytest.approx(10.9542)
    assert res_lang is not None and res_lang.provider == "TrackAsia"
    assert res_lang.ambiguous is False
    assert res_lang.lat == pytest.approx(10.88756)


def test_controller_endpoint_returns_ambiguous_and_single(isolated_cache: GeocodeCache) -> None:
    client = TestClient(app)
    multi = [
        {"lat": "10.7726", "lon": "106.6578", "name": "ĐH Bách Khoa CS1", "display_name": "ĐH Bách Khoa CS1, Quận 10, TP.HCM, Việt Nam"},
        {"lat": "10.8805", "lon": "106.8063", "name": "ĐH Bách Khoa CS2", "display_name": "ĐH Bách Khoa CS2, Dĩ An / Thủ Đức, TP.HCM, Việt Nam"},
    ]
    with patch("app.services.geocoder._session.get", return_value=_mock_http_response(200, multi)):
        r = client.get("/api/v1/geocode/", params={"q": "ĐH Bách Khoa", "hint": "TP.HCM"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["ambiguous"] is True
    assert len(data["candidates"]) == 2
    assert data["lat"] is None


# ==============================================================================
# NHÓM 2: BOUNDARY & EDGE CASES
# ==============================================================================

def test_region_bbox_rejects_wrong_province_instead_of_mismatching(isolated_cache: GeocodeCache) -> None:
    # Nominatim trả toạ độ Hà Nội dù người dùng tìm kèm hint TP.HCM -> BẮT BUỘC từ chối (404)
    wrong_province = [
        {"lat": "21.0050", "lon": "105.8430", "name": "ĐH Bách Khoa Hà Nội", "display_name": "Hai Bà Trưng, Hà Nội, Việt Nam"},
    ]
    with patch("app.services.geocoder._session.get", return_value=_mock_http_response(200, wrong_province)):
        res = resolve_location("Bách Khoa", "TP.HCM", cache=isolated_cache)
    assert res is None

    # Controller phải trả 404 khi bị lọc hết
    client = TestClient(app)
    with patch("app.services.geocoder._session.get", return_value=_mock_http_response(200, wrong_province)):
        http_res = client.get("/api/v1/geocode/", params={"q": "Bách Khoa", "hint": "TP.HCM"})
    assert http_res.status_code == 404


def test_region_bbox_filters_mixed_top5_and_keeps_matching_region(isolated_cache: GeocodeCache) -> None:
    mixed = [
        {"lat": "21.0050", "lon": "105.8430", "name": "Văn phòng ABC Hà Nội", "display_name": "Văn phòng ABC, Hà Nội, Việt Nam"},
        {"lat": "16.0748", "lon": "108.1510", "name": "Văn phòng ABC Đà Nẵng", "display_name": "Văn phòng ABC, Đà Nẵng, Việt Nam"},
        {"lat": "10.0299", "lon": "105.7706", "name": "Văn phòng ABC Cần Thơ", "display_name": "Văn phòng ABC, Ninh Kiều, Cần Thơ, Việt Nam"},
    ]
    with patch("app.services.geocoder._session.get", return_value=_mock_http_response(200, mixed)):
        res = resolve_location("Văn phòng ABC", "Cần Thơ", cache=isolated_cache)
    assert res is not None
    assert not res.ambiguous
    assert res.lat == pytest.approx(10.0299)
    assert res.lon == pytest.approx(105.7706)


def test_clustering_500m_boundary_merges_close_nodes_and_splits_far_campuses(isolated_cache: GeocodeCache) -> None:
    # Hai điểm cách ~220m (cùng khuôn viên: Cổng A & Cổng B) -> gộp thành 1 điểm (không ambiguous)
    close_nodes = [
        {"lat": "10.8700", "lon": "106.8030", "name": "UIT Cổng chính", "display_name": "UIT, Linh Trung, Thủ Đức, TP.HCM"},
        {"lat": "10.8715", "lon": "106.8042", "name": "UIT Khu E", "display_name": "Khu E UIT, Thủ Đức, TP.HCM"},
    ]
    with patch("app.services.geocoder._session.get", return_value=_mock_http_response(200, close_nodes)):
        res_single = resolve_location("UIT cổng", "TP.HCM", cache=isolated_cache)
    assert res_single is not None
    assert res_single.ambiguous is False
    assert res_single.lat == pytest.approx(10.8700)

    # Hai điểm cách ~700m (> 500m threshold) -> trả ambiguous=True kèm 2 ứng viên
    far_nodes = [
        {"lat": "10.8700", "lon": "106.8030", "name": "Cơ sở test 700m A", "display_name": "Cơ sở test 700m A, Linh Trung, Thủ Đức, TP.HCM"},
        {"lat": "10.8765", "lon": "106.8030", "name": "Cơ sở test 700m B", "display_name": "Cơ sở test 700m B, Linh Xuân, Thủ Đức, TP.HCM"},
    ]
    with patch("app.services.geocoder._session.get", return_value=_mock_http_response(200, far_nodes)):
        res_ambig = resolve_location("Cơ sở test 700m", "TP.HCM", cache=isolated_cache)
    assert res_ambig is not None
    assert res_ambig.ambiguous is True
    assert len(res_ambig.candidates) == 2


def test_rejects_irrelevant_provider_match_for_nonexistent_place(isolated_cache: GeocodeCache) -> None:
    """Địa điểm không tồn tại nhưng API bản đồ trả kết quả rác vì chỉ khớp 'trường'/'đại học' -> BẮT BUỘC trả None/404."""
    nominatim_junk = [
        {"lat": "10.7935", "lon": "106.8591", "name": "Trường Đại học Luật TP.HCM", "display_name": "Trường Đại học Luật TP.HCM, TP Thủ Đức, TP.HCM, Việt Nam"},
        {"lat": "10.7320", "lon": "106.6985", "name": "Trường Đại học Tôn Đức Thắng", "display_name": "Trường Đại học Tôn Đức Thắng, Quận 7, TP.HCM, Việt Nam"},
        {"lat": "10.7921", "lon": "106.7317", "name": "Trường Đại học Giao thông Vận tải TP.HCM", "display_name": "Trường Đại học Giao thông Vận tải TP.HCM, TP Thủ Đức, TP.HCM, Việt Nam"},
    ]

    client = TestClient(app)
    with patch("app.services.geocoder._session.get", return_value=_mock_http_response(200, nominatim_junk)):
        res = resolve_location("trường đại học xyz không có thật", "TP.HCM", cache=isolated_cache)
        http_res = client.get("/api/v1/geocode/", params={"q": "trường đại học xyz không có thật", "hint": "TP.HCM"})

    assert res is None
    assert http_res.status_code == 404


def test_broad_area_merges_internal_nodes_without_ambiguous_list(isolated_cache: GeocodeCache) -> None:
    """Khuôn viên/khu vực rộng lớn (vd Khu đô thị Ecopark / Làng ĐH) có các điểm cách ~1.5km -> gom 1 tâm duy nhất."""
    broad_nodes = [
        {"lat": "20.9610", "lon": "105.9300", "name": "Khu đô thị Ecopark - West Bay", "display_name": "Khu đô thị Ecopark, Văn Giang, Hà Nội, Việt Nam"},
        {"lat": "20.9735", "lon": "105.9320", "name": "Khu đô thị Ecopark - Aqua Bay", "display_name": "Khu đô thị Ecopark, Văn Giang, Hà Nội, Việt Nam"},
    ]
    with patch("app.services.geocoder._session.get", return_value=_mock_http_response(200, broad_nodes)):
        res = resolve_location("Khu đô thị Ecopark", "Hà Nội", cache=isolated_cache)

    assert res is not None
    assert res.ambiguous is False
    assert res.lat == pytest.approx(20.9610)


# ==============================================================================
# NHÓM 3: STATE MUTATION & CACHE KEY ISOLATION
# ==============================================================================

def test_cache_isolates_hint_keys_and_never_caches_failures(isolated_cache: GeocodeCache) -> None:
    # 1. Lần gọi lỗi 503 KHÔNG được ghi cache
    with patch("app.services.geocoder._session.get", return_value=_mock_http_response(503, {})):
        assert resolve_location("ĐH Kinh tế", "Hà Nội", cache=isolated_cache) is None

    # 2. Gọi lại thành công cho (ĐH Kinh tế, Hà Nội) và tách biệt với (ĐH Kinh tế, TP.HCM)
    hn_payload = [{"lat": "21.0365", "lon": "105.7824", "name": "ĐH Kinh tế ĐHQGHN", "display_name": "Cầu Giấy, Hà Nội"}]
    hcm_payload = [{"lat": "10.7854", "lon": "106.6949", "name": "UEH Cơ sở A (ĐH Kinh tế TP.HCM)", "display_name": "Quận 3, TP.HCM"}]

    with patch("app.services.geocoder._session.get", return_value=_mock_http_response(200, hn_payload)):
        r_hn = resolve_location("ĐH Kinh tế", "Hà Nội", cache=isolated_cache)
    with patch("app.services.geocoder._session.get", return_value=_mock_http_response(200, hcm_payload)):
        r_hcm = resolve_location("ĐH Kinh tế", "TP.HCM", cache=isolated_cache)

    assert r_hn is not None and r_hcm is not None
    assert r_hn.lat == pytest.approx(21.0365)
    assert r_hcm.lat == pytest.approx(10.7854)

    # 3. Mutate object trả về không ảnh hưởng bản lưu trong SQLite; query thiếu dấu / khác hoa thường vẫn hit cache HN
    r_hn.lat = -99.0
    with patch("app.services.geocoder._session.get") as should_not_call:
        r_hn_again = resolve_location("  dh kinh te ", "Ha Noi", cache=isolated_cache)
    should_not_call.assert_not_called()
    assert r_hn_again is not None
    assert r_hn_again.lat == pytest.approx(21.0365)


# ==============================================================================
# NHÓM 4: PERSISTENCE & TTL LIFECYCLE
# ==============================================================================

def test_persistent_sqlite_cache_survives_reinstantiation_and_respects_ttl(tmp_path: Path) -> None:
    db_file = tmp_path / "persisted.sqlite"
    writer_cache = GeocodeCache(db_path=db_file, ttl_seconds=100)

    ambig_resp = GeocodeResponse(
        query="Bách Khoa",
        lat=None,
        lon=None,
        formatted_address="",
        provider="Nominatim OSM",
        ambiguous=True,
        candidates=[
            GeocodeCandidate(name="Bách Khoa Q10", lat=10.7726, lon=106.6578, formatted_address="Quận 10, TP.HCM", provider="Nominatim OSM"),
            GeocodeCandidate(name="Bách Khoa Thủ Đức", lat=10.8805, lon=106.8063, formatted_address="Thủ Đức, TP.HCM", provider="Nominatim OSM"),
        ],
    )
    writer_cache.set("Bách Khoa", "TP.HCM", ambig_resp, now=1000.0)

    # Mở lại GeocodeCache hoàn toàn mới (giả lập server restart)
    reader_cache = GeocodeCache(db_path=db_file, ttl_seconds=100)
    before_expiry = reader_cache.get("bach khoa", "tp hcm", now=1050.0)
    assert before_expiry is not None
    assert before_expiry.ambiguous is True
    assert len(before_expiry.candidates) == 2

    # Quá TTL (now = 1100.0 >= 1000.0 + 100) -> trả None và tự dọn bản ghi
    after_expiry = reader_cache.get("bach khoa", "tp hcm", now=1100.0)
    assert after_expiry is None


def test_resolve_location_normalizes_dh_prefix_and_strips_trailing_acronym(
    isolated_cache: GeocodeCache, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Backend /geocode tự chuẩn hóa 'ĐH ...' -> 'Đại học ...' và bỏ acronym thừa ở cuối (không dùng từ điển cứng)."""
    monkeypatch.setattr(geocoder.settings, "TRACKASIA_API_KEY", "")
    seen_queries: list[str] = []

    def fake_nominatim(q: str, target_region=None, limit: int = 5):
        seen_queries.append(q)
        if q.lower() == "đại học kinh tế luật":
            return [
                GeocodeCandidate(
                    name="Trường Đại học Kinh tế - Luật",
                    lat=10.8690,
                    lon=106.7788,
                    formatted_address="669 Quốc lộ 1K, Linh Xuân, Thủ Đức, TP.HCM",
                    provider="Nominatim OSM",
                )
            ]
        return []

    with patch("app.services.geocoder.geocode_nominatim_candidates", side_effect=fake_nominatim):
        r_uel = resolve_location("ĐH Kinh tế Luật UEL", None, cache=isolated_cache)
        assert r_uel is not None and r_uel.lat == 10.8690
        assert "Đại học Kinh tế Luật" in seen_queries
