"""Black-box Integration & Unit Tests cho Mốc 1:
- Bán kính tròn Haversine (chống sai số Bounding Box vuông)
- Đa loại phòng cho phép (Multi-RoomType: room_types)
- Đồng bộ lọc ngữ nghĩa Tiện ích (safe_area, furniture)
- Lọc an toàn trạng thái tin đăng (is_active, status)
- State mutation isolation & Geocoder cache safe copy
- Persistence & Live API Server verification

Tuân thủ nghiêm ngặt quy chuẩn Black-box QA tại .gemini/skills/rigorous-testing/SKILL.md:
Đủ 4 nhóm test cases, không hạ tiêu chuẩn assertion, không sửa source code, cleanup DB 100%.
"""

from datetime import datetime, timezone
import math
from unittest.mock import MagicMock, patch
import numpy as np
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.listing import Listing
from app.models.location import City, District, Ward
from app.models.embedding import ListingEmbedding
from app.repositories.listing_repository import ListingRepository
from app.services.listing_service import ListingService
from app.services.geocoder import resolve_location, _lookup_nominatim_cached
from app.schemas.listing import VectorSearchBody


# ==============================================================================
# HÀM BỔ TRỢ HÌNH HỌC HAVERSINE KIỂM THỬ ĐỘC LẬP (BLACK-BOX RE-IMPLEMENTATION)
# ==============================================================================

def _calculate_haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Tính khoảng cách hình học Haversine mặt cầu chuẩn độc lập với mã nguồn ứng dụng."""
    radius_earth_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.asin(math.sqrt(min(1.0, a)))
    return radius_earth_km * c


# ==============================================================================
# FIXTURES CÔ LẬP DỮ LIỆU TEST TRÊN POSTGRESQL THẬT
# ==============================================================================

@pytest.fixture(scope="module")
def db_session():
    """Khởi tạo session DB thật và đảm bảo đóng session sau khi hoàn tất module test."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="module")
