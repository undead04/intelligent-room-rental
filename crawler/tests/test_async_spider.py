"""Bộ kiểm thử Black-box độc lập cho Crawler Asynchronous Concurrency Module.

Kiểm tra toàn diện 4 nhóm:
- Nhóm 1: Happy Path (async_fetch_with_status, async_fetch_with_retry, async_verify, verify shim, async_crawl_regions, BaseSpider fallback)
- Nhóm 2: Boundary & Edge Cases (Staging DB rỗng, lỗi mạng/timeout/500, payload hỏng, API response hỏng)
- Nhóm 3: State Mutation & Concurrency (Semaphore Guard strictly <= max_concurrency, SQLite Staging DB concurrency Lock)
- Nhóm 4: Integration & Full Regression
"""

import asyncio
import os
import sqlite3
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests

from crawler.spiders.base import BaseSpider
from crawler.spiders.nhatot import NhaTotSpider
from crawler.staging_db import StagingDatabase
from crawler.utils.http import (
    async_fetch_with_retry,
    async_fetch_with_status,
)


# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def temp_staging_db(tmp_path):
    """Khởi tạo một database SQLite Staging độc lập trong thư mục tạm."""
    db_file = tmp_path / "test_staging.db"
    db = StagingDatabase(db_path=str(db_file))
    return db


@pytest.fixture
def nhatot_spider(temp_staging_db):
    """Khởi tạo NhaTotSpider gắn với database staging tạm biệt lập."""
    spider = NhaTotSpider()
    spider.staging_db = temp_staging_db
    return spider


# ==============================================================================
# NHÓM 1 — HAPPY PATH
# ==============================================================================


