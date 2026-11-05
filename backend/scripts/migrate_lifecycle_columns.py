"""Database Migration Script: Thêm cột vòng đời tin đăng (Lifecycle Status) vào bảng listings.

Cột bổ sung:
- is_active: BOOLEAN NOT NULL DEFAULT TRUE
- status: VARCHAR(50) NOT NULL DEFAULT 'active'
- last_checked_at: TIMESTAMP WITH TIME ZONE NULL
Chỉ mục bổ sung:
- idx_listings_is_active
- idx_listings_active_composite (Partial Index WHERE is_active = TRUE)
"""

import sys
import io
from pathlib import Path

# Đảm bảo UTF-8 encoding cho stdout/stderr trên Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Thêm backend vào sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from app.core.database import engine


def run_migration():
    print("[MIGRATION] Bắt đầu kiểm tra và cập nhật cấu trúc bảng 'listings'...")

    ddl_statements = [
        """
        ALTER TABLE listings 
        ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
        """,
        """
        ALTER TABLE listings 
        ADD COLUMN IF NOT EXISTS status VARCHAR(50) NOT NULL DEFAULT 'active';
        """,
        """
        ALTER TABLE listings 
        ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMP WITH TIME ZONE NULL;
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_listings_is_active 
        ON listings (is_active);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_listings_active_composite 
        ON listings (region_id, district_id, room_type_id) 
        WHERE is_active = TRUE;
        """,
    ]

    with engine.begin() as conn:
        for stmt in ddl_statements:
            clean_stmt = stmt.strip()
            print(f"  -> Thực thi DDL: {clean_stmt.splitlines()[0]}...")
            conn.execute(text(clean_stmt))

    print("[MIGRATION] Hoàn tất migration thành công 100%!")


if __name__ == "__main__":
    run_migration()
