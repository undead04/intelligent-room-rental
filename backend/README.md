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