def setup_constraint_data(db_session):
    """Fixture tạo dữ liệu kiểm thử cô lập trên PostgreSQL thật và dọn dẹp sạch 100% trong try/finally."""
    center_lat = 10.8700
    center_lng = 106.8031

    # Toạ độ Tin A: Cách tâm 2.85 km theo trục Bắc (vĩ độ) -> Nằm TRONG bán kính 3.0 km
    lat_offset_a = 2.85 / 110.574
    inside_a_lat = center_lat + lat_offset_a
    inside_a_lng = center_lng

    # Toạ độ Tin B: Góc chéo Bounding Box (lat + 2.6km, lng + 2.6km)
    # Nằm TRONG Bounding Box vuông 3.0km nhưng Haversine thực tế ~3.70 km > 3.0 km -> PHẢI BỊ LOẠI BỎ
    lat_offset_b = 2.6 / 110.574
    lng_offset_b = 2.6 / (111.320 * math.cos(math.radians(center_lat)))
    outside_b_lat = center_lat + lat_offset_b
    outside_b_lng = center_lng + lng_offset_b

    test_ids = [
        "test_vs_constraint_room_1",
        "test_vs_constraint_studio_2",
        "test_vs_constraint_apartment_3",
        "test_vs_constraint_sleepbox_4",
        "test_vs_constraint_amenity_camera",
        "test_vs_constraint_amenity_safety_score",
        "test_vs_constraint_amenity_furniture_code",
        "test_vs_constraint_haversine_inside_a",
        "test_vs_constraint_haversine_outside_b",
        "test_vs_constraint_under_review",
    ]

    # Dọn dẹp dữ liệu cũ nếu sót lại từ lần chạy trước
    db_session.query(ListingEmbedding).filter(ListingEmbedding.listing_id.in_(test_ids)).delete(synchronize_session=False)
    db_session.query(Listing).filter(Listing.id.in_(test_ids)).delete(synchronize_session=False)
    old_wards = db_session.query(Ward).filter(Ward.name == "__TEST_VS_CONSTRAINT_WARD__").all()
    for w in old_wards:
        db_session.delete(w)
    old_dists = db_session.query(District).filter(District.name == "__TEST_VS_CONSTRAINT_DISTRICT__").all()
    for d in old_dists:
        db_session.delete(d)
    db_session.commit()

    # Lấy city có sẵn (ưu tiên TP.HCM)
    city = db_session.query(City).filter(City.name.ilike("%Hồ Chí Minh%")).first()
    if not city:
        city = db_session.query(City).first()
    assert city is not None, "Database phải có ít nhất 1 City để chạy test"

    test_dist = District(city_id=city.id, name="__TEST_VS_CONSTRAINT_DISTRICT__")
    db_session.add(test_dist)
    db_session.flush()

    test_ward = Ward(district_id=test_dist.id, name="__TEST_VS_CONSTRAINT_WARD__")
    db_session.add(test_ward)
    db_session.flush()
    db_session.commit()

    city_id = city.id
    district_id = test_dist.id
    ward_id = test_ward.id

    now_utc = datetime.now(timezone.utc)

    # 1. Tin ROOM thông thường (room_type_id=1)
    l_room_1 = Listing(
        id="test_vs_constraint_room_1",
        title="Phòng trọ test constraint room 1",
        price_vnd=3500000.0,
        area_m2=20.0,
        address_raw=f"10 Đường số 1, {test_ward.name}, {test_dist.name}",
        lat=10.8710,
        lng=106.8035,
        region_id=city_id,
        district_id=district_id,
        ward_id=ward_id,
        room_type_id=1,
        furnishing_code=0,
        concept_scores={"safe_area": 0.0, "camera": 0.0, "furniture": 0.0},
        safety_score=0.5,
        is_active=True,
        status="active",
        last_checked_at=now_utc,
    )

    # 2. Tin STUDIO thông thường (room_type_id=2)
    l_studio_2 = Listing(
        id="test_vs_constraint_studio_2",
        title="Căn hộ studio test constraint 2",
        price_vnd=5000000.0,
        area_m2=28.0,
        address_raw=f"20 Đường số 2, {test_ward.name}, {test_dist.name}",
        lat=10.8720,
        lng=106.8040,
        region_id=city_id,
        district_id=district_id,
        ward_id=ward_id,
        room_type_id=2,
        furnishing_code=0,
        concept_scores={"safe_area": 0.0, "furniture": 0.0},
        safety_score=0.5,
        is_active=True,
        status="active",
        last_checked_at=now_utc,
    )

    # 3. Tin APARTMENT thông thường (room_type_id=3)
    l_apartment_3 = Listing(
        id="test_vs_constraint_apartment_3",
        title="Chung cư căn hộ test constraint 3",
        price_vnd=7500000.0,
        area_m2=45.0,
        address_raw=f"30 Đường số 3, {test_ward.name}, {test_dist.name}",
        lat=10.8715,
        lng=106.8038,
        region_id=city_id,
        district_id=district_id,
        ward_id=ward_id,
        room_type_id=3,
        furnishing_code=0,
        concept_scores={"safe_area": 0.0, "furniture": 0.0},
        safety_score=0.5,
        is_active=True,
        status="active",
        last_checked_at=now_utc,
    )

    # 4. Tin SLEEPBOX (room_type_id=4)
    l_sleepbox_4 = Listing(
        id="test_vs_constraint_sleepbox_4",
        title="Sleepbox ktx test constraint 4",
        price_vnd=1500000.0,
        area_m2=6.0,
        address_raw=f"40 Đường số 4, {test_ward.name}, {test_dist.name}",
        lat=10.8705,
        lng=106.8032,
        region_id=city_id,
        district_id=district_id,
        ward_id=ward_id,
        room_type_id=4,
        furnishing_code=0,
        concept_scores={"safe_area": 0.0, "furniture": 0.0},
        safety_score=0.5,
        is_active=True,
        status="active",
        last_checked_at=now_utc,
    )

    # 5. Tin có camera = 1.0 (nhưng safe_area = 0.0) -> phải khớp tiện ích safe_area
    l_amenity_camera = Listing(
        id="test_vs_constraint_amenity_camera",
        title="Phòng trọ trang bị camera an ninh 24/7",
        price_vnd=3800000.0,
        area_m2=22.0,
        address_raw=f"50 Đường số 5, {test_ward.name}, {test_dist.name}",
        lat=10.8708,
        lng=106.8033,
        region_id=city_id,
        district_id=district_id,
        ward_id=ward_id,
        room_type_id=1,
        furnishing_code=0,
        concept_scores={"safe_area": 0.0, "camera": 1.0, "furniture": 0.0},
        safety_score=0.5,
        is_active=True,
        status="active",
        last_checked_at=now_utc,
    )

    # 6. Tin có safety_score = 0.85 (nhưng safe_area = 0.0) -> phải khớp tiện ích safe_area
    l_amenity_safety_score = Listing(
        id="test_vs_constraint_amenity_safety_score",
        title="Phòng trọ khu an ninh cao safety score",
        price_vnd=3900000.0,
        area_m2=22.0,
        address_raw=f"60 Đường số 6, {test_ward.name}, {test_dist.name}",
        lat=10.8709,
        lng=106.8034,
        region_id=city_id,
        district_id=district_id,
        ward_id=ward_id,
        room_type_id=1,
        furnishing_code=0,
        concept_scores={"safe_area": 0.0, "camera": 0.0, "furniture": 0.0},
        safety_score=0.85,
        is_active=True,
        status="active",
        last_checked_at=now_utc,
    )

    # 7. Tin có furnishing_code = 1 (nhưng furniture score = 0.0) -> phải khớp tiện ích furniture
    l_amenity_furniture_code = Listing(
        id="test_vs_constraint_amenity_furniture_code",
        title="Phòng trọ đầy đủ nội thất full đồ tiện nghi",
        price_vnd=4200000.0,
        area_m2=24.0,
        address_raw=f"70 Đường số 7, {test_ward.name}, {test_dist.name}",
        lat=10.8711,
        lng=106.8036,
        region_id=city_id,
        district_id=district_id,
        ward_id=ward_id,
        room_type_id=1,
        furnishing_code=1,
        concept_scores={"furniture": 0.0},
        safety_score=0.5,
        is_active=True,
        status="active",
        last_checked_at=now_utc,
    )

    # 8. Tin A: Cách tâm 2.85 km (trong đường tròn 3.0 km) -> PHẢI XUẤT HIỆN
    l_inside_a = Listing(
        id="test_vs_constraint_haversine_inside_a",
        title="Phòng trọ nằm cách tâm 2.85 km trong bán kính",
        price_vnd=3600000.0,
        area_m2=20.0,
        address_raw=f"80 Đường số 8, {test_ward.name}, {test_dist.name}",
        lat=inside_a_lat,
        lng=inside_a_lng,
        region_id=city_id,
        district_id=district_id,
        ward_id=ward_id,
        room_type_id=1,
        furnishing_code=0,
        concept_scores={"safe_area": 0.0, "furniture": 0.0},
        safety_score=0.5,
        is_active=True,
        status="active",
        last_checked_at=now_utc,
    )

    # 9. Tin B: Góc chéo BB (Haversine ~3.70 km > 3.0 km) -> TUYỆT ĐỐI BỊ LOẠI BỎ
    l_outside_b = Listing(
        id="test_vs_constraint_haversine_outside_b",
        title="Phòng trọ góc chéo bounding box vượt bán kính 3km",
        price_vnd=3700000.0,
        area_m2=20.0,
        address_raw=f"90 Đường số 9, {test_ward.name}, {test_dist.name}",
        lat=outside_b_lat,
        lng=outside_b_lng,
        region_id=city_id,
        district_id=district_id,
        ward_id=ward_id,
        room_type_id=1,
        furnishing_code=0,
        concept_scores={"safe_area": 0.0, "furniture": 0.0},
        safety_score=0.5,
        is_active=True,
        status="active",
        last_checked_at=now_utc,
    )

    # 10. Tin is_active=True nhưng status="under_review" -> Phải bị loại khỏi search & stats
    # Đặt giá 999999.0 (thấp nhất trong toàn bộ district) để xác minh price_aggregates không bị nhiễm
    l_under_review = Listing(
        id="test_vs_constraint_under_review",
        title="Phòng trọ đang chờ duyệt under review",
        price_vnd=999999.0,
        area_m2=20.0,
        address_raw=f"100 Đường số 10, {test_ward.name}, {test_dist.name}",
        lat=10.8702,
        lng=106.8031,
        region_id=city_id,
        district_id=district_id,
        ward_id=ward_id,
        room_type_id=1,
        furnishing_code=0,
        concept_scores={"safe_area": 0.0, "furniture": 0.0},
        safety_score=0.5,
        is_active=True,
        status="under_review",
        last_checked_at=now_utc,
    )

    all_listings = [
        l_room_1,
        l_studio_2,
        l_apartment_3,
        l_sleepbox_4,
        l_amenity_camera,
        l_amenity_safety_score,
        l_amenity_furniture_code,
        l_inside_a,
        l_outside_b,
        l_under_review,
    ]
    db_session.add_all(all_listings)
    db_session.commit()

    # Thêm Vector Embedding 768 chiều chuẩn cho tất cả các tin test
    dummy_vec = [0.01] * 768
    all_embeddings = [
        ListingEmbedding(
            listing_id=l.id,
            model_name="intfloat/multilingual-e5-base",
            dimension=768,
            vector=dummy_vec,
        )
        for l in all_listings
    ]
    db_session.add_all(all_embeddings)
    db_session.commit()

    yield {
        "center_lat": center_lat,
        "center_lng": center_lng,
        "city_id": city_id,
        "district_id": district_id,
        "ward_id": ward_id,
        "inside_a_lat": inside_a_lat,
        "inside_a_lng": inside_a_lng,
        "outside_b_lat": outside_b_lat,
        "outside_b_lng": outside_b_lng,
        "all_test_ids": test_ids,
    }

    # ==============================================================================
    # TEARDOWN: CLEANUP TOÀN BỘ DỮ LIỆU TEST SAU KHI KẾT THÚC
    # ==============================================================================
    db_session.query(ListingEmbedding).filter(ListingEmbedding.listing_id.in_(test_ids)).delete(synchronize_session=False)
    db_session.query(Listing).filter(Listing.id.in_(test_ids)).delete(synchronize_session=False)
    db_session.delete(test_ward)
    db_session.delete(test_dist)
    db_session.commit()

    # Xác minh DB đã sạch 100% qua session độc lập
    verify_session = SessionLocal()
    try:
        rem_count = verify_session.query(Listing).filter(Listing.id.in_(test_ids)).count()
        assert rem_count == 0, f"Rò rỉ dữ liệu test: còn {rem_count} bản ghi chưa dọn dẹp sạch!"
    finally:
        verify_session.close()