class TestAsyncHappyPath:
    """Kiểm thử các kịch bản thành công tiêu chuẩn cho luồng bất đồng bộ."""

    def test_async_fetch_with_status_200(self):
        """async_fetch_with_status trả về đúng tuple (200, json_dict) khi HTTP 200."""

        async def _run():
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"success": True, "data": [1, 2, 3]}

            with patch("crawler.utils.http.requests.get", return_value=mock_resp):
                status, data = await async_fetch_with_status("https://example.com/api/test")
                assert status == 200
                assert data == {"success": True, "data": [1, 2, 3]}

        asyncio.run(_run())

    def test_async_fetch_with_status_404(self):
        """async_fetch_with_status trả về đúng tuple (404, None) khi tin hết hạn/xóa."""

        async def _run():
            mock_resp = MagicMock()
            mock_resp.status_code = 404

            with patch("crawler.utils.http.requests.get", return_value=mock_resp):
                status, data = await async_fetch_with_status("https://example.com/api/test/404")
                assert status == 404
                assert data is None

        asyncio.run(_run())

    def test_async_fetch_with_retry_success(self):
        """async_fetch_with_retry trả về JSON dict khi request thành công."""

        async def _run():
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"ads": [{"id": 1}, {"id": 2}]}

            with patch("crawler.utils.http.requests.get", return_value=mock_resp):
                result = await async_fetch_with_retry("https://example.com/api/crawl")
                assert result == {"ads": [{"id": 1}, {"id": 2}]}

        asyncio.run(_run())

    def test_async_fetch_with_retry_failure_returns_none(self):
        """async_fetch_with_retry trả về None khi server trả mã lỗi hoặc kết nối thất bại."""

        async def _run():
            mock_resp = MagicMock()
            mock_resp.status_code = 404

            with patch("crawler.utils.http.requests.get", return_value=mock_resp):
                result = await async_fetch_with_retry("https://example.com/api/crawl", max_retries=1)
                assert result is None

        asyncio.run(_run())

    def test_async_verify_active_and_expired_listings(self, nhatot_spider, temp_staging_db):
        """async_verify xử lý đúng danh sách tin, nhận diện active vs expired và lưu trạng thái vào DB."""

        # 1. Nạp dữ liệu vào Staging DB
        items = [
            {"list_id": "1001", "title": "Phòng trọ Q1", "is_active": True},
            {"list_id": "1002", "title": "Phòng trọ Bình Thạnh", "is_active": True},
            {"list_id": "1003", "title": "Phòng trọ Thủ Đức", "is_active": True},
        ]
        for it in items:
            temp_staging_db.save_listing(it, source="nhatot")

        # 2. Mock phản hồi API Chợ Tốt:
        # - 1001: 200 active
        # - 1002: 404 expired
        # - 1003: 200 nhưng status='sold' (đã cho thuê / hết hạn)
        async def mock_fetch_status(url, *args, **kwargs):
            if "1001" in url:
                return 200, {"ad": {"status": "active", "state": "accepted"}}
            elif "1002" in url:
                return 404, None
            elif "1003" in url:
                return 200, {"ad": {"status": "sold", "state": "rejected"}}
            return None, None

        async def _run():
            with patch("crawler.spiders.nhatot.async_fetch_with_status", side_effect=mock_fetch_status):
                stats = await nhatot_spider.async_verify(limit=10, max_concurrency=2)

                # Kiểm tra định dạng và số liệu stats
                assert stats == {"checked": 3, "active": 1, "expired": 2, "error": 0}
                assert stats["checked"] == stats["active"] + stats["expired"] + stats["error"]

                # Kiểm tra tính toàn vẹn trong SQLite Staging DB
                records = {
                    r["list_id"]: r
                    for r in temp_staging_db.get_raw_listings(source="nhatot")
                }
                assert len(records) == 3

                # Tin 1001: còn active
                assert records["1001"]["is_active"] is True
                assert records["1001"]["status"] == "active"
                assert "last_checked_at" in records["1001"]

                # Tin 1002: hết hạn (404)
                assert records["1002"]["is_active"] is False
                assert records["1002"]["status"] == "expired_or_deleted"

                # Tin 1003: hết hạn/ẩn (sold)
                assert records["1003"]["is_active"] is False
                assert records["1003"]["status"] == "sold"

        asyncio.run(_run())

    def test_verify_sync_wrapper_standard(self, nhatot_spider, temp_staging_db):
        """Hàm đồng bộ verify() (shim wrapper) hoạt động trơn tru trong ngữ cảnh không có event loop."""
        temp_staging_db.save_listing({"list_id": "2001", "title": "Tin test"}, source="nhatot")

        with patch(
            "crawler.spiders.nhatot.async_fetch_with_status",
            return_value=(200, {"ad": {"status": "active", "state": "accepted"}}),
        ):
            stats = nhatot_spider.verify(limit=5)
            assert stats["checked"] == 1
            assert stats["active"] == 1
            assert stats["expired"] == 0
            assert stats["error"] == 0

    def test_verify_sync_wrapper_inside_running_event_loop(self, nhatot_spider, temp_staging_db):
        """Hàm đồng bộ verify() hoạt động hoàn hảo kể cả khi được gọi lồng bên trong một event loop đang chạy."""
        temp_staging_db.save_listing({"list_id": "2002", "title": "Tin test loop"}, source="nhatot")

        async def _coro_with_running_loop():
            # Trong coroutine này, event loop đang chạy (loop.is_running() == True)
            with patch(
                "crawler.spiders.nhatot.async_fetch_with_status",
                return_value=(404, None),
            ):
                # Gọi verify() đồng bộ từ trong event loop
                stats = nhatot_spider.verify(limit=5)
                assert stats["checked"] == 1
                assert stats["expired"] == 1
                assert stats["active"] == 0

        asyncio.run(_coro_with_running_loop())

    def test_async_crawl_regions_aggregates_total(self, nhatot_spider):
        """async_crawl_regions cào song song các vùng và cộng dồn đúng tổng số tin."""

        crawl_results = {
            "hcm": 15,
            "hanoi": 10,
            "danang": 5,
        }

        def mock_crawl(pages=5, mode="resume", region="all"):
            return crawl_results.get(region, 0)

        async def _run():
            with patch.object(nhatot_spider, "crawl", side_effect=mock_crawl):
                total = await nhatot_spider.async_crawl_regions(
                    pages=2,
                    mode="resume",
                    regions=["hcm", "hanoi", "danang"],
                    max_concurrent_regions=2,
                )
                assert total == 30

        asyncio.run(_run())

    def test_base_spider_fallback_implementations(self):
        """BaseSpider cung cấp fallback async_verify và async_crawl gọi các hàm đồng bộ tương ứng."""

        class DummySpider(BaseSpider):
            def crawl(self, pages: int = 5, mode: str = "resume", region: str = "all") -> int:
                return pages * 2

            def verify(self, limit: int = 100, delay: float = 1.0) -> dict:
                return {"checked": limit, "active": limit, "expired": 0, "error": 0}

        async def _run():
            dummy = DummySpider(name="dummy")
            crawled = await dummy.async_crawl(pages=3, mode="resume", region="all")
            assert crawled == 6

            verified = await dummy.async_verify(limit=25)
            assert verified["checked"] == 25
            assert verified["active"] == 25

        asyncio.run(_run())

    def test_nhatot_async_crawl_routing(self, nhatot_spider):
        """async_crawl tự động route sang async_crawl_regions khi region='all', hoặc crawl 1 vùng cụ thể."""

        async def _run():
            with patch.object(
                nhatot_spider, "async_crawl_regions", new_callable=AsyncMock, return_value=42
            ) as mock_regions:
                result = await nhatot_spider.async_crawl(pages=3, region="all")
                assert result == 42
                mock_regions.assert_awaited_once_with(pages=3, mode="resume")

            with patch.object(nhatot_spider, "crawl", return_value=12) as mock_crawl:
                result = await nhatot_spider.async_crawl(pages=2, region="hcm")
                assert result == 12
                mock_crawl.assert_called_once_with(pages=2, mode="resume", region="hcm")

        asyncio.run(_run())


