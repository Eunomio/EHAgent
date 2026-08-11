"""Persisted runtime-mode orchestration."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import AuditLogRecord, RuntimeStateRecord
from app.db.session import Database
from app.domain.runtime import RuntimeMode, validate_runtime_transition


@dataclass(frozen=True, slots=True)
class RuntimeState:
    """Transport-neutral view of the current runtime state."""

    mode: RuntimeMode
    reason: str
    changed_by: str
    changed_at: datetime
    version: int


class RuntimeService:
    """Own runtime transitions and their audit records."""

    def __init__(self, database: Database) -> None:
        self._database = database

    @staticmethod
    def _to_domain(record: RuntimeStateRecord) -> RuntimeState:
        changed_at = record.changed_at
        if changed_at.tzinfo is None:
            changed_at = changed_at.replace(tzinfo=UTC)
        return RuntimeState(
            mode=RuntimeMode(record.mode),
            reason=record.reason,
            changed_by=record.changed_by,
            changed_at=changed_at,
            version=record.version,
        )

    @staticmethod
    def _get_or_create(session: Session) -> RuntimeStateRecord:
        record = session.get(RuntimeStateRecord, 1)
        if record is None:
            record = RuntimeStateRecord(
                id=1,
                mode=RuntimeMode.UNINITIALIZED.value,
                reason="Initial application state",
                changed_by="system",
                changed_at=datetime.now(UTC),
                version=1,
            )
            session.add(record)
            session.flush()
        return record

    def get(self) -> RuntimeState:
        """Return the current mode, creating the singleton record if necessary."""

        with self._database.session() as session:
            record = self._get_or_create(session)
            return self._to_domain(record)

    def transition(
        self,
        target: RuntimeMode,
        *,
        reason: str,
        actor: str,
    ) -> RuntimeState:
        """Atomically validate, persist and audit a mode transition."""

        with self._database.session() as session:
            record = self._get_or_create(session)
            current = RuntimeMode(record.mode)
            validate_runtime_transition(current, target)

            now = datetime.now(UTC)
            record.mode = target.value
            record.reason = reason
            record.changed_by = actor
            record.changed_at = now
            record.version += 1
            session.add(
                AuditLogRecord(
                    action="RUNTIME_TRANSITION",
                    actor=actor,
                    object_type="runtime_state",
                    object_id="1",
                    detail_json=json.dumps(
                        {"from": current.value, "to": target.value, "reason": reason},
                        ensure_ascii=False,
                    ),
                    occurred_at=now,
                )
            )
            session.flush()
            return self._to_domain(record)
