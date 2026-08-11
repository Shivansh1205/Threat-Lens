"""Small API-key dependencies for collector and local admin routes."""

import secrets

from fastapi import Header, HTTPException, status

from app.config import get_settings


def _require(provided: str | None, expected: str, label: str) -> None:
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or missing {label} API key",
        )


def require_ingest_key(x_threatlens_key: str | None = Header(default=None)) -> None:
    _require(x_threatlens_key, get_settings().INGEST_API_KEY, "collector")


def require_admin_key(
    x_threatlens_admin_key: str | None = Header(default=None),
) -> None:
    _require(x_threatlens_admin_key, get_settings().ADMIN_API_KEY, "admin")
