from typing import Any, Optional


class AppException(Exception):
    status_code = 500
    code = "INTERNAL_SERVER_ERROR"

    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundException(AppException):
    status_code = 404
    code = "NOT_FOUND"


class BadRequestException(AppException):
    status_code = 400
    code = "BAD_REQUEST"
