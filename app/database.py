# app/database.py

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.config import get_settings

settings = get_settings()

# ── Engine ────────────────────────────────────────────────────────────────────
# pool_pre_ping=True: before using a connection from the pool, send a
# lightweight "ping" to check if it's still alive. Without this, you'll
# get mysterious errors after a PostgreSQL restart or timeout.
#
# pool_size=10: number of persistent connections kept open.
# max_overflow=20: additional connections allowed beyond pool_size under load.
# These numbers suit a small/medium production app; tune based on DB server.
engine = create_async_engine(
    settings.async_database_url,
    echo=settings.DEBUG,       # Logs SQL in development — turn OFF in production
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# ── Session Factory ───────────────────────────────────────────────────────────
# async_sessionmaker is the async equivalent of sessionmaker.
# expire_on_commit=False: after a commit, don't expire all attributes.
# With async SQLAlchemy, accessing expired attributes triggers implicit I/O
# which can't happen outside an async context — this prevents subtle bugs.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)