# ==============================================================================
# NHÓM 1: HAPPY PATH (MULTI-ROOMTYPE & SEMANTIC AMENITIES FILTERING)
# ==============================================================================

def test_vector_search_body_room_types_normalization():
    """Nhóm 1: VectorSearchBody chuẩn hóa đúng tập đa loại phòng string/int, loại bỏ trùng lặp và alias."""
    # 1. Nhận mã chuỗi đơn hoặc danh sách
    body0 = VectorSearchBody(query="tìm studio", room_type="studio")
    assert body0.room_type == "STUDIO"

    body1 = VectorSearchBody(query="tìm phòng trọ gần đại học", room_type=["ROOM", "STUDIO"])
    assert body1.room_type == ["ROOM", "STUDIO"]

    # 2. Nhận danh sách ID số
    body2 = VectorSearchBody(query="tìm phòng", room_type=[1, 2])
    assert body2.room_type == [1, 2]

    # 3. Chuẩn hóa alias BOARDING_HOUSE thành ROOM
    body3 = VectorSearchBody(query="tìm phòng", room_type=["BOARDING_HOUSE", "APARTMENT"])
    assert body3.room_type == ["ROOM", "APARTMENT"]

    # 4. Loại bỏ phần tử trùng lặp (Deduplication)
    body4 = VectorSearchBody(query="tìm phòng", room_type=["ROOM", "ROOM", "STUDIO", "STUDIO"])
    assert body4.room_type == ["ROOM", "STUDIO"]


