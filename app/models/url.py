# app/models/url.py

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Boolean, Integer,
    DateTime, ForeignKey, Index, text
)
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """
    Base class for all ORM models.
    All models inherit from this — it gives SQLAlchemy the metadata
    registry it needs to track tables and generate migrations.
    """
    pass


class URL(Base):
    """
    Core table: one row per shortened URL.
    
    Design decisions:
    - UUID primary key: prevents enumeration attacks (attacker can't
      guess id=1, id=2 to scrape all links)
    - short_code indexed unique: this is read on EVERY redirect, 
      so it must be as fast as possible
    - click_count is denormalized (we could compute COUNT from 
      click_logs, but that's slow at scale — we maintain both)
    - is_active for soft deletes: hard deleting URLs breaks any 
      browser history or bookmarks pointing to them
    """
    __tablename__ = "urls"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    original_url = Column(Text, nullable=False)
    short_code = Column(String(20), nullable=False, unique=True, index=True)
    is_custom_code = Column(Boolean, default=False, nullable=False)
    click_count = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # expires_at=NULL means "never expires" — explicit NULL is clearer
    # than a magic date like year 9999
    expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,  # Indexed: cleanup jobs query WHERE expires_at < NOW()
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),  # DB sets this, not application
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),  # Auto-updated by SQLAlchemy on every UPDATE
        nullable=False,
    )

    # Relationship: one URL -> many click logs
    click_logs = relationship(
        "ClickLog",
        back_populates="url",
        cascade="all, delete-orphan",  # Deleting a URL deletes its logs
        lazy="select",  # Don't auto-load logs when fetching URL (N+1 risk)
    )

    def __repr__(self) -> str:
        return f"<URL id={self.id} short_code={self.short_code!r}>"

    @property
    def is_expired(self) -> bool:
        """Check if this URL has passed its expiry date."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at


class ClickLog(Base):
    """
    Append-only log of every redirect event.
    
    This table grows indefinitely — in production you'd archive or
    partition it (PostgreSQL table partitioning by clicked_at month).
    For this project we keep it simple but design it partition-ready.
    
    We store ip_address as PostgreSQL INET type — this gives us:
    - Built-in validation (rejects invalid IPs)
    - Subnet queries: WHERE ip_address << '192.168.0.0/16'
    """
    __tablename__ = "click_logs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    url_id = Column(
        UUID(as_uuid=True),
        ForeignKey("urls.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # Critical: every stats query filters by url_id
    )
    clicked_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,  # Enables time-range analytics queries
    )
    ip_address = Column(INET, nullable=True)   # INET = PostgreSQL IP type
    user_agent = Column(Text, nullable=True)
    referer = Column(Text, nullable=True)

    # Relationship back to URL
    url = relationship("URL", back_populates="click_logs")

    def __repr__(self) -> str:
        return f"<ClickLog url_id={self.url_id} at={self.clicked_at}>"


# ── Composite indexes defined outside the class ───────────────────────────────
# These can't be expressed as column-level index=True

# For analytics: "show me clicks for URL X in the last 30 days"
Index(
    "ix_click_logs_url_id_clicked_at",
    ClickLog.url_id,
    ClickLog.clicked_at,
)