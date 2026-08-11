"""Runtime API schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.runtime import RuntimeMode


class RuntimeStateResponse(BaseModel):
    """Public runtime-state representation."""

    mode: RuntimeMode
    reason: str
    changed_by: str
    changed_at: datetime
    version: int


class RuntimeTransitionRequest(BaseModel):
    """Engineering request for one audited mode transition."""

    target: RuntimeMode
    reason: str = Field(min_length=3, max_length=512)
    actor: str = Field(default="engineering", min_length=1, max_length=128)