def test_repo_vector_search_multi_room_types_filtering(db_session, setup_constraint_data):
    """Nhóm 1: ListingRepository.vector_search trả về đúng các tin trong room_type cho phép, loại bỏ SLEEPBOX."""
    repo = ListingRepository(db_session)
    center_lat = setup_constraint_data["center_lat"]
    center_lng = setup_constraint_data["center_lng"]
    dummy_vec = [0.01] * 768

    # Tìm kiếm cho phép tập ['ROOM', 'STUDIO']
    results = repo.vector_search(
        query_vector=dummy_vec,
        query_text="tìm phòng",
        lat=center_lat,
        lng=center_lng,
        max_distance_km=1.0,
        room_type=["ROOM", "STUDIO"],
        limit=20,
    )

    found_ids = [r["listing"].id for r in results]

    # Tin ROOM và STUDIO trong bán kính 1.0km phải xuất hiện
    assert "test_vs_constraint_room_1" in found_ids
    assert "test_vs_constraint_studio_2" in found_ids

    # Tin SLEEPBOX (room_type_id=4) và APARTMENT (room_type_id=3) TUYỆT ĐỐI KHÔNG xuất hiện
    assert "test_vs_constraint_sleepbox_4" not in found_ids
    assert "test_vs_constraint_apartment_3" not in found_ids

    # Thử tập khác: chỉ cho phép [3] (APARTMENT)
    apt_results = repo.vector_search(
        query_vector=dummy_vec,
        query_text="tìm chung cư",
        lat=center_lat,
        lng=center_lng,
        max_distance_km=1.0,
        room_type=[3],
        limit=20,
    )
    apt_ids = [r["listing"].id for r in apt_results]
    assert "test_vs_constraint_apartment_3" in apt_ids
    assert "test_vs_constraint_room_1" not in apt_ids
    assert "test_vs_constraint_studio_2" not in apt_ids
    assert "test_vs_constraint_sleepbox_4" not in apt_ids


def test_repo_vector_search_semantic_amenity_safe_area(db_session, setup_constraint_data):
    """Nhóm 1: Lọc ngữ nghĩa amenities=['safe_area'] nhận diện camera=1.0 hoặc safety_score=0.85 dù safe_area=0.0."""
    repo = ListingRepository(db_session)
    center_lat = setup_constraint_data["center_lat"]
    center_lng = setup_constraint_data["center_lng"]
    dummy_vec = [0.01] * 768

    results = repo.vector_search(
        query_vector=dummy_vec,
        query_text="phòng trọ an ninh",
        lat=center_lat,
        lng=center_lng,
        max_distance_km=1.0,
        amenities=["safe_area"],
        limit=20,
    )
    found_ids = [r["listing"].id for r in results]

    # Tin có camera = 1.0 dù safe_area = 0.0 -> PHẢI XUẤT HIỆN
    assert "test_vs_constraint_amenity_camera" in found_ids

    # Tin có safety_score = 0.85 dù safe_area = 0.0 -> PHẢI XUẤT HIỆN
    assert "test_vs_constraint_amenity_safety_score" in found_ids

    # Tin không có an ninh (camera=0, safe_area=0, safety_score=0.5) -> BỊ LOẠI BỎ
    assert "test_vs_constraint_room_1" not in found_ids


def test_repo_vector_search_semantic_amenity_furniture(db_session, setup_constraint_data):
    """Nhóm 1: Lọc ngữ nghĩa amenities=['furniture'] nhận diện furnishing_code=1 dù furniture score=0.0."""
    repo = ListingRepository(db_session)
    center_lat = setup_constraint_data["center_lat"]
    center_lng = setup_constraint_data["center_lng"]
    dummy_vec = [0.01] * 768

    results = repo.vector_search(
        query_vector=dummy_vec,
        query_text="phòng trọ nội thất",
        lat=center_lat,
        lng=center_lng,
        max_distance_km=1.0,
        amenities=["furniture"],
        limit=20,
    )
    found_ids = [r["listing"].id for r in results]

    # Tin có furnishing_code = 1 dù concept_scores furniture = 0.0 -> PHẢI XUẤT HIỆN
    assert "test_vs_constraint_amenity_furniture_code" in found_ids

    # Tin không có nội thất (furnishing_code=0, concept_scores furniture=0.0) -> BỊ LOẠI BỎ
    assert "test_vs_constraint_room_1" not in found_ids


# ==============================================================================
# NHÓM 2: BOUNDARY & EDGE CASES (HAVERSINE VS BOUNDING BOX & VALIDATION)
# ==============================================================================

