ACK-CODE: sr-7f3a
# API reference

Base URL: `http://localhost:8000/api/v1` (đổi bằng biến môi trường `SEARCH_ROOM_API_BASE`).

Mọi response được bọc trong `ResponseDTO`; các script tự bóc lớp này và chỉ trả về phần `data`:

```json
{ "success": true, "status": 200, "code": "OK", "data": { }, "message": "..." }
```

## 1. GET /geocode

Đổi địa chỉ/địa danh thành toạ độ.

| Query Param | Bắt buộc | Mô tả |
|-------------|----------|-------|
| `q` | có | Địa chỉ/địa danh (2-200 ký tự) |
| `hint` | không | Tỉnh/thành để thu hẹp khi tên bị trùng |

Response `data`: `{ "query": string, "lat": number, "lon": number, "formatted_address"?: string, "provider"?: string }`. Không tìm thấy → HTTP 404.

Script: `scripts/geocode.py --q "..." [--hint "..."]`

---

## 2. GET /locations/cities

Danh sách thành phố.

| Query Param | Bắt buộc | Mô tả |
|-------------|----------|-------|
| `search` | không | Tên thành phố để lọc (gửi lên API) |

Response `data`: mảng `[{ "id": int, "name": string, ... }, ...]`

Script: `scripts/cities.py [--name <tên>]`

---

## 3. GET /locations/districts

Danh sách quận/huyện.

| Query Param | Bắt buộc | Mô tả |
|-------------|----------|-------|
| `city_id` | không | ID thành phố để lọc |
| `search` | không | Tên quận/huyện để lọc (gửi lên API nếu có `city_id`) |

Response `data`: mảng `[{ "id": int, "city_id": int, "name": string, ... }, ...]`

Script: `scripts/districts.py [--city-id <id>] [--name <tên>]`

---

## 4. GET /locations/wards

Danh sách phường/xã.

| Query Param | Bắt buộc | Mô tả |
|-------------|----------|-------|
| `district_id` | không | ID quận/huyện để lọc |
| `search` | không | Tên phường/xã để lọc (gửi lên API nếu có `district_id`) |

Response `data`: mảng `[{ "id": int, "district_id": int, "name": string, ... }, ...]`

Script: `scripts/wards.py [--district-id <id>] [--name <tên>]`

---

## 5. POST /listings/vector-search

Tìm phòng trọ bằng vector search.

### Query Parameters

| Param | Mặc định | Mô tả |
|-------|----------|-------|
| `limit` | 10 | Số lượng kết quả |
| `offset` | 0 | Phân trang |
| `city_id` | - | Lọc theo thành phố |
| `district_id` | - | Lọc theo quận/huyện |
| `ward_id` | - | Lọc theo phường/xã |
| `min_price` | - | Giá tối thiểu (VND) |
| `max_price` | - | Giá tối đa (VND) |
| `min_area` | - | Diện tích tối thiểu (m²) |
| `max_area` | - | Diện tích tối đa (m²) |
| `lat` | - | Vĩ độ trung tâm tìm kiếm |
| `lng` | - | Kinh độ trung tâm tìm kiếm |

### Request Body (JSON)

| Field | Bắt buộc | Mô tả |
|-------|----------|-------|
| `query` | có | Mô tả nhu cầu bằng ngôn ngữ tự nhiên |
| `amenities` | không | Mảng tên tiện ích (VD: `["wifi", "parking"]`) |

Script gửi body chỉ gồm các field có giá trị. Dùng `--extra-json` để gộp thêm field bất kỳ, hoặc `--body-file` để tự cung cấp toàn bộ body.

Response `data`: mảng listing (mặc định script lược bỏ field chứa `embedding`/`vector`; thêm `--keep-vectors` để giữ).

Script: `scripts/vector_search.py --query "..." [--amenities wifi --amenities parking] [filters] [--limit 10] [--offset 0] [--extra-json '{}'] [--body-file file.json] [--keep-vectors] [--dry-run]`

---

## Mã thoát và lỗi

Mọi script in JSON ra stdout. Thành công có `"ok": true`; thất bại có `"ok": false` kèm `error` và `detail`, mã thoát 1.

| Tình huống | Hướng xử lý |
|------------|-------------|
| Không kết nối được | Báo người dùng backend chưa chạy |
| 404 từ geocode | Viết địa chỉ đầy đủ hơn hoặc hỏi lại người dùng |
| 422 từ vector-search | Sai tên field body/query param, kiểm tra tham số truyền vào |