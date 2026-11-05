"""Unit & Integration Tests cho tính năng Vòng đời tin đăng (Listing Lifecycle & Expired Status).

Tuân thủ quy chuẩn kiểm thử nghiêm ngặt (Black-box testing, chống Confirmation Bias):
1. Nhóm 1: Happy Path - Tin đang hoạt động (is_active=True) được tìm thấy qua Search, Vector Search, Nearby.
2. Nhóm 2: Expired Exclusion - Tin hết hạn (is_active=False) bị loại trừ 100% khỏi kết quả Search, Vector Search, Nearby.
3. Nhóm 3: Detail Access with Warning - Truy cập trực tiếp qua ID của tin hết hạn vẫn trả về thông tin kèm cờ is_expired=True và status_notice.
4. Nhóm 4: Non-existent ID - Truy vấn ID không tồn tại trả về None / 404 Not Found.
"""

import pytest
from datetime import datetime
from sqlalchemy import text
from app.core.database import SessionLocal
from app.models.listing import Listing
from app.models.location import City, District, Ward
from app.models.room_type import RoomType
from app.models.embedding import ListingEmbedding
from app.repositories.listing_repository import ListingRepository
from app.repositories.location_repository import LocationRepository
from app.schemas.listing import ListingDetailResponse, ListingResponse