def test_haversine_vs_bounding_box_diagonal_corner(db_session, setup_constraint_data):
    """Nhóm 2: Tin B nằm TRONG Bounding Box vuông 3.0km nhưng Haversine thực tế ~3.70 km > 3.0 km.
    Kỳ vọng: Tin A xuất hiện, Tin B TUYỆT ĐỐI BỊ LOẠI BỎ ở cả Repository SQL lẫn ListingService!
    """
    repo = ListingRepository(db_session)
    center_lat = setup_constraint_data["center_lat"]
    center_lng = setup_constraint_data["center_lng"]
    inside_a_lat = setup_constraint_data["inside_a_lat"]
    inside_a_lng = setup_constraint_data["inside_a_lng"]
    outside_b_lat = setup_constraint_data["outside_b_lat"]
    outside_b_lng = setup_constraint_data["outside_b_lng"]

    # 1. Kiểm chứng độc lập khoảng cách Haversine toán học
    dist_a = _calculate_haversine_distance_km(center_lat, center_lng, inside_a_lat, inside_a_lng)
    dist_b = _calculate_haversine_distance_km(center_lat, center_lng, outside_b_lat, outside_b_lng)

    assert dist_a < 3.0, f"Tin A phải nằm trong bán kính 3.0km (thực tế: {dist_a:.3f} km)"
    assert dist_b > 3.0, f"Tin B phải vượt quá bán kính 3.0km (thực tế: {dist_b:.3f} km)"

    # Kiểm chứng Tin B nằm trong Bounding Box vuông 3.0km
    lat_delta_max = 3.0 / 110.574
    lng_delta_max = 3.0 / (111.320 * math.cos(math.radians(center_lat)))
    assert abs(outside_b_lat - center_lat) <= lat_delta_max, "Tin B phải nằm trong vĩ độ Bounding Box"
    assert abs(outside_b_lng - center_lng) <= lng_delta_max, "Tin B phải nằm trong kinh độ Bounding Box"

    dummy_vec = [0.01] * 768
    test_dist_id = setup_constraint_data["district_id"]

    # 2. Kiểm thử SQL trực tiếp qua ListingRepository.vector_search (cô lập trong district test)
    repo_results = repo.vector_search(
        query_vector=dummy_vec,
        query_text="tìm phòng trọ",
        district_id=test_dist_id,
        lat=center_lat,
        lng=center_lng,
        max_distance_km=3.0,
        limit=20,
    )
    repo_ids = [r["listing"].id for r in repo_results]

    assert "test_vs_constraint_haversine_inside_a" in repo_ids, "Tin A (2.85 km) PHẢI xuất hiện trong bán kính 3.0 km"
    assert "test_vs_constraint_haversine_outside_b" not in repo_ids, "Tin B (~3.70 km) TUYỆT ĐỐI PHẢI BỊ LOẠI BỎ bởi Haversine SQL!"

    # 3. Kiểm thử tích hợp qua ListingService.vector_search (kiểm chứng kép với Reranker)
    service = ListingService(db=db_session, repository=repo)
    mock_model = MagicMock()
    mock_model.model_name = "intfloat/multilingual-e5-base"
    mock_model.encode_query.return_value = np.array(dummy_vec, dtype=np.float32)

    service_results = service.vector_search(
        query="tìm phòng trọ",
        model_embedding=mock_model,
        district_id=test_dist_id,
        lat=center_lat,
        lng=center_lng,
        max_distance_km=3.0,
        limit=20,
    )
    service_ids = [r.listing.id for r in service_results]

    assert "test_vs_constraint_haversine_inside_a" in service_ids, "Tin A PHẢI xuất hiện qua ListingService"
    assert "test_vs_constraint_haversine_outside_b" not in service_ids, "Tin B TUYỆT ĐỐI BỊ LOẠI BỎ qua ListingService"

    # 4. Khi nới rộng bán kính lên 4.0 km (4.0 > 3.70 km) -> Tin B PHẢI xuất hiện
    service_results_4km = service.vector_search(
        query="tìm phòng trọ",
        model_embedding=mock_model,
        district_id=test_dist_id,
        lat=center_lat,
        lng=center_lng,
        max_distance_km=4.0,
        limit=20,
    )
    service_ids_4km = [r.listing.id for r in service_results_4km]
    assert "test_vs_constraint_haversine_outside_b" in service_ids_4km, "Tin B PHẢI xuất hiện khi nới lỏng bán kính 4.0 km"


def test_vector_search_body_boundary_validation_rejections():
    """Nhóm 2: Kiểm thử validation biên trên VectorSearchBody từ chối các tham số sai lệch."""
    # 1. Từ chối loại phòng không xác định
    with pytest.raises(ValidationError) as exc1:
        VectorSearchBody(query="tìm phòng", room_type=["UNKNOWN_ROOM_TYPE"])
    assert "room_type" in str(exc1.value)

    # 2. Từ chối giá trị boolean lọt vào room_type (vd: [True])
    with pytest.raises(ValidationError) as exc2:
        VectorSearchBody(query="tìm phòng", room_type=[True])
    assert "room_type" in str(exc2.value)

    # 3. Từ chối ID ngoài khoảng 1..5
    with pytest.raises(ValidationError) as exc3:
        VectorSearchBody(query="tìm phòng", room_type=[99])
    assert "room_type" in str(exc3.value)

    # 4. Từ chối min_price > max_price
    with pytest.raises(ValidationError) as exc4:
        VectorSearchBody(query="tìm phòng", min_price=5000000.0, max_price=3000000.0)
    assert "min_price không được lớn hơn max_price" in str(exc4.value)

    # 5. Từ chối min_area > max_area
    with pytest.raises(ValidationError) as exc5:
        VectorSearchBody(query="tìm phòng", min_area=40.0, max_area=20.0)
    assert "min_area không được lớn hơn max_area" in str(exc5.value)

    # 6. Từ chối query rỗng hoặc toàn khoảng trắng
    with pytest.raises(ValidationError) as exc6:
        VectorSearchBody(query="   ")
    assert "query" in str(exc6.value)

    with pytest.raises(ValidationError) as exc7:
        VectorSearchBody(query="")
    assert "query" in str(exc7.value)


# ==============================================================================
# NHÓM 3: STATE MUTATION & ISOLATION (STATUS FILTERING & GEOCODER IMMUTABILITY)
# ==============================================================================

