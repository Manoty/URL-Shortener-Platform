# app/repositories/url_repository.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from typing import Optional
from datetime import datetime, timezone

from app.models.url import URL, ClickLog


class URLRepository:
    """
    Data Access Layer for URL and ClickLog records.
    
    Repositories have one job: talk to the database. No business logic,
    no HTTP concepts, no exception translation (except DB-specific ones
    like IntegrityError which we translate to None/raise at this layer).
    
    Why a class instead of standalone functions?
    - The session is injected once in __init__, not passed to every method
    - Easy to mock in tests: replace the whole repository with a fake
    - Consistent interface for the service layer
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, url: URL) -> URL:
        """
        Persist a new URL record.
        
        Returns the saved URL with DB-generated fields populated
        (id, created_at, etc).
        
        Raises IntegrityError if short_code is not unique — caller
        (the service layer) handles retry logic.
        """
        self.db.add(url)
        await self.db.flush()   # flush sends SQL to DB within the transaction
                                 # but doesn't commit — lets us get the ID back
                                 # without committing yet
        await self.db.refresh(url)  # Reload from DB to get server-set defaults
        return url

    async def get_by_short_code(self, short_code: str) -> Optional[URL]:
        """
        Fetch URL by short code. This is the hot path — called on every redirect.
        
        We use select() with execution options to avoid loading related objects
        (click_logs) unless explicitly requested.
        """
        result = await self.db.execute(
            select(URL).where(URL.short_code == short_code)
        )
        return result.scalar_one_or_none()

    async def get_by_short_code_with_recent_clicks(
        self,
        short_code: str,
        limit: int = 10
    ) -> Optional[URL]:
        """
        Fetch URL with its recent click logs for the stats endpoint.
        Uses a joined load to avoid N+1 queries.
        """
        from sqlalchemy.orm import selectinload

        result = await self.db.execute(
            select(URL)
            .where(URL.short_code == short_code)
            .options(
                selectinload(URL.click_logs)  # Eager load click_logs in one query
            )
        )
        return result.scalar_one_or_none()

    async def short_code_exists(self, short_code: str) -> bool:
        """
        Lightweight existence check — doesn't load the full row.
        Used during code generation collision detection.
        """
        result = await self.db.execute(
            select(URL.id).where(URL.short_code == short_code)
        )
        return result.scalar_one_or_none() is not None

    async def increment_click_count(self, url_id) -> None:
        """
        Increment click_count using a server-side UPDATE, not ORM read-modify-write.
        
        The naive approach:
            url.click_count += 1    # WRONG under concurrent requests!
        
        Why it's wrong: two concurrent requests both read click_count=5,
        both set it to 6, second write wins, and one click is lost.
        
        The correct approach: let the database do the increment atomically.
        This is safe even with 1000 concurrent requests.
        """
        await self.db.execute(
            update(URL)
            .where(URL.id == url_id)
            .values(click_count=URL.click_count + 1)
        )

    async def deactivate(self, short_code: str) -> bool:
        """
        Soft delete a URL by setting is_active=False.
        Returns True if found and deactivated, False if not found.
        """
        result = await self.db.execute(
            update(URL)
            .where(URL.short_code == short_code)
            .values(is_active=False)
            .returning(URL.id)  # Use RETURNING to know if a row was affected
        )
        return result.scalar_one_or_none() is not None

    async def log_click(
        self,
        url_id,
        ip_address: Optional[str],
        user_agent: Optional[str],
        referer: Optional[str],
    ) -> ClickLog:
        """
        Append a click event record.
        Called on every successful redirect.
        """
        log = ClickLog(
            url_id=url_id,
            ip_address=ip_address,
            user_agent=user_agent,
            referer=referer,
            clicked_at=datetime.now(timezone.utc),
        )
        self.db.add(log)
        await self.db.flush()
        return log