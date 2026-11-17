-- Migration: 002_add_unaccent_fts.sql
-- Description: Bật extension unaccent, tạo hàm IMMUTABLE f_unaccent(text) (xử lý cả đ/Đ)
--              và đánh chỉ mục GIN hỗ trợ Full-Text Search tiếng Việt không dấu.

-- ========================================================
-- UP MIGRATION
-- ========================================================

BEGIN;

-- 1. Kích hoạt extension unaccent của PostgreSQL
CREATE EXTENSION IF NOT EXISTS unaccent;

-- 2. Tạo hàm IMMUTABLE để PostgreSQL cho phép dùng trong Expression GIN Index
--    Xử lý chuẩn hóa cả 'đ'/'Đ' -> 'd'/'D' ngoài bảng unaccent mặc định
CREATE OR REPLACE FUNCTION public.f_unaccent(input_text text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
STRICT
AS $$
    SELECT translate(public.unaccent('public.unaccent', input_text), 'đĐ', 'dD');
$$;

-- 3. Đánh chỉ mục GIN hỗ trợ tìm kiếm không dấu trên (title, address_raw, description)
CREATE INDEX IF NOT EXISTS idx_listings_fts_unaccent
ON listings
USING gin (
    to_tsvector(
        'simple',
        public.f_unaccent(
            coalesce(title, '') || ' ' || coalesce(address_raw, '') || ' ' || coalesce(description, '')
        )
    )
);

COMMIT;

-- ========================================================
-- DOWN MIGRATION (ROLLBACK)
-- ========================================================
-- BEGIN;
-- DROP INDEX IF EXISTS idx_listings_fts_unaccent;
-- DROP FUNCTION IF EXISTS public.f_unaccent(text);
-- COMMIT;
