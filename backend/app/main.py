import logging
import uuid

from fastapi import FastAPI
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import configure_logging
from app.api.v1.router import api_router
from app.schemas.response import ErrorDTO

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)


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


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled request error request_id=%s path=%s", request_id, request.url.path)
        raise
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_id=%s method=%s path=%s status=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
    )
    return response


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    logger.warning(
        "Application error request_id=%s code=%s message=%s",
        request.state.request_id,
        exc.code,
        exc.message,
    )
    payload = ErrorDTO(
        status=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        request_id=request.state.request_id,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=payload.model_dump(),
        headers={"X-Request-ID": request.state.request_id},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    payload = ErrorDTO(
        status=422,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        details=exc.errors(),
        request_id=request.state.request_id,
    )
    logger.warning("Validation error request_id=%s details=%s", request.state.request_id, exc.errors())
    return JSONResponse(status_code=422, content=payload.model_dump(), headers={"X-Request-ID": request.state.request_id})


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("Database error request_id=%s", request.state.request_id)
    payload = ErrorDTO(
        status=500,
        code="DATABASE_ERROR",
        message="Database operation failed",
        request_id=request.state.request_id,
    )
    return JSONResponse(status_code=500, content=payload.model_dump(), headers={"X-Request-ID": request.state.request_id})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled application error request_id=%s", request.state.request_id)
    payload = ErrorDTO(
        status=500,
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred",
        request_id=request.state.request_id,
    )
    return JSONResponse(status_code=500, content=payload.model_dump(), headers={"X-Request-ID": request.state.request_id})

# CORS middleware
if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
def root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "docs": "/docs",
        "health": f"{settings.API_V1_STR}/health"
    }
