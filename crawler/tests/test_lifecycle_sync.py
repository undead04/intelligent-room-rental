"""Unit & Integration Tests cho tính năng Listing Lifecycle Sync trong Crawler Pipeline.

Tuân thủ quy chuẩn kiểm thử nghiêm ngặt (Black-box testing, chống Confirmation Bias):
1. Nhóm 1: Happy Path - sync_status_to_postgres() cập nhật chính xác trạng thái từ SQLite Staging sang PostgreSQL.
2. Nhóm 2: Boundary & Edge Cases - Xử lý danh sách ID rỗng, last_checked_at=None, định dạng thời gian lạ, status trống.
3. Nhóm 3: State Mutation & Race Condition - Sync tin expired không ảnh hưởng tới tin active khác, bảo toàn tính bất biến của các cột dữ liệu khác.
4. Nhóm 4: Persistence Test - Dữ liệu sau khi sync được lưu trữ và truy vấn lại nguyên vẹn từ PostgreSQL qua session mới.
"""

import os
import shutil
import tempfile
from datetime import datetime, timezone
import pytest
from sqlalchemy import text

from crawler.staging_db import StagingDatabase
from crawler.etl.db_models import Listing, create_db_session


@pytest.fixture(scope="module")
def pg_session():
    """Tạo kết nối tới PostgreSQL thật để kiểm tra luồng đồng bộ."""
    engine, session = create_db_session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def temp_staging():
    """Tạo Staging DB SQLite tạm thời cho từng test case."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_lifecycle_staging.db")
    db = StagingDatabase(db_path=db_path)
    yield db
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def setup_pg_listings(pg_session):
    """Khởi tạo các bản ghi Listing trong PostgreSQL phục vụ test sync."""
    id_active = "test_sync_pg_active_1"
    id_expired = "test_sync_pg_expired_2"
    id_control = "test_sync_pg_control_active_3"

    # Xóa sạch nếu đã tồn tại
    pg_session.query(Listing).filter(Listing.id.in_([id_active, id_expired, id_control])).delete(synchronize_session=False)
    pg_session.commit()

    # Tạo 3 bản ghi ban đầu: tất cả đều active
    l_active = Listing(
        id=id_active,
        title="Phòng trọ Active Ban Đầu",
        price_vnd=4000000.0,
        area_m2=22.0,
        address_raw="100 Hai Bà Trưng, Quận 1",
        lat=10.78,
        lng=106.69,
        is_active=True,
        status="active",
        last_checked_at=None,
    )
    l_expired = Listing(
        id=id_expired,
        title="Phòng trọ Sắp Hết Hạn",
        price_vnd=3500000.0,
        area_m2=20.0,
        address_raw="200 Hai Bà Trưng, Quận 1",
        lat=10.79,
        lng=106.70,
        is_active=True,
        status="active",
        last_checked_at=None,
    )
    l_control = Listing(
        id=id_control,
        title="Phòng trọ Đối Chứng Không Đổi",
        price_vnd=5000000.0,
        area_m2=30.0,
        address_raw="300 Lê Lợi, Quận 1",
        lat=10.77,
        lng=106.68,
        is_active=True,
        status="active",
        last_checked_at=None,
    )
    pg_session.add_all([l_active, l_expired, l_control])
    pg_session.commit()

    yield {
        "id_active": id_active,
        "id_expired": id_expired,
        "id_control": id_control,
    }

    # Dọn dẹp sau khi test xong
    pg_session.query(Listing).filter(Listing.id.in_([id_active, id_expired, id_control])).delete(synchronize_session=False)
    pg_session.commit()


# ==============================================================================
# NHÓM 1: HAPPY PATH
# ==============================================================================

def test_sync_status_happy_path(temp_staging, setup_pg_listings, pg_session):
    """Nhóm 1: Happy Path - sync_status_to_postgres cập nhật chính xác trạng thái từ SQLite sang PostgreSQL."""
    id_active = setup_pg_listings["id_active"]
    id_expired = setup_pg_listings["id_expired"]

    # 1. Lưu trạng thái mới vào Staging DB (1 tin vẫn active, 1 tin expired)
    checked_iso = "2026-11-05T14:30:00Z"
    temp_staging.save_listing({
        "listing_id": id_active,
        "source": "nhatot",
        "title": "Phòng trọ Active Ban Đầu",
        "is_active": True,
        "status": "active",
        "last_checked_at": checked_iso,
    })
    temp_staging.save_listing({
        "listing_id": id_expired,
        "source": "nhatot",
        "title": "Phòng trọ Sắp Hết Hạn",
        "is_active": False,
        "status": "expired_or_deleted",
        "last_checked_at": checked_iso,
    })

    # 2. Thực hiện sync
    stats = temp_staging.sync_status_to_postgres(specific_ids=[id_active, id_expired])
    assert stats["total_synced"] == 2
    assert stats["active"] == 1
    assert stats["expired"] == 1

    # 3. Kiểm tra kết quả trong PostgreSQL
    pg_session.expire_all()
    rec_active = pg_session.query(Listing).filter(Listing.id == id_active).one()
    rec_expired = pg_session.query(Listing).filter(Listing.id == id_expired).one()

    assert rec_active.is_active is True
    assert rec_active.status == "active"
    assert rec_active.last_checked_at is not None

    assert rec_expired.is_active is False
    assert rec_expired.status == "expired_or_deleted"
    assert rec_expired.last_checked_at is not None


# ==============================================================================
# NHÓM 2: BOUNDARY & EDGE CASES
# ==============================================================================

def test_sync_boundary_empty_ids(temp_staging):
    """Nhóm 2: Boundary - Truyền danh sách ID rỗng không làm crash và trả về 0."""
    stats = temp_staging.sync_status_to_postgres(specific_ids=[])
    assert stats["total_synced"] == 0
    assert stats["active"] == 0
    assert stats["expired"] == 0


def test_sync_boundary_empty_staging_db(temp_staging):
    """Nhóm 2: Boundary - Staging DB hoàn toàn rỗng không gây lỗi."""
    stats = temp_staging.sync_status_to_postgres(specific_ids=None)
    assert stats["total_synced"] == 0
    assert stats["active"] == 0
    assert stats["expired"] == 0


def test_sync_edge_cases_null_and_malformed_timestamp(temp_staging, setup_pg_listings, pg_session):
    """Nhóm 2: Edge Cases - last_checked_at=None hoặc chuỗi thời gian không hợp lệ vẫn xử lý an toàn."""
    id_expired = setup_pg_listings["id_expired"]

    # Lưu bản ghi với chuỗi ngày sai định dạng và status rỗng
    temp_staging.save_listing({
        "listing_id": id_expired,
        "source": "nhatot",
        "is_active": False,
        "status": "",  # status rỗng
        "last_checked_at": "invalid_date_format_xyz",
    })

    stats = temp_staging.sync_status_to_postgres(specific_ids=[id_expired])
    assert stats["total_synced"] == 1
    assert stats["expired"] == 1

    pg_session.expire_all()
    rec = pg_session.query(Listing).filter(Listing.id == id_expired).one()
    assert rec.is_active is False
    # Khi status rỗng và is_active=False, code tự động gán fallback 'expired_or_deleted'
    assert rec.status == "expired_or_deleted"
    # Fallback thời gian là datetime.now()
    assert rec.last_checked_at is not None


def test_sync_edge_case_non_existent_postgres_id(temp_staging):
    """Nhóm 2: Edge Case - ID có trong SQLite nhưng không tồn tại trong PostgreSQL không gây lỗi."""
    temp_staging.save_listing({
        "listing_id": "ghost_id_never_existed_9999",
        "source": "nhatot",
        "is_active": False,
        "status": "expired_or_deleted",
    })

    stats = temp_staging.sync_status_to_postgres(specific_ids=["ghost_id_never_existed_9999"])
    # Batch query vẫn thực thi UPDATE (0 row affected) an toàn
    assert stats["expired"] == 1
    assert stats["total_synced"] == 1


# ==============================================================================
# NHÓM 3: STATE MUTATION & RACE CONDITION
# ==============================================================================

def test_sync_state_mutation_does_not_affect_other_listings(temp_staging, setup_pg_listings, pg_session):
    """Nhóm 3: State Mutation - Đồng bộ tin expired không làm thay đổi trạng thái của các tin khác trong DB."""
    id_expired = setup_pg_listings["id_expired"]
    id_control = setup_pg_listings["id_control"]

    temp_staging.save_listing({
        "listing_id": id_expired,
        "source": "nhatot",
        "is_active": False,
        "status": "expired_or_deleted",
    })

    # Chỉ sync id_expired
    temp_staging.sync_status_to_postgres(specific_ids=[id_expired])

    pg_session.expire_all()
    rec_control = pg_session.query(Listing).filter(Listing.id == id_control).one()

    # Tin đối chứng BẮT BUỘC phải giữ nguyên trạng thái active
    assert rec_control.is_active is True, "Tin đối chứng không được bị chuyển sang expired"
    assert rec_control.status == "active"


def test_sync_immutability_preserves_other_listing_fields(temp_staging, setup_pg_listings, pg_session):
    """Nhóm 3: Immutability - Việc cập nhật lifecycle không làm biến dạng các trường dữ liệu khác."""
    id_expired = setup_pg_listings["id_expired"]

    # Lấy thông tin gốc trước khi sync
    pg_session.expire_all()
    before = pg_session.query(Listing).filter(Listing.id == id_expired).one()
    orig_title = before.title
    orig_price = before.price_vnd
    orig_area = before.area_m2
    orig_lat = before.lat
    orig_lng = before.lng
    orig_address = before.address_raw

    temp_staging.save_listing({
        "listing_id": id_expired,
        "source": "nhatot",
        "is_active": False,
        "status": "expired_or_deleted",
    })

    temp_staging.sync_status_to_postgres(specific_ids=[id_expired])

    pg_session.expire_all()
    after = pg_session.query(Listing).filter(Listing.id == id_expired).one()

    # Chỉ có is_active và status thay đổi, các trường cốt lõi giữ nguyên 100%
    assert after.is_active is False
    assert after.status == "expired_or_deleted"
    assert after.title == orig_title
    assert after.price_vnd == orig_price
    assert after.area_m2 == orig_area
    assert after.lat == orig_lat
    assert after.lng == orig_lng
    assert after.address_raw == orig_address


# ==============================================================================
# NHÓM 4: PERSISTENCE TEST
# ==============================================================================

def test_sync_persistence_with_fresh_db_connection(temp_staging, setup_pg_listings):
    """Nhóm 4: Persistence Test - Dữ liệu sau khi sync được commit vào PostgreSQL và đọc lại từ connection mới."""
    id_expired = setup_pg_listings["id_expired"]

    temp_staging.save_listing({
        "listing_id": id_expired,
        "source": "nhatot",
        "is_active": False,
        "status": "expired_or_deleted",
        "last_checked_at": "2026-11-05T15:00:00Z",
    })

    temp_staging.sync_status_to_postgres(specific_ids=[id_expired])

    # Mở một connection/session HOÀN TOÀN MỚI
    engine, fresh_session = create_db_session()
    try:
        fresh_rec = fresh_session.query(Listing).filter(Listing.id == id_expired).one()
        assert fresh_rec.is_active is False
        assert fresh_rec.status == "expired_or_deleted"
        assert fresh_rec.last_checked_at is not None
    finally:
        fresh_session.close()
