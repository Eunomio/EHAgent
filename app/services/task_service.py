"""Persisted cleanup-task lifecycle and idempotent resident feedback."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.db.models import (
    AuditLogRecord,
    RiskTaskRecord,
    RuntimeStateRecord,
    TaskFeedbackRecord,
)
from app.db.session import Database
from app.domain.tasks import ACTIONABLE_TASK_STATUSES, FeedbackAction, TaskStatus
from app.schemas.tasks import RiskTaskResponse, TaskFeedbackRequest, TaskFeedbackResponse


class TaskNotFoundError(LookupError):
    """Raised when a requested task does not exist."""


class TaskNotActionableError(ValueError):
    """Raised when feedback targets a terminal or waiting task."""


class TaskService:
    """Own task reads, status transitions and feedback audit records."""

    def __init__(self, database: Database) -> None:
        self._database = database

    @staticmethod
    def to_response(record: RiskTaskRecord) -> RiskTaskResponse:
        return RiskTaskResponse(
            task_id=record.task_id,
            title=record.title,
            location=record.location,
            risk_type=record.risk_type,
            risk_level=record.risk_level,
            explanation=record.explanation,
            suggested_action=record.suggested_action,
            status=TaskStatus(record.status),
            source_type=record.source_type,
            runtime_mode=record.runtime_mode,
            evidence_url=record.evidence_url,
            evidence_label=record.evidence_label,
            is_demo=record.runtime_mode != "ACTIVE" or record.source_type != "REAL_DEVICE",
            created_at=record.created_at,
            updated_at=record.updated_at,
            deferred_until=record.deferred_until,
        )

    def latest(self) -> RiskTaskResponse | None:
        """Return the most recently updated task for the single-card resident home."""

        with self._database.session() as session:
            query = select(RiskTaskRecord)
            runtime = session.get(RuntimeStateRecord, 1)
            if runtime and runtime.mode == "ACTIVE":
                query = query.where(
                    RiskTaskRecord.runtime_mode == "ACTIVE",
                    RiskTaskRecord.source_type == "REAL_DEVICE",
                )
            record = session.scalar(
                query.order_by(RiskTaskRecord.updated_at.desc(), RiskTaskRecord.id.desc())
            )
            return self.to_response(record) if record else None

    @staticmethod
    def _message(status: TaskStatus) -> str:
        messages = {
            TaskStatus.OPEN: "这件事还需要处理。",
            TaskStatus.DEFERRED: "好的，稍后再提醒您。",
            TaskStatus.RESCAN_PENDING: "已记录，等待用整改后素材复查。",
            TaskStatus.RESOLVED: "复查完成，通道已经恢复。",
            TaskStatus.DISPUTED: "已记录：这里没有风险。",
            TaskStatus.PAUSED: "此类提醒已经暂停。",
        }
        return messages[status]

    def feedback(
        self,
        task_id: str,
        payload: TaskFeedbackRequest,
        *,
        idempotency_key: str,
    ) -> TaskFeedbackResponse:
        """Apply one of four fixed actions exactly once per idempotency key."""

        with self._database.session() as session:
            existing_feedback = session.scalar(
                select(TaskFeedbackRecord).where(
                    TaskFeedbackRecord.idempotency_key == idempotency_key
                )
            )
            if existing_feedback:
                existing_task = session.scalar(
                    select(RiskTaskRecord).where(
                        RiskTaskRecord.task_id == existing_feedback.task_id
                    )
                )
                if existing_task is None:
                    raise TaskNotFoundError(existing_feedback.task_id)
                result_status = TaskStatus(existing_feedback.result_status)
                return TaskFeedbackResponse(
                    task=self.to_response(existing_task),
                    message=self._message(result_status),
                    duplicate=True,
                )

            record = session.scalar(
                select(RiskTaskRecord).where(RiskTaskRecord.task_id == task_id)
            )
            if record is None:
                raise TaskNotFoundError(task_id)
            current = TaskStatus(record.status)
            if current not in ACTIONABLE_TASK_STATUSES:
                raise TaskNotActionableError(f"Task {task_id} is {current}")

            now = datetime.now(UTC)
            target = {
                FeedbackAction.DONE: TaskStatus.RESCAN_PENDING,
                FeedbackAction.DEFER: TaskStatus.DEFERRED,
                FeedbackAction.NOT_A_RISK: TaskStatus.DISPUTED,
                FeedbackAction.PAUSE: TaskStatus.PAUSED,
            }[payload.action]
            record.status = target.value
            record.updated_at = now
            record.deferred_until = (
                now + timedelta(minutes=30) if payload.action == FeedbackAction.DEFER else None
            )
            feedback_id = str(uuid4())
            session.add(
                TaskFeedbackRecord(
                    feedback_id=feedback_id,
                    task_id=task_id,
                    idempotency_key=idempotency_key,
                    action=payload.action.value,
                    reason_code=payload.reason_code,
                    result_status=target.value,
                )
            )
            session.add(
                AuditLogRecord(
                    action="TASK_FEEDBACK",
                    actor="resident-local",
                    object_type="risk_task",
                    object_id=task_id,
                    detail_json=json.dumps(
                        {"action": payload.action.value, "to": target.value},
                        ensure_ascii=False,
                    ),
                    occurred_at=now,
                )
            )
            session.flush()
            return TaskFeedbackResponse(
                task=self.to_response(record), message=self._message(target)
            )
