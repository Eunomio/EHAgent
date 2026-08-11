"""API schemas for demo analysis, risk tasks and resident feedback."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.domain.events import SourceType
from app.domain.runtime import RuntimeMode
from app.domain.tasks import FeedbackAction, TaskStatus


class DemoMaterial(BaseModel):
    """One honest, deterministic material available to the test console."""

    case_id: str
    name: str
    description: str
    thumbnail_url: str
    expected_outcome: str


class DemoAnalysisRequest(BaseModel):
    """Run a replay case or a manually labelled local image through the demo agent."""

    case_id: Literal["corridor_clutter", "corridor_clear", "quality_insufficient"]
    file_name: str | None = Field(default=None, max_length=255)
    preview_data_url: str | None = Field(default=None, max_length=3_000_000)

    @model_validator(mode="after")
    def validate_manual_material(self) -> "DemoAnalysisRequest":
        if (self.file_name is None) is not (self.preview_data_url is None):
            raise ValueError("file_name and preview_data_url must be provided together")
        if self.preview_data_url and not self.preview_data_url.startswith("data:image/"):
            raise ValueError("Only image data URLs are accepted for manual demo material")
        return self


class AgentStage(BaseModel):
    """One visible, completed step in the deterministic agent workflow."""

    key: str
    label: str
    detail: str
    status: Literal["complete", "blocked"] = "complete"


class RiskTaskResponse(BaseModel):
    """Resident-safe task representation without model internals."""

    task_id: str
    title: str
    location: str
    risk_type: str
    risk_level: int
    explanation: str
    suggested_action: str
    status: TaskStatus
    source_type: SourceType
    runtime_mode: RuntimeMode
    evidence_url: str | None
    evidence_label: str
    is_demo: bool
    created_at: datetime
    updated_at: datetime
    deferred_until: datetime | None


class DemoAnalysisResponse(BaseModel):
    """Engineering result containing evidence and the visible reasoning pipeline."""

    analysis_id: str
    outcome: Literal["TASK_CREATED", "NO_ACTION", "EVIDENCE_INSUFFICIENT", "RESOLVED"]
    source_type: SourceType
    material_name: str
    summary: str
    stages: list[AgentStage]
    task: RiskTaskResponse | None = None


class CurrentTaskResponse(BaseModel):
    """Resident home payload for its single-primary-task information hierarchy."""

    task: RiskTaskResponse | None
    message: str
    checked_at: datetime


class TaskFeedbackRequest(BaseModel):
    """One of the four resident feedback actions."""

    action: FeedbackAction
    reason_code: str | None = Field(default=None, max_length=64)


class TaskFeedbackResponse(BaseModel):
    """Updated task plus plain-language confirmation."""

    task: RiskTaskResponse
    message: str
    duplicate: bool = False
