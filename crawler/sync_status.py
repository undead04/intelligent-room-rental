"""Tiện ích đồng bộ nhanh trạng thái vòng đời tin đăng (is_active, status, last_checked_at)
từ SQLite Staging DB sang PostgreSQL Database.

Không tốn tài nguyên chạy lại mô hình Embedding hay LLM.
Có thể gọi trực tiếp từ crawler/main.py sau khi Verify hoặc chạy độc lập.
"""

import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Iterable

# Đảm bảo UTF-8 encoding cho console trên Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Đảm bảo root dự án có trong sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from sqlalchemy import text
from crawler.staging_db import StagingDatabase, staging_db
from crawler.etl.db_models import create_db_session

logger = logging.getLogger("sync_status")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def sync_status_to_postgres(
    staging_db_instance: Optional[StagingDatabase] = None,
    specific_ids: Optional[Iterable[str]] = None,
    batch_size: int = 500,
) -> Dict[str, int]:
    """Đồng bộ trạng thái is_active, status, last_checked_at từ staging.db sang PostgreSQL.

    Args:
        staging_db_instance: Đối tượng StagingDatabase (mặc định lấy staging_db).
        specific_ids: Tập ID cụ thể cần đồng bộ. Nếu None, đồng bộ các bản ghi có last_checked_at.
        batch_size: Kích thước lô cập nhật.

    Returns:
        Dict thống kê: {'total_synced': int, 'active': int, 'expired': int}
    """
    db = staging_db_instance or staging_db
    records_to_sync: List[Dict[str, Any]] = []

    with db._get_connection() as conn:
        if specific_ids:
            id_list = list(specific_ids)
            # Chunking query nếu danh sách ID quá lớn
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
            # Lấy tất cả các bản ghi trong staging db
            cursor = conn.execute("SELECT payload_json FROM raw_listings")
            for row in cursor.fetchall():
                try:
                    data = json.loads(row["payload_json"])
                    # Chỉ sync những tin có last_checked_at hoặc có cờ is_active rõ ràng
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


if __name__ == "__main__":
    sync_status_to_postgres()
