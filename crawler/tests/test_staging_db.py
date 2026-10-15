"""Unit tests cho SQLite Staging Database và Incremental ETL Pipeline của Crawler."""

import os
import shutil
import tempfile
import pytest

from crawler.staging_db import StagingDatabase
from crawler.spiders.base import BaseSpider
from crawler.etl.extract import extract_raw_listings


@pytest.fixture
def temp_db():
    """Tạo Staging DB tạm thời cho mỗi test case."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_staging.db")
    db = StagingDatabase(db_path=db_path)
    yield db
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_staging_db_init(temp_db):
    assert os.path.exists(temp_db.db_path)
    summary = temp_db.count_summary()
    assert summary["total"] == 0
    assert summary["processed"] == 0
    assert summary["unprocessed"] == 0


def test_save_and_retrieve_listing(temp_db):
    item = {
        "listing_id": "nhatot_123456",
        "title": "Phòng trọ Thủ Đức giá rẻ",
        "price_vnd": 2500000,
        "source": "nhatot",
    }
    saved = temp_db.save_listing(item)
    assert saved is True

    summary = temp_db.count_summary()
    assert summary["total"] == 1
    assert summary["unprocessed"] == 1

    processed_ids = temp_db.get_processed_ids(source="nhatot")
    assert "123456" in processed_ids
    assert "nhatot_123456" in processed_ids

    records = temp_db.get_raw_listings(unprocessed_only=True)
    assert len(records) == 1
    assert records[0]["title"] == "Phòng trọ Thủ Đức giá rẻ"


def test_save_listings_batch(temp_db):
    items = [
        {"listing_id": f"nhatot_{i}", "title": f"Phòng {i}", "source": "nhatot"}
        for i in range(10)
    ]
    saved_count = temp_db.save_listings_batch(items)
    assert saved_count == 10

    summary = temp_db.count_summary()
    assert summary["total"] == 10
    assert summary["unprocessed"] == 10


def test_mark_as_processed_incremental(temp_db):
    items = [
        {"listing_id": "item_1", "title": "P1", "source": "nhatot"},
        {"listing_id": "item_2", "title": "P2", "source": "nhatot"},
        {"listing_id": "item_3", "title": "P3", "source": "nhatot"},
    ]
    temp_db.save_listings_batch(items)

    # Đánh dấu 2 tin đã xử lý
    updated = temp_db.mark_as_processed(["item_1", "item_2"])
    assert updated == 2

    # Lọc incremental chỉ còn 1 tin chưa xử lý
    unprocessed = temp_db.get_raw_listings(unprocessed_only=True)
    assert len(unprocessed) == 1
    assert unprocessed[0]["listing_id"] == "item_3"

    # Lọc toàn bộ vẫn đủ 3 tin
    all_records = temp_db.get_raw_listings(unprocessed_only=False)
    assert len(all_records) == 3


def test_base_spider_integration(temp_db, monkeypatch):
    from crawler.staging_db import staging_db
    monkeypatch.setattr("crawler.spiders.base.staging_db", temp_db)

    class DummySpider(BaseSpider):
        def crawl(self, pages=1, mode="resume", region="all"):
            return 0
        def verify(self, limit=100, delay=1.0):
            return {}

    spider = DummySpider(name="dummyspider")
    spider.staging_db = temp_db

    # Lưu qua spider
    spider.save_listing({
        "listing_id": "dummyspider_999",
        "title": "Phòng Dummy",
    })

    # Kiểm tra ID
    ids = spider.get_processed_ids()
    assert "999" in ids
    assert "dummyspider_999" in ids