# ==============================================================================
# NHÓM 2 — BOUNDARY & EDGE CASES
# ==============================================================================


class TestAsyncBoundaryAndEdgeCases:
    """Kiểm thử các trường hợp biên, lỗi mạng, payload hỏng và response bất thường."""

    def test_async_verify_empty_staging_db(self, nhatot_spider):
        """Khi Staging DB rỗng, async_verify trả về stats rỗng an toàn, không crash."""

        async def _run():
            stats = await nhatot_spider.async_verify(limit=50)
            assert stats == {"checked": 0, "active": 0, "expired": 0, "error": 0}

        asyncio.run(_run())

    def test_async_verify_network_errors_and_http_500(self, nhatot_spider, temp_staging_db):
        """Request bị lỗi HTTP 500 hoặc Timeout/RequestException được ghi nhận vào stats['error'], không làm gãy coroutine khác."""

        # Nạp 4 tin:
        # - 3001: 200 OK (active)
        # - 3002: 500 Internal Server Error
        # - 3003: 404 Not Found (expired)
        # - 3004: Network Connection Error (None)
        items = [
            {"list_id": "3001", "title": "Tin 1"},
            {"list_id": "3002", "title": "Tin 2"},
            {"list_id": "3003", "title": "Tin 3"},
            {"list_id": "3004", "title": "Tin 4"},
        ]
        for it in items:
            temp_staging_db.save_listing(it, source="nhatot")

        async def mock_fetch_status(url, *args, **kwargs):
            if "3001" in url:
                return 200, {"ad": {"status": "active", "state": "accepted"}}
            elif "3002" in url:
                return 500, None
            elif "3003" in url:
                return 404, None
            elif "3004" in url:
                return None, None
            return None, None

        async def _run():
            with patch("crawler.spiders.nhatot.async_fetch_with_status", side_effect=mock_fetch_status):
                stats = await nhatot_spider.async_verify(limit=10, max_concurrency=2)

                assert stats["checked"] == 4
                assert stats["active"] == 1
                assert stats["expired"] == 1
                assert stats["error"] == 2
                assert stats["checked"] == stats["active"] + stats["expired"] + stats["error"]

        asyncio.run(_run())

    def test_async_verify_corrupted_payload_missing_fields(self, nhatot_spider, temp_staging_db):
        """Bản ghi thiếu list_id, payload rỗng hoặc data không hợp lệ không làm sập tiến trình kiểm tra."""

        # Ghi trực tiếp các bản ghi dị tật vào bảng raw_listings
        with temp_staging_db._get_connection() as conn:
            conn.execute(
                "INSERT INTO raw_listings (listing_id, source, payload_json) VALUES (?, ?, ?)",
                ("nhatot_valid_1", "nhatot", '{"list_id": "valid_1", "title": "Tin hợp lệ"}'),
            )
            # Bản ghi có payload_json là rỗng {}
            conn.execute(
                "INSERT INTO raw_listings (listing_id, source, payload_json) VALUES (?, ?, ?)",
                ("nhatot_corrupt_empty", "nhatot", "{}"),
            )
            # Bản ghi không có list_id trong JSON
            conn.execute(
                "INSERT INTO raw_listings (listing_id, source, payload_json) VALUES (?, ?, ?)",
                ("nhatot_no_list_id", "nhatot", '{"title": "Thiếu id hoàn toàn"}'),
            )
            conn.commit()

        async def mock_fetch_status(url, *args, **kwargs):
            return 200, {"ad": {"status": "active", "state": "accepted"}}

        async def _run():
            with patch("crawler.spiders.nhatot.async_fetch_with_status", side_effect=mock_fetch_status):
                stats = await nhatot_spider.async_verify(limit=10)
                # Chỉ có tin có list_id được đưa vào danh sách kiểm tra
                assert stats["checked"] >= 1
                assert stats["active"] >= 1

        asyncio.run(_run())

    def test_async_verify_malformed_api_response(self, nhatot_spider, temp_staging_db):
        """Phản hồi API có mã 200 nhưng payload dị dạng (string, list, hoặc thiếu object 'ad') được tính là error."""

        temp_staging_db.save_listing({"list_id": "4001", "title": "Tin test"}, source="nhatot")
        temp_staging_db.save_listing({"list_id": "4002", "title": "Tin test 2"}, source="nhatot")

        async def mock_fetch_status(url, *args, **kwargs):
            if "4001" in url:
                # 200 nhưng trả về chuỗi text html lỗi
                return 200, "<html>Bad Gateway</html>"
            elif "4002" in url:
                # 200 nhưng ad là None
                return 200, {"ad": None}
            return None, None

        async def _run():
            with patch("crawler.spiders.nhatot.async_fetch_with_status", side_effect=mock_fetch_status):
                stats = await nhatot_spider.async_verify(limit=5)
                assert stats["checked"] == 2
                assert stats["error"] == 2
                assert stats["active"] == 0
                assert stats["expired"] == 0

        asyncio.run(_run())

    def test_async_crawl_regions_handles_region_exception_gracefully(self, nhatot_spider):
        """Khi một vùng gặp lỗi nghiêm trọng (exception), async_crawl_regions không vỡ mà vẫn tổng hợp các vùng còn lại."""

        def mock_crawl(pages=5, mode="resume", region="all"):
            if region == "danang":
                raise RuntimeError("Lỗi mạng nghiêm trọng tại vùng Đà Nẵng")
            elif region == "hcm":
                return 18
            elif region == "hanoi":
                return 12
            return 0

        async def _run():
            with patch.object(nhatot_spider, "crawl", side_effect=mock_crawl):
                total = await nhatot_spider.async_crawl_regions(
                    pages=2,
                    mode="resume",
                    regions=["hcm", "danang", "hanoi"],
                    max_concurrent_regions=2,
                )
                # 18 (HCM) + 12 (Hanoi) = 30 (Đà Nẵng lỗi được bỏ qua)
                assert total == 30

        asyncio.run(_run())