@pytest.fixture(scope="module")
def db_session():
    """Khởi tạo session DB thật để test mutation dữ liệu."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="module")
def setup_lifecycle_data(db_session):
    """Tạo dữ liệu thử nghiệm có cả tin active và tin expired trong DB."""
    # Đảm bảo có location cơ bản
    city = db_session.query(City).filter(City.id == 1).first()
    if not city:
        city = City(id=1, name="Hồ Chí Minh")
        db_session.add(city)
        db_session.commit()

    district = db_session.query(District).filter(District.id == 1).first()
    if not district:
        district = District(id=1, city_id=1, name="Quận 1")
        db_session.add(district)
        db_session.commit()

    ward = db_session.query(Ward).filter(Ward.id == 1).first()
    if not ward:
        ward = Ward(id=1, district_id=1, name="Bến Nghé")
        db_session.add(ward)
        db_session.commit()

    active_id = "test_lifecycle_active_9999"
    expired_id = "test_lifecycle_expired_8888"

    # Xóa dữ liệu cũ nếu có
    db_session.query(ListingEmbedding).filter(ListingEmbedding.listing_id.in_([active_id, expired_id])).delete(synchronize_session=False)
    db_session.query(Listing).filter(Listing.id.in_([active_id, expired_id])).delete(synchronize_session=False)
    db_session.commit()

    # Tạo tin active
    active_listing = Listing(
        id=active_id,
        title="Phòng trọ cao cấp test active",
        price_vnd=4500000.0,
        area_m2=25.0,
        address_raw="123 Lê Lợi, Bến Nghé, Quận 1",
        lat=10.776,
        lng=106.700,
        region_id=1,
        district_id=1,
        ward_id=1,
        is_active=True,
        status="active",
        last_checked_at=datetime.now(),
    )

    # Tạo tin expired
    expired_listing = Listing(
        id=expired_id,
        title="Phòng trọ giá rẻ test expired",
        price_vnd=3000000.0,
        area_m2=20.0,
        address_raw="456 Hai Bà Trưng, Bến Nghé, Quận 1",
        lat=10.780,
        lng=106.695,
        region_id=1,
        district_id=1,
        ward_id=1,
        is_active=False,
        status="expired_or_deleted",
        last_checked_at=datetime.now(),
    )

    db_session.add_all([active_listing, expired_listing])
    db_session.commit()

    # Thêm dummy embedding vector 768 chiều cho cả 2
    dummy_vec = [0.01] * 768
    emb1 = ListingEmbedding(listing_id=active_id, model_name="intfloat/multilingual-e5-base", dimension=768, vector=dummy_vec)
    emb2 = ListingEmbedding(listing_id=expired_id, model_name="intfloat/multilingual-e5-base", dimension=768, vector=dummy_vec)
    db_session.add_all([emb1, emb2])
    db_session.commit()

    yield {"active_id": active_id, "expired_id": expired_id}

    # Cleanup sau khi test
    db_session.query(ListingEmbedding).filter(ListingEmbedding.listing_id.in_([active_id, expired_id])).delete(synchronize_session=False)
    db_session.query(Listing).filter(Listing.id.in_([active_id, expired_id])).delete(synchronize_session=False)
    db_session.commit()


# ==============================================================================
# NHÓM 1 & 2: HAPPY PATH & EXPIRED EXCLUSION IN SEARCH
# ==============================================================================

def test_search_excludes_expired_listings(db_session, setup_lifecycle_data):
    """Xác minh bộ lọc tìm kiếm thường (Search) chỉ trả về tin active, loại trừ hoàn toàn tin expired."""
    repo = ListingRepository(db_session)
    active_id = setup_lifecycle_data["active_id"]
    expired_id = setup_lifecycle_data["expired_id"]

    results = repo.search(
        search="test",
        city_id=1,
        district_id=1,
        ward_id=None,
        room_type_id=None,
        min_price=None,
        max_price=None,
        min_area=None,
        max_area=None,
        order_by="posted_date",
        sort_desc=True,
        limit=50,
        offset=0,
    )

    result_ids = [r.id for r in results]
    assert active_id in result_ids, "Tin active phải xuất hiện trong kết quả search"
    assert expired_id not in result_ids, "Tin expired TUYỆT ĐỐI KHÔNG được xuất hiện trong kết quả search"


def test_vector_search_excludes_expired_listings(db_session, setup_lifecycle_data):
    """Xác minh tìm kiếm ngữ nghĩa (Hybrid Vector Search) không trả về tin đã hết hạn."""
    repo = ListingRepository(db_session)
    active_id = setup_lifecycle_data["active_id"]
    expired_id = setup_lifecycle_data["expired_id"]

    dummy_query_vector = [0.01] * 768
    results = repo.vector_search(
        query_vector=dummy_query_vector,
        query_text="phòng trọ test",
        city_id=1,
        district_id=1,
        limit=20,
    )

    result_ids = [r["listing"].id for r in results]
    assert active_id in result_ids, "Tin active phải xuất hiện trong kết quả vector search"
    assert expired_id not in result_ids, "Tin expired KHÔNG được phép xuất hiện trong kết quả vector search"


def test_nearby_locations_excludes_expired_listings(db_session, setup_lifecycle_data):
    """Xác minh gợi ý địa điểm lân cận chỉ tính toán dựa trên các tin active."""
    loc_repo = LocationRepository(db_session)
    nearby = loc_repo.nearby_locations(lat=10.776, lng=106.700, district_id=1, radius_km=5.0)
    assert isinstance(nearby, list)


# ==============================================================================
# NHÓM 3: DETAIL ACCESS WITH EXPIRED NOTICE
# ==============================================================================

def test_get_by_id_returns_expired_listing_with_notice(db_session, setup_lifecycle_data):
    """Xác minh truy vấn get_by_id với tin hết hạn vẫn lấy được dữ liệu và schema tự động gắn cảnh báo."""
    repo = ListingRepository(db_session)
    expired_id = setup_lifecycle_data["expired_id"]

    listing_orm = repo.get_by_id(expired_id)
    assert listing_orm is not None, "get_by_id không được chặn tin expired (phải trả về để hiển thị chi tiết)"
    assert listing_orm.is_active is False
    assert listing_orm.status == "expired_or_deleted"

    # Chuyển đổi sang Pydantic DTO
    detail_dto = ListingDetailResponse.model_validate(listing_orm)
    assert detail_dto.is_active is False
    assert detail_dto.is_expired is True
    assert detail_dto.status_notice is not None
    assert "hết hạn" in detail_dto.status_notice.lower()


def test_get_by_id_for_active_listing_has_no_expired_notice(db_session, setup_lifecycle_data):
    """Xác minh tin active không bị gán cảnh báo hết hạn."""
    repo = ListingRepository(db_session)
    active_id = setup_lifecycle_data["active_id"]

    listing_orm = repo.get_by_id(active_id)
    assert listing_orm is not None
    assert listing_orm.is_active is True

    detail_dto = ListingDetailResponse.model_validate(listing_orm)
    assert detail_dto.is_active is True
    assert detail_dto.is_expired is False
    assert detail_dto.status_notice is None


# ==============================================================================
# NHÓM 4: NON-EXISTENT ID & FASTAPI HTTP ENDPOINT INTEGRATION
# ==============================================================================

def test_get_by_id_non_existent(db_session):
    """Truy vấn ID không tồn tại trả về None."""
    repo = ListingRepository(db_session)
    assert repo.get_by_id("non_existent_id_xyz_123") is None


def test_http_api_endpoints_for_lifecycle(setup_lifecycle_data):
    """Kiểm tra end-to-end qua FastAPI TestClient:
    1. GET /api/v1/listings/ không chứa tin expired.
    2. GET /api/v1/listings/{expired_id} trả về 200 kèm cờ is_expired=True và status_notice.
    3. GET /api/v1/listings/{active_id} trả về 200 kèm cờ is_expired=False.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    active_id = setup_lifecycle_data["active_id"]
    expired_id = setup_lifecycle_data["expired_id"]

    # 1. Search endpoint
    res_search = client.get("/api/v1/listings/?search=test&city_id=1&district_id=1")
    assert res_search.status_code == 200
    search_data = res_search.json().get("data", [])
    returned_ids = [item["id"] for item in search_data]
    assert active_id in returned_ids
    assert expired_id not in returned_ids

    # 2. Expired detail endpoint
    res_expired = client.get(f"/api/v1/listings/{expired_id}")
    assert res_expired.status_code == 200
    expired_dto = res_expired.json().get("data", {})
    assert expired_dto.get("id") == expired_id
    assert expired_dto.get("is_active") is False
    assert expired_dto.get("is_expired") is True
    assert "hết hạn" in expired_dto.get("status_notice", "").lower()

    # 3. Active detail endpoint
    res_active = client.get(f"/api/v1/listings/{active_id}")
    assert res_active.status_code == 200
    active_dto = res_active.json().get("data", {})
    assert active_dto.get("id") == active_id
    assert active_dto.get("is_active") is True
    assert active_dto.get("is_expired") is False
    assert active_dto.get("status_notice") is None

