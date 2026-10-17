# ⚡ Backend Module — FastAPI Hybrid Search & MCDM Reranker (`backend/`)

Module **Backend (`backend/`)** cung cấp hệ thống RESTful API hiệu năng cao được xây dựng trên nền tảng **FastAPI**, **SQLAlchemy 2.0**, và **PostgreSQL (`pgvector` + Full-Text Search)** cho Hệ Thống Hỗ Trợ Ra Quyết Định Tìm Kiếm Phòng Trọ Thông Minh (**Homigo**).

---

## 📂 1. Cấu Trúc Thư Mục (Layered Architecture)

Backend tuân thủ nghiêm ngặt kiến trúc phân tầng **`Controllers -> Services -> Repositories -> ORM Models`**:

```text
backend/
├── app/
│   ├── api/v1/
│   │   ├── controllers/               # Định nghĩa HTTP Endpoints & Query/Body Validation
│   │   │   ├── listings_controller.py # /api/v1/listings (CRUD, Filter, Vector Search, Price Stats)
│   │   │   ├── locations_controller.py# /api/v1/locations (Cities, Districts, Wards)
│   │   │   ├── room_type_controller.py# /api/v1/room-types
│   │   │   ├── geocode.py             # /api/v1/geocode (Nominatim OSM Geocoding)
│   │   │   └── health_controller.py   # /api/v1/health
│   │   └── router.py                  # Router tổng hợp API v1
│   ├── core/
│   │   ├── config.py                  # Cấu hình biến môi trường (Pydantic Settings)
│   │   ├── database.py                # Quản lý kết nối SQLAlchemy Session
│   │   ├── exceptions.py              # Custom HTTP Exceptions & Global Error Handlers
│   │   └── security.py                # Middleware chống SQL Injection & Sliding-Window Rate Limit
│   ├── models/                        # SQLAlchemy ORM Models (Listing, ListingEmbedding, Location, RoomType, User)
│   ├── repositories/                  # Truy vấn CSDL & Hybrid Search (70% Dense pgvector + 30% Sparse FTS)
│   ├── schemas/                       # Pydantic v2 DTOs (ResponseDTO, ListingResponse, VectorSearchResult...)
│   ├── services/                      # Logic nghiệp vụ (ListingService, EmbeddingModel, GeocodeService)
│   ├── utils/
│   │   └── utils.py                   # Thuật toán MCDM Rerank 5 tiêu chí & Explainable AI (explain_match)
│   └── main.py                        # FastAPI App Entrypoint & Lifespan (nạp sẵn Vietnamese-SBERT)
├── scripts/
│   ├── init_db.py                     # Khởi tạo extension pgvector & toàn bộ bảng CSDL
│   └── load_data.py                   # Wrapper tương thích ngược gọi sang crawler.etl.load.DataLoader
├── tests/                             # Bộ Unit Tests (Embedding, MCDM Rerank, Security Middleware)
├── requirements.txt
└── run.py                             # Script khởi chạy nhanh Uvicorn server
```

---

## 🧠 2. Cơ Chế Tìm Kiếm Lai (Hybrid Search) & MCDM Reranking

### 2.1. Giai đoạn 1 — Candidate Generation (`listing_repository.py`)
1. **Lọc ràng buộc cứng (Hard Constraints)**: Lọc theo `city_id`, `district_id`, `ward_id`, `min_price`, `max_price`, `min_area`, `max_area`.
2. **Chấm điểm Hybrid Search**: Kết hợp độ tương đồng Cosine trên vector 768 chiều (`keepitreal/vietnamese-sbert`) và điểm khớp từ khóa PostgreSQL Full-Text Search để lấy Top 50 ứng viên tiềm năng nhất:
   $$\text{CandidateScore} = 0.70 \times \text{DenseScore} + 0.30 \times \text{SparseScore}$$