def test_status_under_review_isolated_from_public_views(db_session, setup_constraint_data):
    """Nhóm 3: Tin is_active=True nhưng status='under_review' bị loại khỏi search, vector_search, price_aggregates
    nhưng get_by_id vẫn đọc được nguyên vẹn.
    """
    repo = ListingRepository(db_session)
    dist_id = setup_constraint_data["district_id"]
    center_lat = setup_constraint_data["center_lat"]
    center_lng = setup_constraint_data["center_lng"]
    under_review_id = "test_vs_constraint_under_review"

    # 1. Bị loại khỏi ListingRepository.search()
    search_results = repo.search(
        search="under review",
        city_id=setup_constraint_data["city_id"],
        district_id=dist_id,
        ward_id=None,
        room_type_id=None,
        min_price=None,
        max_price=None,
        min_area=None,
        max_area=None,
        order_by="posted_date",
        sort_desc=True,
        limit=20,
        offset=0,
    )
    search_ids = [l.id for l in search_results]
    assert under_review_id not in search_ids, "Tin status='under_review' không được xuất hiện trong Search công khai"

    # 2. Bị loại khỏi ListingRepository.vector_search()
    dummy_vec = [0.01] * 768
    vs_results = repo.vector_search(
        query_vector=dummy_vec,
        query_text="under review",
        lat=center_lat,
        lng=center_lng,
        max_distance_km=1.0,
        limit=20,
    )
    vs_ids = [r["listing"].id for r in vs_results]
    assert under_review_id not in vs_ids, "Tin status='under_review' không được xuất hiện trong Vector Search"

    # 3. Bị loại khỏi ListingRepository.price_aggregates()
    count_val, avg_val, min_val, max_val = repo.price_aggregates([Listing.district_id == dist_id])
    # Tổng cộng có 10 tin trong district test, trong đó đúng 9 tin active và 1 tin under_review
    assert count_val == 9, f"Kỳ vọng 9 tin active, nhưng nhận {count_val} (tin under_review chưa bị loại bỏ)"
    # Tin under_review có giá 999999.0 (thấp nhất). Nếu bị lọt vào stats, min_val sẽ là 999999.0
    # Tin active có giá rẻ nhất là sleepbox_4 (1500000.0)
    assert min_val == 1500000.0, f"min_price kỳ vọng 1.5tr từ sleepbox active, nhận {min_val}"
    assert min_val > 999999.0, "Tin under_review (999.999đ) không được tham gia thống kê giá"

    # 4. get_by_id() vẫn đọc được nguyên vẹn đối tượng
    direct_listing = repo.get_by_id(under_review_id)
    assert direct_listing is not None, "get_by_id phải đọc được tin đăng bất kể trạng thái"
    assert direct_listing.id == under_review_id
    assert direct_listing.status == "under_review"
    assert direct_listing.is_active is True
    assert direct_listing.price_vnd == 999999.0


def test_geocoder_cache_returns_safe_copy_no_pollution():
    """Nhóm 3: Cache của geocoder.resolve_location trả bản copy an toàn: caller mutate kết quả
    không làm nhiễm bẩn dữ liệu cho lần gọi tiếp theo.
    """
    # Xoá cache trước khi test
    _lookup_nominatim_cached.cache_clear()

    mock_nominatim_data = [
        {
            "lat": "10.7725",
            "lon": "106.6578",
            "display_name": "Đại học Bách Khoa TP.HCM, Quận 10",
        }
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_nominatim_data

    with patch("app.services.geocoder._session.get", return_value=mock_resp) as mock_get:
        test_query = "Đại học Bách Khoa TP.HCM"

        # Lần gọi 1
        res1 = resolve_location(test_query)
        assert res1 is not None
        assert res1.lat == 10.7725
        assert res1.lon == 106.6578
        assert mock_get.call_count == 1

        # Caller cố tình đột biến dữ liệu (Mutate model attributes & model_dump dict)
        res1.lat = 999.0
        res1.lon = -999.0
        dumped_dict = res1.model_dump()
        dumped_dict["lat"] = 888.8

        # Lần gọi 2: Phải trúng cache lru_cache và trả bản copy mới, không bị nhiễm bẩn giá trị 999.0
        res2 = resolve_location(test_query)
        assert res2 is not None
        assert res2.lat == 10.7725, f"Cache bị nhiễm bẩn: mong đợi 10.7725 nhưng nhận {res2.lat}"
        assert res2.lon == 106.6578
        # Xác minh mock_get không bị gọi thêm lần nữa (lru_cache hoạt động)
        assert mock_get.call_count == 1


# ==============================================================================
# NHÓM 4: PERSISTENCE & LIVE FASTAPI SERVER CHECK
# ==============================================================================

def test_persistence_consistency_across_isolated_session(setup_constraint_data):
    """Nhóm 4: Dữ liệu sau commit được nạp lại chính xác từ một SessionLocal() mới hoàn toàn độc lập."""
    test_id = "test_vs_constraint_room_1"
    new_session = SessionLocal()
    try:
        repo = ListingRepository(new_session)
        listing = repo.get_by_id(test_id)
        assert listing is not None, f"Không tìm thấy listing {test_id} trong session mới"
        assert listing.room_type_id == 1
        assert listing.price_vnd == 3500000.0
        assert listing.area_m2 == 20.0
        assert listing.is_active is True
        assert listing.status == "active"
        assert listing.lat == 10.8710
        assert listing.lng == 106.8035
    finally:
        new_session.close()


def test_live_server_vector_search_endpoint_haversine_and_room_types(setup_constraint_data):
    """Nhóm 4: Gửi HTTP POST tới TestClient(app) tại /api/v1/listings/vector-search với
    room_types=['ROOM', 'STUDIO'] và max_distance_km=2.0. Xác minh 200 OK và 100% kết quả
    tuân thủ bán kính Haversine <= 2.0 km và loại phòng thuộc {'ROOM', 'STUDIO'}.
    """
    center_lat = setup_constraint_data["center_lat"]
    center_lng = setup_constraint_data["center_lng"]

    with TestClient(app) as client:
        request_payload = {
            "query": "phòng trọ tiện nghi gần trường đại học",
            "lat": center_lat,
            "lng": center_lng,
            "max_distance_km": 2.0,
            "room_type": ["ROOM", "STUDIO"],
            "limit": 10,
        }

        response = client.post("/api/v1/listings/vector-search", json=request_payload)

        assert response.status_code == 200, f"API trả về status {response.status_code}: {response.text}"
        body = response.json()
        assert body.get("success") is True
        assert body.get("code") == "OK"

        data = body.get("data", [])
        assert isinstance(data, list)
        assert len(data) > 0, "Phải có ít nhất 1 kết quả trả về từ dữ liệu test đã tạo"

        for item in data:
            listing_data = item.get("listing", {})
            room_type_id = listing_data.get("room_type_id")
            room_type_obj = listing_data.get("room_type")
            room_type_code = room_type_obj.get("code") if room_type_obj else None

            # 1. Xác minh 100% loại phòng thuộc ROOM hoặc STUDIO (ID: 1 hoặc 2)
            assert room_type_id in (1, 2) or room_type_code in ("ROOM", "STUDIO"), (
                f"Lọt loại phòng ngoài danh mục cho phép: ID={room_type_id}, code={room_type_code}"
            )

            # 2. Xác minh 100% toạ độ tuân thủ bán kính tròn Haversine <= 2.0 km
            l_lat = listing_data.get("lat")
            l_lng = listing_data.get("lng")
            if l_lat is not None and l_lng is not None:
                calc_dist = _calculate_haversine_distance_km(center_lat, center_lng, float(l_lat), float(l_lng))
                assert calc_dist <= 2.0 + 1e-4, (
                    f"Phòng {listing_data.get('id')} vượt quá bán kính tròn 2.0 km (thực tế: {calc_dist:.3f} km)"
                )

        # 3. Xác minh lỗi validation khi truyền room_type không hợp lệ nhận đúng 422 VALIDATION_ERROR (không bị lỗi 500 serialization)
        invalid_payload = {
            "query": "phòng trọ",
            "room_type": ["INVALID_TYPE"],
        }
        res_invalid = client.post("/api/v1/listings/vector-search", json=invalid_payload)
        assert res_invalid.status_code == 422, f"API phải trả về 422 khi room_type không hợp lệ, thực tế: {res_invalid.status_code}"
        invalid_body = res_invalid.json()
        assert invalid_body.get("code") == "VALIDATION_ERROR"
        assert invalid_body.get("success") is False


def test_vector_search_endpoint_invalid_room_types_returns_422():
    """Kiểm tra gửi HTTP POST /api/v1/listings/vector-search với room_type=['INVALID_TYPE']
    phải nhận đúng status_code == 422 và code == 'VALIDATION_ERROR' (không bị 500 serialization error).
    """
    with TestClient(app) as client:
        invalid_payload = {
            "query": "phòng trọ",
            "room_type": ["INVALID_TYPE"],
        }
        res = client.post("/api/v1/listings/vector-search", json=invalid_payload)
        assert res.status_code == 422, f"API phải trả về 422, thực tế: {res.status_code}"
        body = res.json()
        assert body.get("code") == "VALIDATION_ERROR"
        assert body.get("status") == 422
        assert body.get("success") is False


def test_bedrooms_bathrooms_filters_and_api_endpoints():
    """Kiểm thử end-to-end lọc min_bedrooms / min_bathrooms từ schema, repository tới REST & Vector Search API."""
    from app.schemas.listing import ListingFilterParams

    # 1. Schema validation: min_bedrooms/min_bathrooms >= 1
    with pytest.raises(ValidationError):
        ListingFilterParams(min_bedrooms=0)
    with pytest.raises(ValidationError):
        VectorSearchBody(query="căn hộ", min_bathrooms=0)

    local_session = SessionLocal()
    city = local_session.query(City).first()
    assert city is not None
    unit_vec = [1.0 / math.sqrt(768)] * 768
    test_ids = ["test_bed_1pn", "test_bed_3pn", "test_bed_null"]

    # Pre-clean phòng trường hợp dữ liệu test cũ còn sót
    local_session.query(ListingEmbedding).filter(ListingEmbedding.listing_id.in_(test_ids)).delete(synchronize_session=False)
    local_session.query(Listing).filter(Listing.id.in_(test_ids)).delete(synchronize_session=False)
    local_session.commit()

    dist = District(city_id=city.id, name="__TEST_BEDROOM_DIST__")
    local_session.add(dist)
    local_session.flush()
    ward = Ward(district_id=dist.id, name="__TEST_BEDROOM_WARD__")
    local_session.add(ward)
    local_session.flush()

    try:
        listings = [
            Listing(
                id="test_bed_1pn",
                title="Căn hộ mini 1PN 1WC test",
                price_vnd=4000000.0,
                area_m2=28.0,
                bedrooms=1,
                bathrooms=1,
                region_id=city.id,
                district_id=dist.id,
                ward_id=ward.id,
                room_type_id=3,
                is_active=True,
                status="active",
            ),
            Listing(
                id="test_bed_3pn",
                title="Nhà nguyên căn 3PN 2WC nhiều người test",
                price_vnd=9000000.0,
                area_m2=75.0,
                bedrooms=3,
                bathrooms=2,
                region_id=city.id,
                district_id=dist.id,
                ward_id=ward.id,
                room_type_id=5,
                is_active=True,
                status="active",
            ),
            Listing(
                id="test_bed_null",
                title="Phòng trọ chưa khai báo số phòng test",
                price_vnd=3000000.0,
                area_m2=20.0,
                bedrooms=None,
                bathrooms=None,
                region_id=city.id,
                district_id=dist.id,
                ward_id=ward.id,
                room_type_id=1,
                is_active=True,
                status="active",
            ),
        ]
        for obj in listings:
            local_session.add(obj)
            local_session.add(
                ListingEmbedding(
                    listing_id=obj.id,
                    vector=unit_vec,
                    dimension=768,
                    model_name="intfloat/multilingual-e5-base",
                )
            )
        local_session.commit()

        # 2. Repository filter tests (SQL + Vector Search)
        repo = ListingRepository(local_session)
        found_2pn = repo.search(
            search=None, city_id=city.id, district_id=dist.id, ward_id=ward.id,
            room_type_id=None, min_price=None, max_price=None, min_area=None, max_area=None,
            min_bedrooms=2, order_by="price_vnd", sort_desc=False, limit=10, offset=0,
        )
        assert [x.id for x in found_2pn] == ["test_bed_3pn"]
        assert repo.count(
            search=None, city_id=city.id, district_id=dist.id, ward_id=ward.id,
            room_type_id=None, min_price=None, max_price=None, min_area=None, max_area=None,
            min_bathrooms=2,
        ) == 1

        vec_res = repo.vector_search(
            query_vector=unit_vec, query_text="nhà nguyên căn 3PN",
            city_id=city.id, district_id=dist.id, ward_id=ward.id,
            min_bedrooms=2, min_bathrooms=2, limit=10,
        )
        assert [item["listing"].id for item in vec_res] == ["test_bed_3pn"]

        # 3. REST & Vector Search Live TestClient verification
        with TestClient(app) as client:
            res_list = client.get(f"/api/v1/listings/?district_id={dist.id}&min_bedrooms=2")
            assert res_list.status_code == 200
            items = res_list.json()["data"]
            assert len(items) == 1
            assert items[0]["id"] == "test_bed_3pn"
            assert items[0]["bedrooms"] == 3 and items[0]["bathrooms"] == 2

            res_vec = client.post(
                "/api/v1/listings/vector-search",
                json={"query": "nhà 3 phòng ngủ nhiều người", "district_id": dist.id, "min_bedrooms": 2, "limit": 5},
            )
            assert res_vec.status_code == 200
            vec_items = res_vec.json()["data"]
            assert len(vec_items) == 1
            assert vec_items[0]["listing"]["id"] == "test_bed_3pn"
            assert vec_items[0]["listing"]["bedrooms"] == 3
            assert vec_items[0]["listing"]["bathrooms"] == 2
    finally:
        local_session.rollback()
        local_session.query(ListingEmbedding).filter(ListingEmbedding.listing_id.in_(test_ids)).delete(synchronize_session=False)
        local_session.query(Listing).filter(Listing.id.in_(test_ids)).delete(synchronize_session=False)
        local_session.query(Ward).filter(Ward.id == ward.id).delete(synchronize_session=False)
        local_session.query(District).filter(District.id == dist.id).delete(synchronize_session=False)
        local_session.commit()
        local_session.close()


def test_no_shared_landlord_self_managed_equivalence_isolated():
    """Kiểm tra tương đương ngữ nghĩa: free_hours + fingerprint_lock thỏa mãn no_shared_landlord ở tầng Repository."""
    local_session = SessionLocal()
    unit_vec = (np.ones(768, dtype=float) / math.sqrt(768.0)).tolist()
    test_ids = ["test_nsl_explicit", "test_nsl_self_managed", "test_nsl_missing"]

    city = local_session.query(City).first()
    assert city is not None
    dist = District(city_id=city.id, name="__TEST_NSL_EQUIV_DIST__")
    local_session.add(dist)
    local_session.flush()
    ward = Ward(district_id=dist.id, name="__TEST_NSL_EQUIV_WARD__")
    local_session.add(ward)
    local_session.flush()
    local_session.commit()

    try:
        items = [
            Listing(
                id="test_nsl_explicit",
                title="Phòng không chung chủ trực tiếp",
                price_vnd=3_500_000.0,
                area_m2=25.0,
                region_id=city.id,
                district_id=dist.id,
                ward_id=ward.id,
                room_type_id=1,
                concept_scores={"no_shared_landlord": 1.0, "free_hours": 0.0, "fingerprint_lock": 0.0},
                is_active=True,
                status="active",
            ),
            Listing(
                id="test_nsl_self_managed",
                title="Tòa nhà giờ tự do khóa vân tay",
                price_vnd=3_600_000.0,
                area_m2=26.0,
                region_id=city.id,
                district_id=dist.id,
                ward_id=ward.id,
                room_type_id=1,
                concept_scores={"no_shared_landlord": 0.0, "free_hours": 1.0, "fingerprint_lock": 1.0},
                is_active=True,
                status="active",
            ),
            Listing(
                id="test_nsl_missing",
                title="Phòng chỉ có giờ tự do nhưng không vân tay",
                price_vnd=3_400_000.0,
                area_m2=25.0,
                region_id=city.id,
                district_id=dist.id,
                ward_id=ward.id,
                room_type_id=1,
                concept_scores={"no_shared_landlord": 0.0, "free_hours": 1.0, "fingerprint_lock": 0.0},
                is_active=True,
                status="active",
            ),
        ]
        for obj in items:
            local_session.add(obj)
            local_session.add(
                ListingEmbedding(
                    listing_id=obj.id,
                    vector=unit_vec,
                    dimension=768,
                    model_name="intfloat/multilingual-e5-base",
                )
            )
        local_session.commit()

        repo = ListingRepository(local_session)
        res = repo.vector_search(
            query_vector=unit_vec,
            query_text="phòng không chung chủ",
            city_id=city.id,
            district_id=dist.id,
            ward_id=ward.id,
            amenities=["no_shared_landlord"],
            limit=10,
        )
        matched_ids = {row["listing"].id for row in res}
        assert matched_ids == {"test_nsl_explicit", "test_nsl_self_managed"}
    finally:
        local_session.rollback()
        local_session.query(ListingEmbedding).filter(ListingEmbedding.listing_id.in_(test_ids)).delete(synchronize_session=False)
        local_session.query(Listing).filter(Listing.id.in_(test_ids)).delete(synchronize_session=False)
        local_session.query(Ward).filter(Ward.id == ward.id).delete(synchronize_session=False)
        local_session.query(District).filter(District.id == dist.id).delete(synchronize_session=False)
        local_session.commit()
        local_session.close()

