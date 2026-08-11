"""Risk-task states and resident feedback contracts."""

from enum import StrEnum


class TaskStatus(StrEnum):
    """Persisted lifecycle states exposed by the vertical slice."""

    OPEN = "OPEN"
    DEFERRED = "DEFERRED"
    RESCAN_PENDING = "RESCAN_PENDING"
    RESOLVED = "RESOLVED"
    DISPUTED = "DISPUTED"
    PAUSED = "PAUSED"


class FeedbackAction(StrEnum):
    """The four fixed resident actions from the PRD."""

    DONE = "DONE"
    DEFER = "DEFER"
    NOT_A_RISK = "NOT_A_RISK"
    PAUSE = "PAUSE"


ACTIONABLE_TASK_STATUSES = frozenset({TaskStatus.OPEN, TaskStatus.DEFERRED})
