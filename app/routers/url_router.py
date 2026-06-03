# app/routers/url_router.py

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.services.url_service import URLService
from app.schemas.url import (
    URLCreateRequest,
    URLResponse,
    URLStatsResponse,
    DeleteResponse,
)

router = APIRouter(tags=["URLs"])


def get_url_service(db: AsyncSession = Depends(get_db)) -> URLService:
    """
    Dependency that constructs the service with an injected DB session.
    Separating this makes it easy to override in tests.
    """
    return URLService(db)


@router.post(
    "/shorten",
    response_model=URLResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Shorten a URL",
    description="Creates a new shortened URL. Optionally accepts a custom short code and expiration date.",
)
async def shorten_url(
    body: URLCreateRequest,
    service: URLService = Depends(get_url_service),
) -> URLResponse:
    """
    POST /shorten
    
    Creates a short URL from a long URL.
    Returns 201 on success, 409 if custom code is taken, 422 on validation error.
    """
    return await service.create_short_url(body)


@router.get(
    "/stats/{short_code}",
    response_model=URLStatsResponse,
    summary="Get URL statistics",
    description="Returns click statistics and metadata for a given short code.",
)
async def get_stats(
    short_code: str,
    service: URLService = Depends(get_url_service),
) -> URLStatsResponse:
    """
    GET /stats/{short_code}
    
    IMPORTANT: This route must be registered BEFORE the /{short_code} redirect
    route. FastAPI matches routes in order — if /{short_code} is first, then
    /stats/abc would match it with short_code="stats/abc".
    
    Returns 200 with stats, 404 if not found.
    """
    return await service.get_url_stats(short_code)


@router.delete(
    "/{short_code}",
    response_model=DeleteResponse,
    summary="Delete a short URL",
    description="Soft-deletes a short URL, making it inactive.",
)
async def delete_url(
    short_code: str,
    service: URLService = Depends(get_url_service),
) -> DeleteResponse:
    """
    DELETE /{short_code}
    
    Soft-deletes the URL. Returns 200 on success, 404 if not found.
    """
    await service.delete_short_url(short_code)
    return DeleteResponse(
        message="Short URL has been deactivated.",
        short_code=short_code,
    )


@router.get(
    "/{short_code}",
    summary="Redirect to original URL",
    description="Resolves a short code and redirects to the original URL.",
    response_class=RedirectResponse,
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
)
async def redirect_to_url(
    short_code: str,
    request: Request,
    service: URLService = Depends(get_url_service),
) -> RedirectResponse:
    """
    GET /{short_code}
    
    The core redirect endpoint. Returns 307 redirect to original URL.
    
    Why 307 (Temporary Redirect) and not 301 (Permanent Redirect)?
    - 301 is cached by browsers permanently — if the destination ever
      changes or expires, users get a stale redirect with no way to fix it
    - 307 tells browsers not to cache — every click goes through our server
    - Trade-off: 307 is slightly slower (extra round-trip vs cached 301)
    - For a URL shortener where links can be updated/deleted: 307 is correct
    
    We extract IP and headers from the Request object here in the router
    (HTTP concerns), then pass raw strings to the service (no HTTP objects
    cross the service boundary).
    """
    # Extract client metadata for click logging
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    referer = request.headers.get("referer")

    # X-Forwarded-For: real IP when running behind a proxy/load balancer
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()

    original_url = await service.get_redirect_url(
        short_code=short_code,
        ip_address=ip_address,
        user_agent=user_agent,
        referer=referer,
    )

    return RedirectResponse(
        url=str(original_url),
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )