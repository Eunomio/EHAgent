"""Resident-safe current-task and feedback endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.dependencies import get_task_service
from app.schemas.tasks import CurrentTaskResponse, TaskFeedbackRequest, TaskFeedbackResponse
from app.services.task_service import TaskNotActionableError, TaskNotFoundError, TaskService

router = APIRouter(prefix="/tasks", tags=["resident tasks"])


@router.get("/current", response_model=CurrentTaskResponse)
def current_task(
    task_service: Annotated[TaskService, Depends(get_task_service)],
) -> CurrentTaskResponse:
    """Return at most one primary task for the resident home."""

    task = task_service.latest()
    message = "目前没有需要处理的演示任务。"
    if task:
        message = "这里有一件需要您确认的事情。"
    return CurrentTaskResponse(task=task, message=message, checked_at=datetime.now(UTC))


@router.post("/{task_id}/feedback", response_model=TaskFeedbackResponse)
def submit_feedback(
    task_id: str,
    payload: TaskFeedbackRequest,
    idempotency_key: Annotated[str, Header(min_length=8, max_length=128)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
) -> TaskFeedbackResponse:
    """Apply one resident action with an idempotency key."""

    try:
        return task_service.feedback(task_id, payload, idempotency_key=idempotency_key)
    except TaskNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        ) from error
    except TaskNotActionableError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="TASK_NOT_ACTIONABLE"
        ) from error
