from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ResponseDTO(BaseModel, Generic[T]):
    success: bool = True
    status: int = 200
    code: str = "OK"
    data: T
    message: str = "Request completed successfully"


class ErrorDTO(BaseModel):
    success: bool = False
    status: int
    code: str
    message: str
    details: Optional[Any] = None
    request_id: Optional[str] = None
