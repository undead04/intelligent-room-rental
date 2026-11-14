"""SQLite Staging Storage Manager cho Crawler Pipeline.
Quản lý dữ liệu cào thô trong đúng 1 file database duy nhất: crawler/data/raw/staging.db.
Hỗ trợ kiểm tra trùng lặp O(1), tối ưu I/O đĩa và Incremental ETL.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger(__name__)

from crawler.config.paths import STAGING_DB_PATH_STR

DEFAULT_DB_PATH = STAGING_DB_PATH_STR


class StagingDatabase:
    """Quản lý kho dữ liệu thô (Staging Area) trên nền SQLite."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._write_lock = threading.RLock()
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Tạo kết nối SQLite và bật các cờ PRAGMA hiệu năng cao."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA temp_store = MEMORY;")
        return conn

    def init_db(self):
        """Khởi tạo cấu trúc bảng và các chỉ mục nếu chưa tồn tại."""
        with self._write_lock:
            with self._get_connection() as conn:
                # Bật WAL mode (Write-Ahead Logging) trong lock ghi để tránh tranh chấp đa luồng
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS raw_listings (
                        listing_id TEXT PRIMARY KEY,
                        source TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_processed INTEGER DEFAULT 0
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_raw_unprocessed 
                    ON raw_listings(is_processed, source);
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_raw_source 
                    ON raw_listings(source);
                    """
                )
                conn.commit()

    def save_listing(self, item: Dict[str, Any], source: Optional[str] = None) -> bool:
        """Lưu một bản ghi listing thô vào database.

        Nếu listing_id đã tồn tại, sẽ ghi đè bản mới nhất và đặt lại is_processed = 0.
        """
        src = source or str(item.get("source") or "nhatot").lower()
        sub_id = item.get("list_id") or item.get("ad_id") or item.get("id")
        listing_id = str(
            item.get("listing_id")
            or (f"{src}_{sub_id}" if sub_id else "")
        )
        payload_str = json.dumps(item, ensure_ascii=False)

        with self._write_lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO raw_listings (listing_id, source, payload_json, is_processed)
                    VALUES (?, ?, ?, 0)
                    ON CONFLICT(listing_id) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        crawled_at = CURRENT_TIMESTAMP,
                        is_processed = 0;
                    """,
                    (listing_id, src, payload_str),
                )
                conn.commit()
        return True

    def save_listings_batch(
        self, items: List[Dict[str, Any]], source: Optional[str] = None
    ) -> int:
        """Lưu nhiều bản ghi listing thô theo lô trong 1 transaction duy nhất."""
        if not items:
            return 0

        rows = []
        for item in items:
            src = source or str(item.get("source") or "nhatot").lower()
            sub_id = item.get("list_id") or item.get("ad_id") or item.get("id")
            listing_id = str(
                item.get("listing_id")
                or (f"{src}_{sub_id}" if sub_id else "")
            )
            payload_str = json.dumps(item, ensure_ascii=False)
            rows.append((listing_id, src, payload_str))

        with self._write_lock:
            with self._get_connection() as conn:
                conn.executemany(
                    """
                    INSERT INTO raw_listings (listing_id, source, payload_json, is_processed)
                    VALUES (?, ?, ?, 0)
                    ON CONFLICT(listing_id) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        crawled_at = CURRENT_TIMESTAMP,
                        is_processed = 0;
                    """,
                    rows,
                )
                conn.commit()
        return len(rows)

    def get_processed_ids(
        self, source: Optional[str] = None, strip_prefix: bool = True
    ) -> Set[str]:
        """Lấy danh sách ID đã cào để kiểm tra trùng lặp tức thì.

        Hỗ trợ cả ID gốc (ví dụ: '134968897') và ID đầy đủ ('nhatot_134968897').
        """
        query = "SELECT listing_id, source FROM raw_listings"
        params: List[Any] = []
        if source:
            query += " WHERE source = ?"
            params.append(source.lower())

        processed: Set[str] = set()
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            for row in cursor.fetchall():
                lid = row["listing_id"]
                src = row["source"]
                processed.add(lid)
                if strip_prefix and lid.startswith(f"{src}_"):
                    processed.add(lid[len(src) + 1 :])

        return processed

    def get_raw_listings(
        self,
        unprocessed_only: bool = False,
        source: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Lấy danh sách các bản ghi thô để nạp vào luồng ETL Transform."""
        clauses = []
        params: List[Any] = []

        if unprocessed_only:
            clauses.append("is_processed = 0")
        if source:
            clauses.append("source = ?")
            params.append(source.lower())

        query = "SELECT payload_json FROM raw_listings"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY crawled_at ASC"

        if limit is not None:
            query += f" LIMIT {int(limit)}"

        records: List[Dict[str, Any]] = []
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            for row in cursor.fetchall():
                try:
                    records.append(json.loads(row["payload_json"]))
                except Exception as e:
                    logger.warning(f"Lỗi parse payload JSON từ staging db: {e}")

        return records

    def mark_as_processed(self, listing_ids: Iterable[str]) -> int:
        """Đánh dấu các bản ghi đã được ETL và load thành công vào kho đích."""
        id_list = [str(lid) for lid in listing_ids if str(lid)]
        if not id_list:
            return 0

        # Chunk theo batch 500 ID để tránh giới hạn tham số câu lệnh SQL
        updated_count = 0
        chunk_size = 500
        with self._write_lock:
            with self._get_connection() as conn:
                for i in range(0, len(id_list), chunk_size):
                    chunk = id_list[i : i + chunk_size]
                    placeholders = ",".join("?" for _ in chunk)
                    cur = conn.execute(
                        f"UPDATE raw_listings SET is_processed = 1 WHERE listing_id IN ({placeholders})",
                        chunk,
                    )
                    updated_count += cur.rowcount
                conn.commit()

        return updated_count

    def count_summary(self) -> Dict[str, int]:
        """Thống kê tổng quan số lượng bản ghi trong Staging DB."""
        with self._get_connection() as conn:
            total = conn.execute("SELECT count(*) FROM raw_listings").fetchone()[0]
            processed = conn.execute(
                "SELECT count(*) FROM raw_listings WHERE is_processed = 1"
            ).fetchone()[0]
            unprocessed = conn.execute(
                "SELECT count(*) FROM raw_listings WHERE is_processed = 0"
            ).fetchone()[0]

        return {
            "total": total,
            "processed": processed,
            "unprocessed": unprocessed,
        }

    def sync_status_to_postgres(
        self,
        specific_ids: Optional[Iterable[str]] = None,
        batch_size: int = 500,
    ) -> Dict[str, int]:
        """Đồng bộ trạng thái is_active, status, last_checked_at từ staging.db sang PostgreSQL."""
        from datetime import datetime
        from sqlalchemy import text
        from crawler.etl.db_models import create_db_session

        records_to_sync: List[Dict[str, Any]] = []

        with self._get_connection() as conn:
            if specific_ids:
                id_list = list(specific_ids)
                for i in range(0, len(id_list), batch_size):
                    chunk = id_list[i : i + batch_size]
                    placeholders = ",".join("?" for _ in chunk)
                    cursor = conn.execute(
                        f"SELECT payload_json FROM raw_listings WHERE listing_id IN ({placeholders})",
                        chunk,
                    )
                    for row in cursor.fetchall():
                        try:
                            records_to_sync.append(json.loads(row["payload_json"]))
                        except Exception as e:
                            logger.warning(f"Lỗi parse JSON: {e}")
            else:
                cursor = conn.execute("SELECT payload_json FROM raw_listings")
                for row in cursor.fetchall():
                    try:
                        data = json.loads(row["payload_json"])
                        if "is_active" in data or "last_checked_at" in data or "status" in data:
                            records_to_sync.append(data)
                    except Exception as e:
                        logger.warning(f"Lỗi parse JSON: {e}")

        if not records_to_sync:
            logger.info("[FAST SYNC] Không có bản ghi nào cần đồng bộ trạng thái.")
            return {"total_synced": 0, "active": 0, "expired": 0}

        logger.info(f"[FAST SYNC] Bắt đầu đồng bộ trạng thái {len(records_to_sync)} tin sang PostgreSQL...")
        stats = {"total_synced": 0, "active": 0, "expired": 0}
        engine, session = create_db_session()

        update_stmt = text(
            """
            UPDATE listings 
            SET 
                is_active = :is_active,
                status = :status,
                last_checked_at = :last_checked_at
            WHERE id = :id;
            """
        )

        try:
            batch_params: List[Dict[str, Any]] = []
            for item in records_to_sync:
                src = str(item.get("source") or "nhatot").lower()
                sub_id = item.get("list_id") or item.get("ad_id") or item.get("id")
                lid = str(item.get("listing_id") or (f"{src}_{sub_id}" if sub_id else ""))
                if not lid:
                    continue

                is_act = bool(item.get("is_active", True))
                st = str(item.get("status") or ("active" if is_act else "expired_or_deleted")).lower()

                raw_checked = item.get("last_checked_at")
                checked_dt = None
                if raw_checked:
                    try:
                        checked_dt = datetime.fromisoformat(str(raw_checked).replace("Z", "+00:00"))
                    except Exception:
                        checked_dt = datetime.now()

                batch_params.append({
                    "id": lid,
                    "is_active": is_act,
                    "status": st,
                    "last_checked_at": checked_dt,
                })

                if is_act:
                    stats["active"] += 1
                else:
                    stats["expired"] += 1

                if len(batch_params) >= batch_size:
                    session.execute(update_stmt, batch_params)
                    session.commit()
                    stats["total_synced"] += len(batch_params)
                    batch_params.clear()

            if batch_params:
                session.execute(update_stmt, batch_params)
                session.commit()
                stats["total_synced"] += len(batch_params)
                batch_params.clear()

            logger.info(
                f"[FAST SYNC] Hoàn tất đồng bộ trạng thái: "
                f"{stats['total_synced']} tin (Còn sống: {stats['active']}, Hết hạn/Ẩn: {stats['expired']})."
            )
            return stats
        except Exception as e:
            session.rollback()
            logger.error(f"[FAST SYNC] Lỗi khi đồng bộ sang PostgreSQL: {e}")
            raise
        finally:
            session.close()


# Singleton dùng chung cho toàn bộ crawler module
staging_db = StagingDatabase()


def sync_status_to_postgres(specific_ids: Optional[Iterable[str]] = None, batch_size: int = 500) -> Dict[str, int]:
    """Hàm wrapper tiện lợi để gọi nhanh đồng bộ trạng thái sang PostgreSQL."""
    return staging_db.sync_status_to_postgres(specific_ids=specific_ids, batch_size=batch_size)
