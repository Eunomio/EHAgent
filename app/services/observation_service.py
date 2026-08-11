"""Append-only normalized observation persistence."""

from app.db.models import ObservationEventRecord
from app.db.session import Database
from app.domain.events import ObservationEvent


class ObservationService:
    """Persist normalized observations without altering their provenance."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def append(self, event: ObservationEvent) -> ObservationEvent:
        """Store one immutable event and return the validated domain object."""

        record = ObservationEventRecord(
            event_id=str(event.event_id),
            trace_id=str(event.trace_id),
            event_type=event.event_type,
            scene_id=event.scene_id,
            source_type=event.source.source_type.value,
            runtime_mode=event.runtime_mode.value,
            occurred_at=event.occurred_at,
            received_at=event.received_at,
            payload_json=event.model_dump_json(),
        )
        with self._database.session() as session:
            session.add(record)
        return event
