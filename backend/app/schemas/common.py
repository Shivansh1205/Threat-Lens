"""Enums shared across ORM models and Pydantic schemas.

Single source of truth: `app.models.*` imports these for column types, and
`app.schemas.*` imports these for request/response validation. Don't redefine
these values anywhere else.
"""

from enum import Enum


class EventType(str, Enum):
    """Kind of activity a raw log event represents."""

    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILURE = "LOGIN_FAILURE"
    API_CALL = "API_CALL"
    PORT_ACCESS = "PORT_ACCESS"
    LOGOUT = "LOGOUT"


class Severity(str, Enum):
    """Alert severity bucket, aligned with the 0-100 risk score bands."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
