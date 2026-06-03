# tests/conftest.py

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from typing import AsyncGenerator

from app.main import create_app
from app.models.url import Base
from app.dependencies import get_db
from app.config import Settings, get_settings

# ── Test Database ─────────────────────────────────────────────────────────────
# Use a separate test database — never run tests against your dev/prod DB.
# SQLite in-memory is fast but has quirks with PostgreSQL-specific types (INET, UUID).
# For production-fidelity tests, use a real PostgreSQL instance.
# We use the DATABASE_URL from environment, but you can hardcode a test URL here.

TEST_DATABASE_URL = "postgresql+asyncpg://urlshortener:password@localhost:5432/urlshortener_test"


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Override settings for test environment."""
    return Settings(
        DATABASE_URL=TEST_DATABASE_URL.replace("+asyncpg", ""),
        ENVIRONMENT="testing",
        BASE_URL="http://testserver",
        SHORT_CODE_LENGTH=7,
    )


@pytest_asyncio.fixture(scope="session")
async def test_engine(test_settings):
    """
    Create test DB engine and tables once per test session.
    Drops all tables after the session completes (clean slate for next run).
    """
    engine = create_async_engine(
        test_settings.async_database_url,
        echo=False,
        poolclass=None,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)   # Clean slate
        await conn.run_sync(Base.metadata.create_all) # Create all tables

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)   # Cleanup after session
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a clean database session per test function.
    
    The trick: wrap everything in a SAVEPOINT (nested transaction).
    After each test, roll back to the savepoint — this undoes all
    inserts/updates from that test without dropping/recreating tables.
    
    This makes each test isolated and fast.
    """
    async with test_engine.connect() as connection:
        await connection.begin()  # Outer transaction
        async with async_sessionmaker(
            bind=connection,
            class_=AsyncSession,
            expire_on_commit=False,
        )() as session:
            await session.begin_nested()  # SAVEPOINT
            yield session
            await session.rollback()  # Roll back to savepoint


@pytest_asyncio.fixture(scope="function")
async def client(db_session, test_settings) -> AsyncGenerator[AsyncClient, None]:
    """
    HTTP test client with DB and settings overridden.
    
    We override the get_db dependency so API routes use
    our test session (which gets rolled back after each test).
    We also override get_settings so the app uses test config.
    """
    app = create_app()

    # Dependency override: replace get_db with one that uses our test session
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: test_settings

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver"
    ) as ac:
        yield ac