# 📋 Đặc Tả Kỹ Thuật (Feature Spec): Đồng Bộ Trạng Thái Vòng Đời Tin Đăng (Listing Lifecycle & Expired Status) Giữa SQLite Staging & PostgreSQL

- **Mã tính năng (Feature ID):** `FEAT-LISTING-LIFECYCLE-SYNC`
- **Trạng thái:** ✅ COMPLETED (Đã hoàn thành và kiểm thử 100%)
- **Ngày tạo:** 05/11/2026
- **Tác giả:** Homigo AI Solution Architect

---

## 1. 🎯 Tổng Quan & Động Lực (Overview & Motivation)

### 1.1. Hiện trạng vấn đề
1. **Đứt gãy chuỗi đồng bộ giữa Crawler và Production Database:**
   - Khi chạy chế độ kiểm tra tin cũ (`python crawler/main.py --mode verify`), Spider đã phát hiện tin bị gỡ/hết hạn trên trang gốc (HTTP 404, status $\neq$ `active`) và cập nhật `is_active = False`, `status = "expired_or_deleted"` vào SQLite Staging Database (`crawler/data/staging.db`).
   - Tuy nhiên, bảng `listings` trong cơ sở dữ liệu chính PostgreSQL trước đây **hoàn toàn chưa có cột `is_active`, `status` và `last_checked_at`**.
   - Dẫn đến tin đã chết trên web gốc vẫn tồn tại vĩnh viễn trên hệ thống và người dùng vẫn tìm thấy.
2. **Trải nghiệm tìm kiếm bị loãng bởi tin rác / tin ảo:**
   - Hệ thống Hybrid Search (Dense vector + FTS), bộ lọc tìm kiếm và truy vấn các khu vực lân cận (`LocationRepository.nearby_locations()`) vẫn trả về các tin phòng trọ đã cho thuê xong hoặc đã bị chủ nhà gỡ bài.
3. **Mất dấu lịch sử nếu xóa cứng (Hard Delete):**
   - Nếu xóa cứng bài đăng khỏi PostgreSQL, các liên kết chia sẻ cũ hoặc người dùng đã lưu ID/bookmark bài viết sẽ gặp lỗi `404 Not Found`. Thay vào đó, cần cho phép người dùng **vẫn truy cập được bằng ID** nhưng giao diện chi tiết phải có thông báo rõ ràng là **tin đăng này đã hết hạn / phòng đã được thuê**.

### 1.2. Mục tiêu kỹ thuật
1. **Migration PostgreSQL Database:** Bổ sung các cột trạng thái (`is_active`, `status`, `last_checked_at`) vào bảng `listings` với chỉ mục tối ưu.
2. **Tự động đồng bộ hóa SQLite $\rightarrow$ PostgreSQL:** Tự động đồng bộ ngay khi kết thúc lệnh spider verify (`--mode verify`).
3. **Cập nhật tầng Backend:** Tự động lọc bỏ các tin `is_active = False` khỏi kết quả tìm kiếm và bảng thống kê; cho phép xem chi tiết theo ID kèm thông báo hết hạn.
4. **Cập nhật tầng Frontend:** Hiển thị Banner cảnh báo nổi bật màu cam/đỏ trên trang `/phong-tro/[id]` đối với tin đã hết hạn, vô hiệu hóa liên hệ.

---

## 2. 🗄 Thiết Kế Cơ Sở Dữ Liệu & Database Migration

### 2.1. Cấu trúc bảng `listings` (PostgreSQL)
Bổ sung 3 trường mới vào bảng `listings`:

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Giá Trị Mặc Định | Mục Đích |
| :--- | :--- | :--- | :--- | :--- |
| `is_active` | `BOOLEAN` | `NOT NULL` | `TRUE` | Cờ nhanh xác định tin còn mở hay đã hết hạn/gỡ |
| `status` | `VARCHAR(50)` | `NOT NULL` | `'active'` | Trạng thái chi tiết: `active`, `expired_or_deleted`, `pending` |
| `last_checked_at`| `TIMESTAMP WITH TIME ZONE` | `NULLABLE` | `NULL` | Thời điểm gần nhất spider kiểm tra tính khả dụng |

### 2.2. Kịch bản SQL Migration (An toàn & Zero-Downtime)