# ==============================================================================
# NHÓM 3 — CONCURRENCY & SEMAPHORE GUARD (QUAN TRỌNG NHẤT)
# ==============================================================================


class TestConcurrencyAndSemaphoreGuard:
    """Kiểm thử cơ chế Semaphore giới hạn lưu lượng đồng thời và tính toàn vẹn SQLite Staging DB."""

    def test_semaphore_guard_never_exceeds_max_concurrency(self, nhatot_spider, temp_staging_db):
        """Đếm số coroutine chạy đồng thời tại mọi thời điểm, khẳng định KHÔNG BAO GIỜ vượt quá max_concurrency."""

        # 1. Nạp 16 tin vào Staging DB
        for i in range(16):
            temp_staging_db.save_listing({"list_id": f"sem_{i:02d}", "title": f"Phòng trọ {i}"}, source="nhatot")

        active_workers = 0
        max_observed_workers = 0
        counter_lock = asyncio.Lock()
        max_limit = 3

        async def mock_fetch_status(url, *args, **kwargs):
            nonlocal active_workers, max_observed_workers

            async with counter_lock:
                active_workers += 1
                if active_workers > max_observed_workers:
                    max_observed_workers = active_workers

            # Mô phỏng I/O network delay
            await asyncio.sleep(0.04)

            async with counter_lock:
                active_workers -= 1

            return 200, {"ad": {"status": "active", "state": "accepted"}}

        async def _run():
            with patch("crawler.spiders.nhatot.async_fetch_with_status", side_effect=mock_fetch_status):
                stats = await nhatot_spider.async_verify(limit=16, max_concurrency=max_limit)

                assert stats["checked"] == 16
                assert stats["active"] == 16

                # Khẳng định số active worker tối đa quan sát được KHÔNG ĐƯỢC vượt quá max_concurrency
                assert max_observed_workers <= max_limit, (
                    f"Vi phạm Semaphore: Số worker đồng thời đạt {max_observed_workers}, "
                    f"vượt quá ngưỡng cho phép {max_limit}!"
                )
                # Khẳng định hệ thống thực sự chạy song song (lớn hơn 1) chứ không phải tuần tự đơn luồng
                assert max_observed_workers > 1, "Hệ thống đang chạy tuần tự đơn luồng thay vì song song bất đồng bộ!"

        asyncio.run(_run())

    def test_async_fetch_with_status_direct_semaphore_guard(self):
        """async_fetch_with_status trực tiếp tuân thủ Semaphore truyền vào khi gọi đồng thời nhiều task."""
        import threading

        active_count = 0
        max_observed = 0
        counter_thread_lock = threading.Lock()
        sem = asyncio.Semaphore(4)

        def mock_sync_fetch(url, *args, **kwargs):
            nonlocal active_count, max_observed
            with counter_thread_lock:
                active_count += 1
                if active_count > max_observed:
                    max_observed = active_count
            time.sleep(0.02)
            with counter_thread_lock:
                active_count -= 1
            return 200, {"ok": True}

        async def _run():
            with patch("crawler.utils.http.fetch_with_status", side_effect=mock_sync_fetch):
                # async_fetch_with_status tự acquire semaphore, không wrap bên ngoài để tránh double acquire deadlock
                tasks = [
                    async_fetch_with_status(f"https://api.test/{i}", semaphore=sem)
                    for i in range(20)
                ]
                results = await asyncio.gather(*tasks)

                assert len(results) == 20
                for status, data in results:
                    assert status == 200

                assert max_observed <= 4, f"Lưu lượng vượt quá semaphore limit: {max_observed} > 4"
                assert max_observed > 1

        asyncio.run(_run())

    def test_sqlite_staging_db_concurrency_integrity_no_lock_error(self, temp_staging_db):
        """Cho 30 tasks ghi cập nhật trạng thái đồng thời qua asyncio.Lock + save_listing, xác nhận KHÔNG phát sinh sqlite3.OperationalError."""

        lock = asyncio.Lock()
        num_tasks = 30

        async def _save_worker(item_idx: int):
            item = {
                "list_id": f"conc_{item_idx:03d}",
                "title": f"Phòng trọ ghi đồng thời {item_idx}",
                "price": 3000000 + item_idx * 100000,
                "is_active": True,
            }
            # Cấu trúc đồng bộ giống hệt NhaTotSpider.async_verify
            async with lock:
                await asyncio.to_thread(temp_staging_db.save_listing, item, source="nhatot")

        async def _run():
            tasks = [_save_worker(i) for i in range(num_tasks)]
            await asyncio.gather(*tasks)

            # Kiểm tra toàn bộ dữ liệu đã được ghi đầy đủ và chuẩn xác vào SQLite
            saved = temp_staging_db.get_raw_listings(source="nhatot")
            assert len(saved) == num_tasks, f"Thiếu bản ghi: kỳ vọng {num_tasks}, thực tế {len(saved)}"

            ids = {r.get("list_id") for r in saved}
            for i in range(num_tasks):
                assert f"conc_{i:03d}" in ids

        asyncio.run(_run())

    def test_async_verify_end_to_end_concurrency_db_integrity(self, nhatot_spider, temp_staging_db):
        """Toàn bộ quy trình async_verify với 25 tin chạy dưới max_concurrency=8 không sinh lỗi lock DB và cập nhật 100% bản ghi."""

        total_items = 25
        for i in range(total_items):
            temp_staging_db.save_listing(
                {"list_id": f"e2e_{i:02d}", "title": f"Tin {i}", "is_active": True},
                source="nhatot",
            )

        async def mock_fetch_status(url, *args, **kwargs):
            # 50% tin còn active, 50% tin hết hạn
            list_id = url.split("/")[-1]
            idx = int(list_id.replace("e2e_", ""))
            await asyncio.sleep(0.02)
            if idx % 2 == 0:
                return 200, {"ad": {"status": "active", "state": "accepted"}}
            else:
                return 404, None

        async def _run():
            with patch("crawler.spiders.nhatot.async_fetch_with_status", side_effect=mock_fetch_status):
                stats = await nhatot_spider.async_verify(limit=total_items, max_concurrency=8)

                assert stats["checked"] == total_items
                expected_active = (total_items + 1) // 2  # các chỉ số chẵn: 0, 2, ..., 24 -> 13
                expected_expired = total_items // 2      # các chỉ số lẻ: 1, 3, ..., 23 -> 12
                assert stats["active"] == expected_active
                assert stats["expired"] == expected_expired
                assert stats["error"] == 0

                # Kiểm tra trong DB
                db_items = temp_staging_db.get_raw_listings(source="nhatot")
                assert len(db_items) == total_items
                for item in db_items:
                    assert "last_checked_at" in item
                    idx = int(item["list_id"].replace("e2e_", ""))
                    if idx % 2 == 0:
                        assert item["is_active"] is True
                        assert item["status"] == "active"
                    else:
                        assert item["is_active"] is False
                        assert item["status"] == "expired_or_deleted"

        asyncio.run(_run())


