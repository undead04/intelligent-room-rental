import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import configure_logging
from app.middleware import (
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    SQLInjectionMiddleware,
)
from app.schemas.response import ErrorDTO
from app.services.embedding import EmbeddingModel

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Gán trực tiếp vào app.state khi Server START
    app.state.embedding_model = EmbeddingModel(
        model_name=settings.EMBEDDING_MODEL_NAME,
        batch_size=settings.EMBEDDING_BATCH_SIZE,
    )

    yield

    # Cleanup khi Server STOP (nếu cần)
    if hasattr(app.state, "embedding_model"):
        del app.state.embedding_model


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# Exception Handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    detail = exc.detail
    message = detail if isinstance(detail, str) else "HTTP request failed"
    code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
    payload = ErrorDTO(
        status=exc.status_code,
        code=code,
        message=message,
        details=detail if not isinstance(detail, str) else None,
        request_id=request_id,
    )
    logger.warning(
        "HTTP error request_id=%s status=%s message=%s",
        request_id,
        exc.status_code,
        message,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=payload.model_dump(),
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.warning(
        "Application error request_id=%s code=%s message=%s",
        request_id,
        exc.code,
        exc.message,
    )
    payload = ErrorDTO(
        status=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=payload.model_dump(),
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    payload = ErrorDTO(
        status=422,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        details=exc.errors(),
        request_id=request_id,
    )
    logger.warning("Validation error request_id=%s details=%s", request_id, exc.errors())
    return JSONResponse(
        status_code=422,
        content=payload.model_dump(),
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request: Request, exc: SQLAlchemyError):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.exception("Database error request_id=%s", request_id)
    payload = ErrorDTO(
        status=500,
        code="DATABASE_ERROR",
        message="Database operation failed",
        request_id=request_id,
    )
    return JSONResponse(
        status_code=500,
        content=payload.model_dump(),
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.exception("Unhandled application error request_id=%s", request_id)
    payload = ErrorDTO(
        status=500,
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred",
        request_id=request_id,
    )
    return JSONResponse(
        status_code=500,
        content=payload.model_dump(),
        headers={"X-Request-ID": request_id},
    )


# Middlewares (thứ tự đăng ký theo cơ chế LIFO: middleware đăng ký sau cùng sẽ được gọi đầu tiên)
# 1. SQL Injection Middleware
app.add_middleware(
    SQLInjectionMiddleware,
    enabled=settings.SQL_INJECTION_CHECK_ENABLED,
)

# 2. Rate Limiting Middleware
app.add_middleware(
    RateLimitMiddleware,
    requests_per_minute=settings.RATE_LIMIT_PER_MINUTE,
    enabled=settings.RATE_LIMIT_ENABLED,
)

# 3. CORS Middleware
if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# 4. Request Logging & Request-ID Middleware (Nằm ngoài cùng, xử lý đầu tiên khi request tới)
app.add_middleware(RequestLoggingMiddleware)

# Routes
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
def root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "docs": "/docs",
        "health": f"{settings.API_V1_STR}/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