```sql
-- 1. Thêm các cột mới với giá trị mặc định an toàn cho dữ liệu sẵn có
ALTER TABLE listings 
ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS status VARCHAR(50) NOT NULL DEFAULT 'active',
ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMP WITH TIME ZONE NULL;

-- 2. Tạo Partial Index để tối ưu hóa cực đại tốc độ Hybrid Search và Bộ Lọc
CREATE INDEX IF NOT EXISTS idx_listings_is_active 
ON listings (is_active);

CREATE INDEX IF NOT EXISTS idx_listings_active_composite 
ON listings (region_id, district_id, room_type_id) 
WHERE is_active = TRUE;
```

---

## 3. 🔄 Quy Trình Tự Động Đồng Bộ Dữ Liệu (SQLite Staging $\rightarrow$ PostgreSQL)

```mermaid
flowchart TD
    A["Spider Chạy Chế Độ Verify<br/>(crawler/spiders/nhatot.py)"] -->|Kiểm tra HTTP 404 / inactive| B["SQLite staging.db<br/>raw_listings table"]
    B -->|Cập nhật payload_json<br/>is_active=False, status='expired_or_deleted'| B
    
    subgraph Tự Động Đồng Bộ Ngay Trong Lệnh Verify
        B -->|staging_db.sync_status_to_postgres()| C[("PostgreSQL Database<br/>Bảng listings")]
    end

    C -->|Loại trừ is_active = False| D["Backend Search / Vector Search / Nearby Locations"]
    C -->|Cho phép xem + Kèm cảnh báo| E["Backend Detail API<br/>GET /listings/{id}"]
    E --> F["Frontend UI Trang Chi Tiết<br/>(/phong-tro/[id])"]
```

---

## 4. ⚙️ Đặc Tả Cập Nhật Backend API (`backend/`)

### 4.1. Cập nhật Data Transfer Objects (Pydantic Schemas)
- `ListingResponse`: Thêm `is_active: bool = True`, `status: str = "active"`, `last_checked_at: Optional[datetime] = None`.
- `ListingDetailResponse`: Thêm `is_expired: bool = False`, `status_notice: Optional[str] = None`.
- Validator tự động sinh thông báo khi tin không còn active.

### 4.2. Cập nhật Repositories
1. **`ListingRepository`:**
   - `filtered_query()`: Thêm `Listing.is_active == True`.
   - `vector_search()`: Thêm `Listing.is_active == True`.
   - `price_aggregates()`: Thêm `Listing.is_active == True`.
2. **`LocationRepository` (`nearby_locations`):**
   - Thêm `Listing.is_active == True` vào cả query cấp Phường (`_build_wq`), cấp Quận (`_build_dq`), và tính tọa độ trung bình `avg(Listing.lat), avg(Listing.lng)`.

---

## 5. 🖥 Giao Diện Người Dùng (Frontend UI/UX)

* **File:** `frontend/src/app/phong-tro/[id]/page.tsx`
* **Xử lý hiển thị:**
  - Nếu `listing.is_expired || listing.is_active === false`:
    - Hiển thị Banner cảnh báo:
      > ⚠️ **Tin đăng này đã hết hạn hoặc đã ngừng cho thuê**  
      > *Bài đăng này đã hết hạn hoặc được người cho thuê gỡ bài trên nguồn gốc. Các thông tin dưới đây chỉ mang tính chất tham khảo lưu trữ.*
    - Gắn nhãn badge `[ĐÃ HẾT HẠN]` ngay cạnh tiêu đề phòng trong `ListingPriceHeader`.
    - Hiển thị thông báo `Phòng đã ngừng giao dịch` trong `LandlordCard`.

---

## 6. 🏆 Danh Sách Các Mốc Triển Khai (Milestones)

> Tuân thủ nghiêm ngặt 3 quy tắc: **Working Software** (chạy được thực tế) — **One Session Scope** (tối đa 4-6 files) — **Tiêu chí nghiệm thu rõ ràng**.

