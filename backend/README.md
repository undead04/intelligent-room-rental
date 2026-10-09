# FastAPI Backend - Smart Housing Decision Support System

Backend service built with **FastAPI**, **Pydantic v2**, and **SQLAlchemy** for the Smart Housing Decision Support System.

## 📁 Directory Structure

```text
backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── health.py        # GET /api/v1/health
│   │       │   └── listings.py      # GET /api/v1/listings
│   │       └── router.py            # API v1 Central Router
│   ├── core/
│   │   ├── config.py                # Environment & App Settings (Pydantic BaseSettings)
│   │   └── database.py              # SQLAlchemy Database Setup
│   ├── models/                      # SQLAlchemy Database Models
│   ├── schemas/                     # Pydantic Request/Response Schemas
│   ├── services/                    # Business Logic / ML Integrations
│   └── main.py                      # FastAPI Application Entrypoint
├── .env.example                     # Environment Configuration Template
├── .env                             # Active Local Environment File
├── requirements.txt                 # Backend Python Dependencies
└── README.md                        # Documentation
```

## 🚀 Getting Started

### 1. Environment Setup

Ensure the virtual environment is created and dependencies are installed:

```bash
# From workspace root
pip install -r backend/requirements.txt
```

### PostgreSQL vector search setup

Embeddings use PostgreSQL's `pgvector` extension through the SQLAlchemy
`Vector` type. Install the extension once in the target database before
creating or migrating the tables:

```bash
psql "$DATABASE_URL" -f backend/sql/001_enable_pgvector.sql
```

The `listing_embeddings.vector` column intentionally uses an unbounded
`vector` type. This allows different embedding models to coexist; the
`dimension` column stores the expected length for each row. Validate the
vector length in the embedding service before persisting it. Add a
dimension-specific HNSW or IVFFlat index only after choosing the model and
dimension used for similarity search.

### Initialize the development database

1. Create a PostgreSQL database named `smart_housing_db` in PostgreSQL, pgAdmin,
   or with `createdb`.
2. Copy `backend/.env.example` to `backend/.env` and set the real PostgreSQL
   password. The database URL must include the database name, for example:

   ```env
   DATABASE_URL=postgresql://postgres:your_password@localhost:5432/smart_housing_db
   ```

3. Ensure the PostgreSQL server has the `vector` extension installed. The
   initialization script enables it in the selected database and creates all
   SQLAlchemy tables:

   ```powershell
   cd backend
   ..\.venv\Scripts\python.exe scripts\init_db.py
   ```

The script is intended for local development. It creates missing tables but
does not alter existing columns. Use a migration tool before applying schema
changes to a shared or production database.

### Load crawler data

After initializing the schema, load the bundled data:

```powershell
cd backend
..\.venv\Scripts\python.exe scripts\load_data.py
```

The default source is `backend/app/datas/datas.json`. The loader upserts
listings by `listing_id`, creates or updates the related users, cities,
districts, wards, and room types, and imports the vectors from
`listing_embeddings.npy` using `listing_embedding_mapping.parquet`.
To explicitly load the processed CSV or raw crawler JSON files:

```powershell
..\.venv\Scripts\python.exe scripts\load_data.py --source csv
..\.venv\Scripts\python.exe scripts\load_data.py --source json --data-dir ..\crawler\data
```

Use `--data-dir` when the crawler data is stored elsewhere.

### Backend layers and error responses

The API is organized into:

```text
controllers -> services -> repositories -> SQLAlchemy models
```

Controllers only declare HTTP routes and dependencies. Services contain
business rules and repositories contain database queries. Application errors
use `ErrorDTO`:

```json
{
  "success": false,
  "status": 404,
  "code": "NOT_FOUND",
  "message": "Listing with id 'missing-id' not found",
  "details": null,
  "request_id": "..."
}
```

Successful API responses use the same envelope style:

```json
{
  "success": true,
  "status": 200,
  "code": "OK",
  "message": "Request completed successfully",
  "data": []
}
```

The frontend API client unwraps `data` automatically, while direct API
consumers can use `status`, `code`, and `message` for response handling.

Every response includes `X-Request-ID`. The same ID is included in logs, so a
frontend error can be searched directly in the backend log.

Unknown routes also use the same error format instead of FastAPI's default
`{"detail":"Not Found"}` response:

```json
{
  "success": false,
  "status": 404,
  "code": "NOT_FOUND",
  "message": "Not Found",
  "details": null,
  "request_id": "..."
}
```

The listings API also provides `GET /api/v1/listings/total` for counting
matching listings without loading listing records. It accepts the listing
filters such as `city_id`, `district_id`, `ward_id`, `room_type_id`,
`min_price`, `max_price`, `min_area`, `max_area`, and `search`, and returns:

```json
{
  "total_listings": 9551
}
```

#### Vector Search API (`POST /api/v1/listings/vector-search`)

Thực hiện tìm kiếm ngữ nghĩa (Semantic Search) bằng PostgreSQL `pgvector`:

* **Request Body**:
  ```json
  {
    "vector": [0.012, -0.045, ...]
  }
  ```
* **Query Parameters**:
  * `limit` (int, default: 20): Số lượng kết quả tối đa
  * `similarity_threshold` (float 0.0 - 1.0): Ngưỡng tương đồng tối thiểu
  * `model_name` (string, optional): Tên mô hình embedding
  * `city_id`, `district_id`, `ward_id`, `room_type_id`, `min_price`, `max_price`: Bộ lọc metadata kết hợp (Hybrid Search)
* **Response**:
  ```json
  {
    "success": true,
    "data": [
      {
        "listing": { "id": "nhatot_123", "title": "Phòng trọ..." },
        "distance": 0.1824,
        "similarity_score": 0.8176
      }
    ]
  }
  ```

#### Batch Query By IDs (`POST /api/v1/listings/by-ids`)

Lấy thông tin danh sách tin đăng theo mảng ID và **giữ nguyên thứ tự** của mảng đầu vào:

* **Request Body**:
  ```json
  {
    "ids": ["nhatot_123", "nhatot_456"]
  }
  ```
* **Response**:
  ```json
  {
    "success": true,
    "data": [ { "id": "nhatot_123", ... }, { "id": "nhatot_456", ... } ]
  }
  ```

#### Market Price Statistics (`GET /api/v1/listings/price-stats`)

Thống kê phân tích giá phòng trọ theo thành phố/quận/phường trong thời gian thực:

* **Query Parameters**: `city_id` (bắt buộc), `district_id`, `room_type_id`.
* **Response Data**:
  ```json
  {
    "price_stats_general": {
      "total_listings": 9550,
      "average_price_vnd": 4500000.0,
      "price_fluctuation_month": 2.45,
      "area_hotspot": "Quận Gò Vấp",
      "hotspot_posting_growth_month": 15.3
    },
    "price_stats_by_area": [
      {
        "area_id": 1,
        "area": "Quận Gò Vấp",
        "total_listings": 1250,
        "fluctuation_month": 1.8,
        "average_price_vnd": 4200000.0,
        "minimum_price_vnd": 2000000.0,
        "maximum_price_vnd": 9000000.0
      }
    ]
  }
  ```

### 2. Running the Development Server

Navigate to the `backend` folder and run `uvicorn`:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Or from the root directory using python from `.venv`:

```bash
python -m uvicorn app.main:app --reload --port 8000 --app-dir backend
```

### 3. API Documentation

Once the server is running, visit:
- **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)
- **Listings API**: [http://localhost:8000/api/v1/listings?limit=10](http://localhost:8000/api/v1/listings?limit=10)
- **Vector Search API**: `POST http://localhost:8000/api/v1/listings/vector-search`
- **Price Stats API**: [http://localhost:8000/api/v1/listings/price-stats?city_id=1](http://localhost:8000/api/v1/listings/price-stats?city_id=1)
