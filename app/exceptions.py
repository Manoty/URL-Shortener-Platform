# app/exceptions.py

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


# ── Domain Exceptions ─────────────────────────────────────────────────────────

class URLShortenerException(Exception):
    """Base exception for all app-specific errors."""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class URLNotFoundException(URLShortenerException):
    """Raised when a short_code doesn't exist in the database."""
    def __init__(self, short_code: str):
        super().__init__(
            message=f"Short URL '{short_code}' not found.",
            code="URL_NOT_FOUND"
        )
        self.short_code = short_code


class URLExpiredException(URLShortenerException):
    """Raised when a URL exists but has passed its expiration date."""
    def __init__(self, short_code: str):
        super().__init__(
            message=f"Short URL '{short_code}' has expired.",
            code="URL_EXPIRED"
        )


class URLInactiveException(URLShortenerException):
    """Raised when a URL has been deactivated (soft-deleted)."""
    def __init__(self, short_code: str):
        super().__init__(
            message=f"Short URL '{short_code}' is no longer active.",
            code="URL_INACTIVE"
        )


class CustomCodeConflictException(URLShortenerException):
    """Raised when a requested custom code is already taken."""
    def __init__(self, code: str):
        super().__init__(
            message=f"The custom code '{code}' is already in use.",
            code="CUSTOM_CODE_CONFLICT"
        )


class ShortCodeGenerationException(URLShortenerException):
    """Raised when we fail to generate a unique code after max retries."""
    def __init__(self):
        super().__init__(
            message="Failed to generate a unique short code. Please try again.",
            code="CODE_GENERATION_FAILED"
        )


# ── Exception Handlers (registered in main.py) ────────────────────────────────

async def url_not_found_handler(
    request: Request,
    exc: URLNotFoundException
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "error": exc.message,
            "code": exc.code,
            "detail": None,
        }
    )


async def url_expired_handler(
    request: Request,
    exc: URLExpiredException
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_410_GONE,  # 410 = resource permanently gone
        content={
            "error": exc.message,
            "code": exc.code,
            "detail": None,
        }
    )


async def url_inactive_handler(
    request: Request,
    exc: URLInactiveException
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_410_GONE,
        content={
            "error": exc.message,
            "code": exc.code,
            "detail": None,
        }
    )


async def custom_code_conflict_handler(
    request: Request,
    exc: CustomCodeConflictException
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": exc.message,
            "code": exc.code,
            "detail": None,
        }
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """
    Override FastAPI's default 422 handler to use our error envelope shape.
    This ensures ALL error responses look the same to API consumers.
    """
    errors = exc.errors()
    # Flatten Pydantic's nested error structure into something readable
    detail = "; ".join(
        f"{' -> '.join(str(loc) for loc in err['loc'])}: {err['msg']}"
        for err in errors
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation failed.",
            "code": "VALIDATION_ERROR",
            "detail": detail,
        }
    )


async def generic_exception_handler(
    request: Request,
    exc: Exception
) -> JSONResponse:
    """Catch-all — never let a raw traceback leak to the client."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "An unexpected error occurred.",
            "code": "INTERNAL_ERROR",
            "detail": None,
        }
    )