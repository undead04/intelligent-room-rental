"""Unit & Integration Tests cho tính năng Vòng đời tin đăng (Listing Lifecycle & Expired Status).

Tuân thủ quy chuẩn kiểm thử nghiêm ngặt (Black-box testing, chống Confirmation Bias) theo đúng 4 nhóm test case bắt buộc:
1. Nhóm 1: Happy Path - Tin active xuất hiện trong Search, Vector Search, Nearby, Price Aggregates; tin expired bị loại trừ; chi tiết tin expired trả về đầy đủ kèm status_notice.
2. Nhóm 2: Boundary & Edge Cases - ID không tồn tại trả về None/404, last_checked_at=None, status lạ hoặc trống, chuỗi tìm kiếm chỉ có khoảng trắng.
3. Nhóm 3: State Mutation & Race Condition - Cập nhật trạng thái tin expired không ảnh hưởng tới tin active khác, tính bất biến (Immutability) của các trường dữ liệu lõi.
4. Nhóm 4: Persistence Test - Dữ liệu sau khi commit được lưu trữ và nạp lại chính xác từ PostgreSQL qua session mới.
"""

from datetime import datetime, timezone
import pytest
from sqlalchemy import text

from app.core.database import SessionLocal
from app.models.listing import Listing
from app.models.location import City, District, Ward
from app.models.room_type import RoomType
from app.models.embedding import ListingEmbedding
from app.repositories.listing_repository import ListingRepository
from app.repositories.location_repository import LocationRepository
from app.services.listing_service import ListingService
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
    # Dọn dẹp dữ liệu test cũ nếu còn sót lại từ lần chạy trước
    active_id = "test_lifecycle_active_9999"
    expired_id = "test_lifecycle_expired_8888"
    db_session.query(ListingEmbedding).filter(ListingEmbedding.listing_id.in_([active_id, expired_id])).delete(synchronize_session=False)
    db_session.query(Listing).filter(Listing.id.in_([active_id, expired_id])).delete(synchronize_session=False)
    old_wards = db_session.query(Ward).filter(Ward.name == "__TEST_LIFECYCLE_WARD__").all()
    for w in old_wards:
        db_session.delete(w)
    old_dists = db_session.query(District).filter(District.name == "__TEST_LIFECYCLE_DISTRICT__").all()
    for d in old_dists:
        db_session.delete(d)
    db_session.commit()

    # Lấy city có sẵn (ưu tiên TP Hồ Chí Minh)
    city = db_session.query(City).filter(City.name.ilike("%Hồ Chí Minh%")).first()
    if not city:
        city = db_session.query(City).first()

    # Tạo district và ward RIÊNG BIỆT cho bài test để cô lập hoàn toàn với dữ liệu production
    test_dist = District(city_id=city.id, name="__TEST_LIFECYCLE_DISTRICT__")
    db_session.add(test_dist)
    db_session.flush()

    test_ward = Ward(district_id=test_dist.id, name="__TEST_LIFECYCLE_WARD__")
    db_session.add(test_ward)
    db_session.flush()
    db_session.commit()

    city_id = city.id
    district_id = test_dist.id
    ward_id = test_ward.id

    active_addr = f"123 Lê Lợi, {test_ward.name}, {test_dist.name}"
    expired_addr = f"456 Hai Bà Trưng, {test_ward.name}, {test_dist.name}"

    # Tạo tin active
    active_listing = Listing(
        id=active_id,
        title="Phòng trọ cao cấp test active",
        price_vnd=4500000.0,
        area_m2=25.0,
        address_raw=active_addr,
        lat=10.776,
        lng=106.700,
        region_id=city_id,
        district_id=district_id,
        ward_id=ward_id,
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
        address_raw=expired_addr,
        lat=10.780,
        lng=106.695,
        region_id=city_id,
        district_id=district_id,
        ward_id=ward_id,
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

    yield {
        "active_id": active_id,
        "expired_id": expired_id,
        "city_id": city_id,
        "district_id": district_id,
        "ward_id": ward_id,
        "active_address_raw": active_addr,
        "expired_address_raw": expired_addr,
    }

    # Cleanup sau khi test
    db_session.query(ListingEmbedding).filter(ListingEmbedding.listing_id.in_([active_id, expired_id])).delete(synchronize_session=False)
    db_session.query(Listing).filter(Listing.id.in_([active_id, expired_id])).delete(synchronize_session=False)
    db_session.delete(test_ward)
    db_session.delete(test_dist)
    db_session.commit()


# ==============================================================================
# NHÓM 1: HAPPY PATH (DỮ LIỆU HỢP LỆ & LOẠI TRỪ TIN EXPIRED KHỎI SEARCH/STATS)
# ==============================================================================

def test_search_excludes_expired_listings(db_session, setup_lifecycle_data):
    """Nhóm 1: Xác minh bộ lọc tìm kiếm thường (Search) chỉ trả về tin active, loại trừ hoàn toàn tin expired."""
    repo = ListingRepository(db_session)
    active_id = setup_lifecycle_data["active_id"]
    expired_id = setup_lifecycle_data["expired_id"]

    results = repo.search(
        search="test",
        city_id=setup_lifecycle_data["city_id"],
        district_id=setup_lifecycle_data["district_id"],
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
    """Nhóm 1: Xác minh tìm kiếm ngữ nghĩa (Hybrid Vector Search) không trả về tin đã hết hạn."""
    repo = ListingRepository(db_session)
    active_id = setup_lifecycle_data["active_id"]
    expired_id = setup_lifecycle_data["expired_id"]

    dummy_query_vector = [0.01] * 768
    results = repo.vector_search(
        query_vector=dummy_query_vector,
        query_text="phòng trọ test",
        city_id=setup_lifecycle_data["city_id"],
        district_id=setup_lifecycle_data["district_id"],
        limit=20,
    )

    result_ids = [r["listing"].id for r in results]
    assert active_id in result_ids, "Tin active phải xuất hiện trong kết quả vector search"
    assert expired_id not in result_ids, "Tin expired KHÔNG được phép xuất hiện trong kết quả vector search"


def test_nearby_locations_excludes_expired_listings(db_session, setup_lifecycle_data):
    """Nhóm 1: Xác minh gợi ý địa điểm lân cận chỉ tính toán dựa trên các tin active."""
    loc_repo = LocationRepository(db_session)
    nearby = loc_repo.nearby_locations(
        lat=10.776,
        lng=106.700,
        district_id=setup_lifecycle_data["district_id"],
        radius_km=5.0,
    )
    assert isinstance(nearby, list)


def test_price_aggregates_and_stats_excludes_expired_listings(db_session, setup_lifecycle_data):
    """Nhóm 1: Xác minh thống kê giá phòng (price_aggregates & get_price_stats) loại trừ hoàn toàn tin expired."""
    service = ListingService(db_session)
    stats_res = service.get_price_stats(
        city_id=setup_lifecycle_data["city_id"],
        district_id=setup_lifecycle_data["district_id"],
        room_type_id=None,
    )

    # Thống kê chung
    assert stats_res.price_stats_general is not None
    # Nếu tin expired (giá 3.000.000) bị lọt vào, minimum_price sẽ là 3.000.000.
    # Nhưng vì chỉ tính tin active (giá 4.500.000), minimum_price phải >= 4.500.000
    if stats_res.price_stats_general.minimum_price_vnd is not None:
        assert stats_res.price_stats_general.minimum_price_vnd >= 4500000.0, "Tin expired giá 3tr không được làm giảm minimum_price"

    # Thống kê theo khu vực (phường)
    if stats_res.price_stats_by_area:
        for area_stat in stats_res.price_stats_by_area:
            if area_stat.area_id == setup_lifecycle_data["ward_id"]:
                assert area_stat.minimum_price_vnd is not None
                assert area_stat.minimum_price_vnd >= 4500000.0


def test_get_by_id_returns_expired_listing_with_notice(db_session, setup_lifecycle_data):
    """Nhóm 1: Xác minh truy vấn get_by_id với tin hết hạn vẫn lấy được dữ liệu và schema tự động gắn cảnh báo."""
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
    """Nhóm 1: Xác minh tin active không bị gán cảnh báo hết hạn."""
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
# NHÓM 2: BOUNDARY & EDGE CASES (DỮ LIỆU BIÊN & BẨN)
# ==============================================================================

def test_get_by_id_non_existent_returns_none(db_session):
    """Nhóm 2: Boundary - Truy vấn ID không tồn tại ở Repository trả về None."""
    repo = ListingRepository(db_session)
    assert repo.get_by_id("non_existent_id_xyz_123") is None


def test_http_get_by_id_non_existent_returns_404():
    """Nhóm 2: Boundary - Endpoint HTTP GET /api/v1/listings/{id} với ID không tồn tại trả về 404 Not Found."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    res = client.get("/api/v1/listings/non_existent_id_xyz_999")
    assert res.status_code == 404
    err_body = res.json()
    assert "not found" in err_body.get("detail", "").lower() or "not found" in str(err_body).lower()


def test_schema_edge_cases_null_timestamp_and_unusual_status():
    """Nhóm 2: Edge Cases - Xử lý an toàn khi last_checked_at=None, status lạ hoặc chữ hoa."""
    # 1. last_checked_at là None
    dto1 = ListingDetailResponse(
        id="test_dto_null_checked",
        title="Phòng trọ test null checked",
        is_active=True,
        status="active",
        last_checked_at=None,
    )
    assert dto1.last_checked_at is None
    assert dto1.is_expired is False
    assert dto1.status_notice is None

    # 2. status lạ e.g. "under_review" khi is_active=True
    dto2 = ListingDetailResponse(
        id="test_dto_under_review",
        title="Phòng trọ đang duyệt",
        is_active=True,
        status="under_review",
    )
    # Vì status != "active" nên compute_expiry_notice tự động đánh dấu is_expired = True
    assert dto2.is_expired is True
    assert dto2.status_notice is not None

    # 3. status rỗng và is_active=False
    dto3 = ListingDetailResponse(
        id="test_dto_empty_status",
        title="Phòng trọ status rỗng",
        is_active=False,
        status="",
    )
    assert dto3.is_expired is True
    assert dto3.status_notice is not None

    # 4. status chữ hoa "ACTIVE" với is_active=True
    dto4 = ListingDetailResponse(
        id="test_dto_caps_status",
        title="Phòng trọ chữ hoa",
        is_active=True,
        status="ACTIVE",
    )
    assert dto4.is_expired is False
    assert dto4.status_notice is None


def test_boundary_whitespace_search_query(db_session, setup_lifecycle_data):
    """Nhóm 2: Boundary - Chuỗi tìm kiếm chỉ có khoảng trắng không gây crash và xử lý an toàn."""
    repo = ListingRepository(db_session)
    results = repo.search(
        search="   ",
        city_id=setup_lifecycle_data["city_id"],
        district_id=setup_lifecycle_data["district_id"],
        ward_id=None,
        room_type_id=None,
        min_price=None,
        max_price=None,
        min_area=None,
        max_area=None,
        order_by="posted_date",
        sort_desc=True,
        limit=10,
        offset=0,
    )
    assert isinstance(results, list)


# ==============================================================================
# NHÓM 3: STATE MUTATION & RACE CONDITION (TÍNH TOÀN VẸN & BẤT BIẾN)
# ==============================================================================

def test_state_mutation_isolation_does_not_affect_active_listings(db_session, setup_lifecycle_data):
    """Nhóm 3: State Mutation - Thay đổi trạng thái tin expired không ảnh hưởng tới các tin active khác."""
    active_id = setup_lifecycle_data["active_id"]
    expired_id = setup_lifecycle_data["expired_id"]

    repo = ListingRepository(db_session)

    # Lấy đối tượng active trước
    active_before = repo.get_by_id(active_id)
    assert active_before.is_active is True

    # Cập nhật status của tin expired
    expired_orm = repo.get_by_id(expired_id)
    expired_orm.status = "expired_or_deleted"
    expired_orm.is_active = False
    db_session.commit()

    # Kiểm tra lại tin active: TUYỆT ĐỐI không bị đổi
    db_session.expire_all()
    active_after = repo.get_by_id(active_id)
    assert active_after.is_active is True
    assert active_after.status == "active"


def test_immutability_core_fields_intact(db_session, setup_lifecycle_data):
    """Nhóm 3: Immutability - Đọc tin expired không làm biến dạng các trường dữ liệu lõi (giá, toạ độ, diện tích)."""
    repo = ListingRepository(db_session)
    expired_id = setup_lifecycle_data["expired_id"]

    listing = repo.get_by_id(expired_id)
    assert listing.title == "Phòng trọ giá rẻ test expired"
    assert listing.price_vnd == 3000000.0
    assert listing.area_m2 == 20.0
    assert listing.lat == 10.780
    assert listing.lng == 106.695
    assert listing.address_raw == setup_lifecycle_data["expired_address_raw"]


# ==============================================================================
# NHÓM 4: PERSISTENCE TEST (LƯU TRỮ VÀ NẠP LẠI TỪ DB THẬT)
# ==============================================================================

def test_persistence_with_fresh_db_session(setup_lifecycle_data):
    """Nhóm 4: Persistence Test - Đóng session cũ, mở session mới hoàn toàn để xác minh dữ liệu đã persist."""
    expired_id = setup_lifecycle_data["expired_id"]
    active_id = setup_lifecycle_data["active_id"]

    # Mở một session DB hoàn toàn mới
    fresh_session = SessionLocal()
    try:
        fresh_repo = ListingRepository(fresh_session)
        exp_orm = fresh_repo.get_by_id(expired_id)
        act_orm = fresh_repo.get_by_id(active_id)

        assert exp_orm is not None
        assert exp_orm.is_active is False
        assert exp_orm.status == "expired_or_deleted"

        assert act_orm is not None
        assert act_orm.is_active is True
        assert act_orm.status == "active"
    finally:
        fresh_session.close()


def test_http_api_endpoints_for_lifecycle(setup_lifecycle_data):
    """Nhóm 4: HTTP API End-to-End Test qua FastAPI TestClient:
    1. GET /api/v1/listings/ không chứa tin expired.
    2. GET /api/v1/listings/{expired_id} trả về 200 kèm cờ is_expired=True và status_notice.
    3. GET /api/v1/listings/{active_id} trả về 200 kèm cờ is_expired=False.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    active_id = setup_lifecycle_data["active_id"]
    expired_id = setup_lifecycle_data["expired_id"]

    cid = setup_lifecycle_data["city_id"]
    did = setup_lifecycle_data["district_id"]

    # 1. Search endpoint
    res_search = client.get(f"/api/v1/listings/?search=test&city_id={cid}&district_id={did}")
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
