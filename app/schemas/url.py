# app/schemas/url.py

from pydantic import BaseModel, HttpUrl, Field, field_validator, model_validator
from datetime import datetime
from typing import Optional
import re


# ── Request Schemas (API input) ───────────────────────────────────────────────

class URLCreateRequest(BaseModel):
    """
    Body for POST /shorten
    
    We use HttpUrl from Pydantic — it validates that the URL is
    actually a valid HTTP/HTTPS URL, not just a string.
    """
    original_url: HttpUrl = Field(
        ...,
        description="The long URL to shorten",
        examples=["https://www.example.com/very/long/path?with=query&params=true"]
    )
    custom_code: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=20,
        description="Optional custom short code (e.g. 'my-link')",
        examples=["my-promo"]
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        description="Optional expiration datetime (UTC). Null = never expires.",
    )

    @field_validator("custom_code")
    @classmethod
    def validate_custom_code(cls, v: Optional[str]) -> Optional[str]:
        """
        Custom codes must be URL-safe: letters, numbers, hyphens, underscores.
        Reject anything that would break URL parsing.
        """
        if v is None:
            return v
        pattern = r'^[a-zA-Z0-9_-]+$'
        if not re.match(pattern, v):
            raise ValueError(
                "Custom code may only contain letters, numbers, hyphens, "
                "and underscores."
            )
        return v.lower()  # Normalize to lowercase

    @field_validator("expires_at")
    @classmethod
    def validate_expiry_in_future(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Expiry date must be in the future."""
        if v is None:
            return v
        from datetime import timezone
        now = datetime.now(timezone.utc)
        # Make timezone-aware if naive
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v <= now:
            raise ValueError("Expiration date must be in the future.")
        return v


# ── Response Schemas (API output) ─────────────────────────────────────────────

class URLResponse(BaseModel):
    """
    Returned after creating a short URL.
    Includes the full short URL (base_url + short_code) for convenience.
    """
    id: str
    original_url: str
    short_code: str
    short_url: str               # Full URL: https://short.ly/abc1234
    is_custom_code: bool
    click_count: int
    is_active: bool
    expires_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}  # Allows model_validate(orm_object)


class URLStatsResponse(BaseModel):
    """
    Extended stats response for GET /stats/{short_code}
    Includes recent clicks detail.
    """
    id: str
    original_url: str
    short_code: str
    short_url: str
    click_count: int
    is_active: bool
    expires_at: Optional[datetime]
    created_at: datetime
    recent_clicks: list["ClickLogResponse"] = []

    model_config = {"from_attributes": True}


class ClickLogResponse(BaseModel):
    """Individual click event in stats response."""
    clicked_at: datetime
    referer: Optional[str]

    # Note: we intentionally omit ip_address from the public stats API
    # — that's private data. A real system would have auth before exposing it.

    model_config = {"from_attributes": True}


class DeleteResponse(BaseModel):
    """Confirmation response for DELETE operations."""
    message: str
    short_code: str


# ── Error Schemas ─────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Standard error envelope. All API errors return this shape."""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None   # Machine-readable error code, e.g. "URL_NOT_FOUND"