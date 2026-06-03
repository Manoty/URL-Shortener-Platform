# app/main.py

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.exceptions import (
    URLNotFoundException,
    URLExpiredException,
    URLInactiveException,
    CustomCodeConflictException,
    url_not_found_handler,
    url_expired_handler,
    url_inactive_handler,
    custom_code_conflict_handler,
    validation_exception_handler,
    generic_exception_handler,
)
from app.routers import url_router

settings = get_settings()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler (replaces deprecated startup/shutdown events).
    
    Code before `yield` runs at startup.
    Code after `yield` runs at shutdown.
    
    This is where you'd:
    - Warm up connection pools
    - Initialize cache connections (Redis)
    - Start background task schedulers
    """
    logger.info(
        "application_starting",
        environment=settings.ENVIRONMENT,
        version=settings.APP_VERSION,
    )
    yield
    logger.info("application_shutdown")


def create_app() -> FastAPI:
    """
    Application factory pattern.
    
    Returning a factory function instead of a module-level app instance
    makes testing much cleaner — each test can create a fresh app
    with different settings if needed.
    """
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Production-grade URL shortener API",
        docs_url="/docs" if not settings.is_production else None,  # Hide docs in prod
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Middleware ────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not settings.is_production else ["https://yourdomain.com"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception Handlers ────────────────────────────────────────────────────
    # Order matters: more specific exceptions first
    app.add_exception_handler(URLNotFoundException, url_not_found_handler)
    app.add_exception_handler(URLExpiredException, url_expired_handler)
    app.add_exception_handler(URLInactiveException, url_inactive_handler)
    app.add_exception_handler(CustomCodeConflictException, custom_code_conflict_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(url_router.router)

    # ── Health Check ──────────────────────────────────────────────────────────
    @app.get("/health", tags=["System"])
    async def health_check():
        """
        Minimal health endpoint for load balancers and container orchestrators.
        Returns 200 if the app process is alive.
        For a deeper check (DB connectivity), you'd query the DB here.
        """
        return {"status": "ok", "version": settings.APP_VERSION}

    return app


# Module-level app instance — used by uvicorn
app = create_app()