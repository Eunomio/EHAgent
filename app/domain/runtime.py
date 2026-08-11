"""Runtime modes and their only legal state transitions."""

from enum import StrEnum


class RuntimeMode(StrEnum):
    """Operational mode of the complete local system."""

    UNINITIALIZED = "UNINITIALIZED"
    COMMISSIONING = "COMMISSIONING"
    ACTIVE = "ACTIVE"
    MAINTENANCE = "MAINTENANCE"
    SUSPENDED = "SUSPENDED"


ALLOWED_RUNTIME_TRANSITIONS: dict[RuntimeMode, frozenset[RuntimeMode]] = {
    RuntimeMode.UNINITIALIZED: frozenset({RuntimeMode.COMMISSIONING}),
    RuntimeMode.COMMISSIONING: frozenset(
        {RuntimeMode.ACTIVE, RuntimeMode.MAINTENANCE, RuntimeMode.SUSPENDED}
    ),
    RuntimeMode.ACTIVE: frozenset({RuntimeMode.MAINTENANCE, RuntimeMode.SUSPENDED}),
    RuntimeMode.MAINTENANCE: frozenset(
        {RuntimeMode.ACTIVE, RuntimeMode.COMMISSIONING, RuntimeMode.SUSPENDED}
    ),
    RuntimeMode.SUSPENDED: frozenset({RuntimeMode.COMMISSIONING}),
}


class InvalidRuntimeTransition(ValueError):
    """Raised when a caller requests an illegal runtime-mode transition."""


def validate_runtime_transition(current: RuntimeMode, target: RuntimeMode) -> None:
    """Validate a transition using the single domain transition table."""

    if target not in ALLOWED_RUNTIME_TRANSITIONS[current]:
        raise InvalidRuntimeTransition(f"Cannot transition from {current} to {target}")