### [x] Mốc 1: Database Migration & Đồng Bộ ORM Models (PostgreSQL)
* **Mục tiêu:** Cập nhật schema database PostgreSQL an toàn với dữ liệu cũ và đồng bộ models SQLAlchemy ở cả Backend và Crawler.
* **Các file chính tạo/sửa:**
  1. `backend/app/models/listing.py` (Bổ sung columns SQLAlchemy)
  2. `crawler/etl/db_models.py` (Đồng bộ columns SQLAlchemy trong crawler)
* **Cách kiểm chứng:**
  - Chạy inspect DB bằng SQLAlchemy: `cols = inspect(engine).get_columns('listings')` thấy đủ 3 cột `is_active`, `status`, `last_checked_at`.

### [x] Mốc 2: Cơ Chế Tự Động Đồng Bộ Crawler (SQLite $\rightarrow$ PostgreSQL)
* **Mục tiêu:** Tự động đồng bộ trạng thái tin hết hạn từ SQLite sang PostgreSQL ngay khi chạy xong lệnh verify, không cần cron job riêng.
* **Các file chính tạo/sửa:**
  1. `crawler/etl/transform.py` (Giữ nguyên `last_checked_at`, `is_active`, `status`)
  2. `crawler/etl/load.py` (UPSERT các trường mới vào PostgreSQL)
  3. `crawler/staging_db.py` (Bổ sung phương thức `sync_status_to_postgres` bulk update)
  4. `crawler/main.py` (Tự động kích hoạt sync ở cuối `--mode verify`)
* **Cách kiểm chứng:**
  - Chạy `pytest crawler/tests -q` pass 30/30 tests.
  - Chạy sync thử nghiệm 10.430 tin hoàn thành trong 3 giây.

### [x] Mốc 3: Cập Nhật Backend Search, Nearby & Detail API Notice
* **Mục tiêu:** Ẩn toàn bộ tin hết hạn khỏi kết quả Search/Vector Search/Nearby, nhưng giữ nguyên khả năng truy cập theo ID kèm gắn cờ `is_expired` và `status_notice`.
* **Các file chính tạo/sửa:**
  1. `backend/app/schemas/listing.py` (Bổ sung fields DTO & validator)
  2. `backend/app/repositories/listing_repository.py` (Lọc `is_active == True` trong `filtered_query` và `vector_search`)
  3. `backend/app/repositories/location_repository.py` (Lọc `is_active == True` trong `nearby_locations`)
  4. `backend/app/services/listing_service.py` (Lọc `is_active == True` trong `get_price_stats`)
  5. `backend/tests/test_listing_lifecycle.py` (Bộ test kiểm thử 7 cases)
* **Cách kiểm chứng:**
  - Chạy `pytest backend/tests/test_listing_lifecycle.py -v` pass 7/7 tests.
  - Chạy `pytest backend/tests -q` pass 24/24 tests.

### [x] Mốc 4: Giao Diện Frontend Hiển Thị Tin Đăng Hết Hạn
* **Mục tiêu:** Hiển thị Banner cảnh báo màu vàng cam, badge `[Đã hết hạn]` và thông báo ngừng giao dịch trong thẻ chủ nhà khi xem tin hết hạn.
* **Các file chính tạo/sửa:**
  1. `frontend/src/types/dto/listing.ts` (Đồng bộ type `ListingDto` & `ListingDetailDto`)
  2. `frontend/src/app/phong-tro/[id]/page.tsx` (Banner cảnh báo đầu trang)
  3. `frontend/src/app/phong-tro/[id]/_components/ListingPriceHeader.tsx` (Badge `[Đã hết hạn]`)
  4. `frontend/src/app/phong-tro/[id]/_components/LandlordCard.tsx` (Khối cảnh báo ngừng giao dịch)
* **Cách kiểm chứng:**
  - Chạy `npx tsc --noEmit` và `npm run lint` pass 0 errors.
  - Truy cập `http://localhost:3000/phong-tro/demo_expired_room` hiển thị đầy đủ Banner, Badge và cảnh báo ngừng giao dịch.

---

## 7. 📌 Checklist Theo Dõi Tiến Độ Chi Tiết (Progress Tracking Checklist)

Bảng checklist dưới đây theo dõi trạng thái hoàn thành thực tế của từng đầu việc trong dự án:

### A. Tầng Cơ Sở Dữ Liệu (PostgreSQL Migration)
- [x] Thêm cột `is_active` (`BOOLEAN NOT NULL DEFAULT TRUE`) vào bảng `listings`.
- [x] Thêm cột `status` (`VARCHAR(50) NOT NULL DEFAULT 'active'`) vào bảng `listings`.
- [x] Thêm cột `last_checked_at` (`TIMESTAMP WITH TIME ZONE NULL`) vào bảng `listings`.
- [x] Tạo Partial Index `idx_listings_is_active` và `idx_listings_active_composite`.
- [x] Cập nhật model SQLAlchemy `Listing` trong [`backend/app/models/listing.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/models/listing.py).
- [x] Đồng bộ model SQLAlchemy `Listing` trong [`crawler/etl/db_models.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/crawler/etl/db_models.py).

### B. Tầng Crawler & ETL Pipeline
- [x] Cập nhật [`crawler/etl/transform.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/crawler/etl/transform.py) giữ nguyên `is_active`, `status`, `last_checked_at`.
- [x] Cập nhật [`crawler/etl/load.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/crawler/etl/load.py) UPSERT các trường trạng thái vào PostgreSQL.
- [x] Thêm hàm `sync_status_to_postgres()` vào [`crawler/staging_db.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/crawler/staging_db.py) thực hiện bulk update siêu tốc.
- [x] Tích hợp tự động sync vào lệnh `python crawler/main.py --mode verify` trong [`crawler/main.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/crawler/main.py).
- [x] Chạy kiểm thử bộ crawler tests pass 30/30 bài test.

### C. Tầng Backend Core API
- [x] Cập nhật [`backend/app/schemas/listing.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/schemas/listing.py) (`ListingResponse` và `ListingDetailResponse`).
- [x] Bổ sung điều kiện `Listing.is_active == True` vào `filtered_query()` trong [`backend/app/repositories/listing_repository.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/repositories/listing_repository.py).
- [x] Bổ sung điều kiện `Listing.is_active == True` vào `vector_search()` trong [`backend/app/repositories/listing_repository.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/repositories/listing_repository.py).
- [x] Bổ sung điều kiện `Listing.is_active == True` vào `nearby_locations()` trong [`backend/app/repositories/location_repository.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/repositories/location_repository.py).
- [x] Bổ sung điều kiện `Listing.is_active == True` vào `get_price_stats()` trong [`backend/app/services/listing_service.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/services/listing_service.py).
- [x] Bảo toàn khả năng xem chi tiết theo ID trong `get_by_id()` không bị chặn.
- [x] Viết bộ kiểm thử [`backend/tests/test_listing_lifecycle.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/tests/test_listing_lifecycle.py) pass 7/7 tests.
- [x] Chạy toàn bộ backend tests pass 24/24 bài test.

### D. Tầng Frontend UI/UX
- [x] Cập nhật type-safe DTOs trong [`frontend/src/types/dto/listing.ts`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/frontend/src/types/dto/listing.ts).
- [x] Thêm Banner cảnh báo màu vàng cam ở đầu trang chi tiết trong [`frontend/src/app/phong-tro/[id]/page.tsx`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/frontend/src/app/phong-tro/[id]/page.tsx).
- [x] Thêm badge `[Đã hết hạn]` trong [`frontend/src/app/phong-tro/[id]/_components/ListingPriceHeader.tsx`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/frontend/src/app/phong-tro/[id]/_components/ListingPriceHeader.tsx).
- [x] Thêm khối thông báo `Phòng đã ngừng giao dịch` trong [`frontend/src/app/phong-tro/[id]/_components/LandlordCard.tsx`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/frontend/src/app/phong-tro/[id]/_components/LandlordCard.tsx).
- [x] Kiểm tra linting và TypeScript: `tsc --noEmit` và `npm run lint` pass 0 errors.

### E. Kiểm Thử Tích Hợp & Đóng Gói (Verification)
- [x] Khởi chạy Backend và Frontend, kiểm tra trực quan giao diện tin hết hạn thành công.
- [x] Chụp ảnh màn hình lưu trữ xác thực giao diện thực tế.
- [x] Xóa sạch các script tạm (`migrate_lifecycle_columns.py`, `sync_status.py`) và thư mục `docsl/`.
- [x] Push toàn bộ commit lên GitHub an toàn.
