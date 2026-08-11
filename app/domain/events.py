"""Normalized observation-event contracts shared by every input adapter."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.domain.runtime import RuntimeMode


class SourceType(StrEnum):
    """Immutable provenance category of an observation."""

    REAL_DEVICE = "REAL_DEVICE"
    REPLAY = "REPLAY"
    MANUAL = "MANUAL"


class CaptureMode(StrEnum):
    """How the input was captured."""

    SNAPSHOT = "snapshot"
    STREAM = "stream"
    EVENT = "event"
    FILE = "file"


class EventSource(BaseModel):
    """Normalized, non-secret input provenance."""

    model_config = ConfigDict(frozen=True)

    provider: str = Field(min_length=1, max_length=64)
    source_type: SourceType
    device_id: str | None = Field(default=None, max_length=128)
    channel_no: int | None = Field(default=None, ge=1)
    capture_mode: CaptureMode


class QualityResult(BaseModel):
    """Quality evidence that can gate downstream risk assessment."""

    model_config = ConfigDict(frozen=True)

    passed: bool = True
    score: float = Field(default=1.0, ge=0.0, le=1.0)
    reason_codes: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)


class ObservationEvent(BaseModel):
    """Canonical event stored by the local system."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    event_id: UUID = Field(default_factory=uuid4)
    trace_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime
    received_at: datetime
    source: EventSource
    event_type: str = Field(min_length=1, max_length=64)
    runtime_mode: RuntimeMode
    scene_id: str = Field(min_length=1, max_length=128)
    observations: dict[str, Any] = Field(default_factory=dict)
    quality: QualityResult = Field(default_factory=QualityResult)
    consent_scope: str = Field(default="research_demo", max_length=64)
    configuration_version: str = Field(default="unversioned", max_length=64)


class ManualObservationRequest(BaseModel):
    """Engineering input used to exercise downstream flows without a device."""

    event_type: str = Field(min_length=1, max_length=64)
    scene_id: str = Field(min_length=1, max_length=128)
    observations: dict[str, Any] = Field(default_factory=dict)
    quality: QualityResult = Field(default_factory=QualityResult)
    occurred_at: datetime | None = None
