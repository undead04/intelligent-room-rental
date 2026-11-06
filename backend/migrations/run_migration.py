import sys
import time
from pathlib import Path

# Thêm thư mục backend vào sys.path để import cấu hình DB
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy import create_engine, text
from app.core.config import settings

def run_migration(rollback: bool = False):
    db_url = settings.sync_database_url
    print(f"[MIGRATION] Kết nối tới CSDL: {settings.POSTGRES_DB}@{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}")
    
    engine = create_engine(db_url, isolation_level="AUTOCOMMIT")

    with engine.connect() as conn:
        if rollback:
            print("[MIGRATION] Bắt đầu rollback (DROP INDEX)...")
            t0 = time.time()
            conn.execute(text("DROP INDEX IF EXISTS idx_listing_embeddings_vector_hnsw;"))
            conn.execute(text("DROP INDEX IF EXISTS idx_listings_fts_full;"))
            print(f"[MIGRATION] Hoàn thành rollback trong {time.time() - t0:.2f}s.")
            return

        print("[MIGRATION] Bắt đầu thực thi UP MIGRATION...")

        # 1. Tạm thời tăng maintenance_work_mem
        print("  1. Thiết lập maintenance_work_mem = '256MB'...")
        conn.execute(text("SET maintenance_work_mem = '256MB';"))

        # 2. Đảm bảo cột vector có kiểu vector(768)
        print("  2. Đồng bộ kiểu dữ liệu vector(768) cho bảng listing_embeddings...")
        conn.execute(text("ALTER TABLE listing_embeddings ALTER COLUMN vector TYPE vector(768);"))

        # 3. Tạo HNSW Index cho listing_embeddings
        print("  3. Đang tạo HNSW Index (idx_listing_embeddings_vector_hnsw)...")
        t_hnsw = time.time()
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_listing_embeddings_vector_hnsw 
            ON listing_embeddings 
            USING hnsw (vector vector_cosine_ops) 
            WITH (m = 16, ef_construction = 64);
        """))
        hnsw_duration = time.time() - t_hnsw
        print(f"     -> HNSW Index hoàn tất ({hnsw_duration:.2f}s)!")

        # 4. Tạo GIN Index cho listings FTS
        print("  4. Đang tạo GIN Index (idx_listings_fts_full)...")
        t_gin = time.time()
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_listings_fts_full 
            ON listings 
            USING gin (
                to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(address_raw, '') || ' ' || coalesce(description, ''))
            );
        """))
        gin_duration = time.time() - t_gin
        print(f"     -> GIN Index hoàn tất ({gin_duration:.2f}s)!")

        # 5. Kiểm chứng kết quả
        print("\n[MIGRATION] Kiểm tra thông tin các chỉ mục:")
        res = conn.execute(text("""
            SELECT 
                i.relname AS index_name,
                t.relname AS table_name,
                am.amname AS index_type,
                pg_size_pretty(pg_relation_size(i.oid)) AS index_size
            FROM pg_class i
            JOIN pg_index x ON i.oid = x.indexrelid
            JOIN pg_class t ON t.oid = x.indrelid
            JOIN pg_am am ON am.oid = i.relam
            WHERE i.relname IN ('idx_listing_embeddings_vector_hnsw', 'idx_listings_fts_full')
            ORDER BY i.relname;
        """)).fetchall()

        for row in res:
            print(f"  - Bảng: {row[1]} | Tên Index: {row[0]} | Kiểu: {row[2]} | Kích thước: {row[3]}")

        if len(res) == 2:
            print("\n[MIGRATION] >>> THÀNH CÔNG: Cả 2 index đều đã tồn tại và sẵn sàng hoạt động! <<<")
        else:
            print(f"\n[MIGRATION] CẢNH BÁO: Chỉ tìm thấy {len(res)}/2 index.")

if __name__ == "__main__":
    is_rollback = "--rollback" in sys.argv
    run_migration(rollback=is_rollback)