### 2.2. Giai đoạn 2 — 5-Factor Dynamic MCDM Reranking (`app/utils/utils.py`)
Top 50 ứng viên được xếp hạng lại theo 5 tiêu chí với trọng số thích ứng động ($\sum w_k = 1.0$):
- **`price`**: Điểm hợp lý giá `price_score` $\in [0.0, 1.0]$ từ mô hình ML Conformal Prediction.
- **`safety`**: Điểm an ninh `safety_score` $\in [0.0, 1.0]$ trích xuất từ bằng chứng thực tế trong mô tả.
- **`semantic`**: Độ tương đồng ngữ nghĩa `similarity_score` $\in [0.0, 1.0]$.
- **`location`** *(Động — bật khi có `lat`, `lng`)*: Độ gần địa lý tính bằng công thức Haversine ($\le 1\text{km} \rightarrow 1.0$, giảm tuyến tính đến $10\text{km} \rightarrow 0.0$).
- **`amenity`** *(Động — bật khi có yêu cầu `amenities`)*: Điểm khớp trung bình các tiện ích người dùng yêu cầu trên `concept_scores` (hỗ trợ chuẩn hóa cả mã tiếng Anh lẫn từ khóa tiếng Việt có dấu như `"máy lạnh" -> "aircon"`, `"gác lửng" -> "mezzanine"`).

Hàm `explain_match(breakdown)` xuất ra đóng góp của từng tiêu chí (`top_factors`, `weak_factors`) để **AI Agent** và **Frontend** giải thích minh bạch lý do đề xuất.

---

## 📡 3. Danh Sách Endpoints Chính

| Phương thức | Endpoint | Mô tả |
| :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Kiểm tra trạng thái hoạt động của Backend & Database |
| `GET` | `/api/v1/listings/` | Lấy danh sách tin đăng (hỗ trợ lọc địa lý, loại phòng, giá, diện tích, sắp xếp, phân trang) |
| `GET` | `/api/v1/listings/total` | Đếm tổng số lượng tin đăng khớp bộ lọc |
| `GET` | `/api/v1/listings/price-stats` | Thống kê giá trung bình, min/max, biến động theo tháng & khu vực sôi động (Hotspot) |
| `GET` | `/api/v1/listings/{list_id}` | Xem chi tiết tin đăng (`ListingDetailResponse` kèm `price_score`, `safety_score`, `concept_scores`) |
| `POST` | `/api/v1/listings/by-ids` | Lấy danh sách tin đăng theo mảng ID và bảo toàn thứ tự |
| `POST` | `/api/v1/listings/vector-search` | Tìm kiếm Hybrid Vector Search kết hợp MCDM Rerank & `explain_match` |
| `GET` | `/api/v1/locations/cities` | Danh sách Tỉnh/Thành phố |
| `GET` | `/api/v1/locations/districts` | Danh sách Quận/Huyện theo `city_id` |
| `GET` | `/api/v1/locations/wards` | Danh sách Phường/Xã theo `district_id` |
| `GET` | `/api/v1/room-types/` | Danh sách loại hình phòng trọ (`id`, `name`) |
| `GET` | `/api/v1/geocode` | Chuyển đổi tên địa điểm/trường học sang tọa độ (`lat`, `lon`) |

---

## 🚀 4. Hướng Dẫn Cài Đặt & Khởi Chạy

### 4.1. Cấu Hình Môi Trường & Nạp Dữ Liệu (từ Crawler ETL)
1. Cài đặt thư viện:
   ```powershell
   .\.venv\Scripts\pip.exe install -r backend/requirements.txt
   ```
2. Tạo file `backend/.env` từ `backend/.env.example`:
   ```env
   DATABASE_URL=postgresql://postgres:your_password@localhost:5432/smart_housing_db
   RATE_LIMIT_PER_MINUTE=120
   ```
3. Nạp dữ liệu vào PostgreSQL thông qua **Crawler ETL** (`crawler/etl/load.py` tự động tạo extension `pgvector`, khởi tạo bảng và nạp cả dữ liệu phòng lẫn vector 768 chiều):
   ```powershell
   # Cách 1: Nạp trực tiếp từ file JSON + Embeddings đã xử lý sẵn trong crawler/data/
   .\.venv\Scripts\python.exe -m crawler.etl.load

   # Cách 2: Chạy full luồng ETL (Extract -> Transform -> Embed -> Load vào DB)
   .\.venv\Scripts\python.exe -m crawler.etl.pipeline --dest db --embed --eval-price
   ```

### 4.2. Chạy Server Phát Triển
```powershell
.\.venv\Scripts\python.exe backend/run.py
```
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### 4.3. Chạy Kiểm Thử (Unit Tests)
```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -v
```
