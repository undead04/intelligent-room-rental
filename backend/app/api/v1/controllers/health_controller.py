from fastapi import APIRouter

from app.core.config import settings
from app.schemas.health import HealthResponse
from app.schemas.response import ResponseDTO

router = APIRouter()


@router.get("/health", response_model=ResponseDTO[HealthResponse])
def check_health():
    return ResponseDTO[HealthResponse](
        data=HealthResponse(
            status="ok",
            project_name=settings.PROJECT_NAME,
            version=settings.VERSION,
            environment=settings.ENVIRONMENT,
        )
    )
