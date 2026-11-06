-- Migration: 001_add_hnsw_and_gin_indexes.sql
-- Description: Đánh chỉ mục HNSW (pgvector) cho Dense Cosine Search và GIN Index cho Full-Text Search (title, address_raw, description)

-- ========================================================
-- UP MIGRATION
-- ========================================================

-- Tạm thời tăng dung lượng bộ nhớ cho tác vụ bảo trì / đánh index trong phiên làm việc
SET maintenance_work_mem = '256MB';

-- 1. Đảm bảo cột vector có kích thước xác định (768 chiều) để pgvector hỗ trợ xây dựng HNSW index
ALTER TABLE listing_embeddings ALTER COLUMN vector TYPE vector(768);

-- 2. Chỉ mục HNSW cho Dense Search (vector 768 chiều cosine distance)
CREATE INDEX IF NOT EXISTS idx_listing_embeddings_vector_hnsw 
ON listing_embeddings 
USING hnsw (vector vector_cosine_ops) 
WITH (m = 16, ef_construction = 64);

-- 3. Chỉ mục GIN cho Sparse Search (Full-Text Search kết hợp title, address_raw, description)
CREATE INDEX IF NOT EXISTS idx_listings_fts_full 
ON listings 
USING gin (
    to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(address_raw, '') || ' ' || coalesce(description, ''))
);

-- ========================================================
-- DOWN MIGRATION (ROLLBACK)
-- ========================================================
-- DROP INDEX IF EXISTS idx_listing_embeddings_vector_hnsw;
-- DROP INDEX IF EXISTS idx_listings_fts_full;