# ==============================================================================
# NHÓM 4 — INTEGRATION & SPIDER RUN LIFECYCLE
# ==============================================================================


class TestSpiderLifecycleIntegration:
    """Kiểm thử tích hợp luồng thực thi vòng đời spider (Spider Run Lifecycle)."""

    def test_spider_run_in_verify_mode(self, nhatot_spider, temp_staging_db):
        """spider.run(mode='verify', auto_clean=False) kích hoạt verify() hoàn tất và ghi log chuẩn."""

        temp_staging_db.save_listing({"list_id": "9001", "title": "Tin kiểm thử run"}, source="nhatot")

        with patch(
            "crawler.spiders.nhatot.async_fetch_with_status",
            return_value=(200, {"ad": {"status": "active", "state": "accepted"}}),
        ):
            # Chạy chế độ verify đồng bộ không tự động gọi ETL
            nhatot_spider.run(mode="verify", limit=5, auto_clean=False)

            records = temp_staging_db.get_raw_listings(source="nhatot")
            assert len(records) == 1
            assert records[0]["is_active"] is True
            assert records[0]["status"] == "active"

    def test_async_crawl_regions_semaphore_limiting(self, nhatot_spider):
        """async_crawl_regions đảm bảo số vùng cào đồng thời không vượt quá max_concurrent_regions."""
        import threading

        active_regions = 0
        max_concurrent_regions_seen = 0
        region_thread_lock = threading.Lock()
        max_allowed = 2

        def mock_crawl(pages=5, mode="resume", region="all"):
            nonlocal active_regions, max_concurrent_regions_seen
            with region_thread_lock:
                active_regions += 1
                if active_regions > max_concurrent_regions_seen:
                    max_concurrent_regions_seen = active_regions
            time.sleep(0.04)
            with region_thread_lock:
                active_regions -= 1
            return 10

        async def _run():
            with patch.object(nhatot_spider, "crawl", side_effect=mock_crawl):
                total = await nhatot_spider.async_crawl_regions(
                    pages=1,
                    regions=["hcm", "hanoi", "danang", "binhduong", "dongnai"],
                    max_concurrent_regions=max_allowed,
                )
                assert total == 50
                assert max_concurrent_regions_seen <= max_allowed, (
                    f"Vượt quá giới hạn concurrency vùng: {max_concurrent_regions_seen} > {max_allowed}"
                )
                assert max_concurrent_regions_seen > 1, "Các vùng không chạy đồng thời!"

        asyncio.run(_run())

    def test_spider_run_routes_all_regions_through_semaphore(self, nhatot_spider, monkeypatch):
        """spider.run(region='all') tự động đi qua async_crawl_regions với Semaphore giới hạn concurrency."""
        import threading
        from crawler.config import settings

        monkeypatch.setattr(settings, "CRAWL_MAX_CONCURRENT_REGIONS", 2)
        active = 0
        max_seen = 0
        called_regions = []
        lock = threading.Lock()

        def mock_crawl(pages=5, mode="resume", region="all"):
            nonlocal active, max_seen
            with lock:
                called_regions.append(region)
                active += 1
                max_seen = max(max_seen, active)
            time.sleep(0.03)
            with lock:
                active -= 1
            return 3

        with patch.object(nhatot_spider, "crawl", side_effect=mock_crawl):
            nhatot_spider.run(mode="update", pages=1, region="all", auto_clean=False)

        assert set(called_regions) == set(settings.REGIONS.keys())
        assert 1 < max_seen <= 2, f"Concurrency vượt quá CRAWL_MAX_CONCURRENT_REGIONS: {max_seen}"

    def test_staging_db_and_checkpoint_concurrent_writes(self, nhatot_spider, temp_staging_db, tmp_path, monkeypatch):
        """Nhiều thread vùng ghi đồng thời vào StagingDatabase và checkpoint JSON không bị race condition hay corrupt."""
        import concurrent.futures
        import json
        from crawler.spiders import base as base_mod

        monkeypatch.setattr(base_mod, "RAW_DATA_DIR", tmp_path)
        nhatot_spider.raw_dir = str(tmp_path)

        def _worker(idx: int) -> None:
            temp_staging_db.save_listing({"list_id": f"conc_{idx}_a", "title": f"Tin {idx}A"}, source="nhatot")
            temp_staging_db.save_listing({"list_id": f"conc_{idx}_b", "title": f"Tin {idx}B"}, source="nhatot")
            nhatot_spider.save_checkpoint(offset=idx * 50, region="hcm")

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(_worker, range(8)))

        records = temp_staging_db.get_raw_listings(source="nhatot")
        assert len(records) == 16
        ckpt_path = tmp_path / "checkpoint_nhatot_hcm.json"
        assert ckpt_path.exists()
        ckpt_data = json.loads(ckpt_path.read_text(encoding="utf-8"))
        assert ckpt_data["region"] == "hcm"
        assert isinstance(ckpt_data["last_offset"], int)
