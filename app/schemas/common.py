"""Shared API response schemas."""

from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    """Stable public error body."""

    code: str
    message: str
    trace_id: str | None = None
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Stable error envelope."""

    error: ErrorBody
