# app/services/url_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from typing import Optional
from datetime import datetime

from app.models.url import URL
from app.repositories.url_repository import URLRepository
from app.schemas.url import URLCreateRequest, URLResponse, URLStatsResponse
from app.utils.shortcode import generate_short_code
from app.config import get_settings
from app.exceptions import (
    URLNotFoundException,
    URLExpiredException,
    URLInactiveException,
    CustomCodeConflictException,
    ShortCodeGenerationException,
)

settings = get_settings()


class URLService:
    """
    Business logic for URL shortening operations.
    
    The service layer:
    - Orchestrates between repositories
    - Enforces business rules (expiry, active status)
    - Handles retry logic (code collision)
    - Builds response objects
    - Knows nothing about HTTP (no Request/Response objects here)
    """

    def __init__(self, db: AsyncSession):
        self.repo = URLRepository(db)

    def _build_short_url(self, short_code: str) -> str:
        """Construct the full shortened URL from a short code."""
        base = settings.BASE_URL.rstrip("/")
        return f"{base}/{short_code}"

    def _build_url_response(self, url: URL) -> URLResponse:
        """Map ORM model -> URLResponse schema."""
        return URLResponse(
            id=str(url.id),
            original_url=str(url.original_url),
            short_code=url.short_code,
            short_url=self._build_short_url(url.short_code),
            is_custom_code=url.is_custom_code,
            click_count=url.click_count,
            is_active=url.is_active,
            expires_at=url.expires_at,
            created_at=url.created_at,
        )

    async def create_short_url(self, request: URLCreateRequest) -> URLResponse:
        """
        Core business logic: create a new shortened URL.
        
        Flow:
        1. If custom code requested → check availability → use it
        2. Otherwise → generate random code with collision retry
        3. Save to database
        4. Return response
        
        Collision handling strategy:
        We use a try/except on IntegrityError from the DB unique constraint.
        This is more reliable than "check then insert" because it eliminates
        the race condition between the check and the insert (TOCTOU bug).
        """
        original_url_str = str(request.original_url)

        if request.custom_code:
            # Custom code path — user specified the code they want
            exists = await self.repo.short_code_exists(request.custom_code)
            if exists:
                raise CustomCodeConflictException(request.custom_code)

            url = URL(
                original_url=original_url_str,
                short_code=request.custom_code,
                is_custom_code=True,
                expires_at=request.expires_at,
            )
            try:
                saved = await self.repo.create(url)
            except IntegrityError:
                # Another request beat us to it between check and insert
                raise CustomCodeConflictException(request.custom_code)

        else:
            # Auto-generation path — try up to MAX_RETRIES times
            max_retries = settings.SHORT_CODE_MAX_RETRIES
            saved = None

            for attempt in range(max_retries):
                code = generate_short_code(settings.SHORT_CODE_LENGTH)
                url = URL(
                    original_url=original_url_str,
                    short_code=code,
                    is_custom_code=False,
                    expires_at=request.expires_at,
                )
                try:
                    saved = await self.repo.create(url)
                    break  # Success — exit the retry loop
                except IntegrityError:
                    # Collision — the generated code already exists
                    # This is extremely rare (see shortcode.py for stats)
                    # but we handle it gracefully
                    continue

            if saved is None:
                raise ShortCodeGenerationException()

        return self._build_url_response(saved)

    async def get_redirect_url(
        self,
        short_code: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        referer: Optional[str] = None,
    ) -> str:
        """
        Resolve a short code to its original URL.
        
        Side effects (intentional):
        - Increments click_count atomically
        - Logs the click event
        
        These side effects happen synchronously here. For a higher-scale
        system you'd put click logging on a message queue (Celery/RQ)
        to keep redirect latency minimal. For our scale, synchronous is fine.
        
        Returns:
            The original URL string (used in HTTP redirect response)
            
        Raises:
            URLNotFoundException, URLExpiredException, URLInactiveException
        """
        url = await self.repo.get_by_short_code(short_code)

        if url is None:
            raise URLNotFoundException(short_code)
        if not url.is_active:
            raise URLInactiveException(short_code)
        if url.is_expired:
            raise URLExpiredException(short_code)

        # Record the visit — both operations happen in the same transaction
        await self.repo.increment_click_count(url.id)
        await self.repo.log_click(
            url_id=url.id,
            ip_address=ip_address,
            user_agent=user_agent,
            referer=referer,
        )

        return url.original_url

    async def get_url_stats(self, short_code: str) -> URLStatsResponse:
        """
        Return stats for a short URL including recent click history.
        """
        url = await self.repo.get_by_short_code_with_recent_clicks(short_code)

        if url is None:
            raise URLNotFoundException(short_code)

        # Sort click logs by most recent first, limit to 10
        recent = sorted(
            url.click_logs, key=lambda c: c.clicked_at, reverse=True
        )[:10]

        return URLStatsResponse(
            id=str(url.id),
            original_url=str(url.original_url),
            short_code=url.short_code,
            short_url=self._build_short_url(url.short_code),
            click_count=url.click_count,
            is_active=url.is_active,
            expires_at=url.expires_at,
            created_at=url.created_at,
            recent_clicks=[
                {"clicked_at": c.clicked_at, "referer": c.referer}
                for c in recent
            ]
        )

    async def delete_short_url(self, short_code: str) -> bool:
        """
        Soft-delete a URL. Returns True if found and deleted.
        Raises URLNotFoundException if the code doesn't exist.
        """
        deactivated = await self.repo.deactivate(short_code)
        if not deactivated:
            raise URLNotFoundException(short_code)
        return True