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
