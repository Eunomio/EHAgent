"""Runtime-domain transition tests."""

import pytest

from app.domain.runtime import InvalidRuntimeTransition, RuntimeMode, validate_runtime_transition


def test_initialization_can_enter_commissioning() -> None:
    validate_runtime_transition(RuntimeMode.UNINITIALIZED, RuntimeMode.COMMISSIONING)


def test_initialization_cannot_enter_active_directly() -> None:
    with pytest.raises(InvalidRuntimeTransition):
        validate_runtime_transition(RuntimeMode.UNINITIALIZED, RuntimeMode.ACTIVE)


def test_active_can_enter_maintenance() -> None:
    validate_runtime_transition(RuntimeMode.ACTIVE, RuntimeMode.MAINTENANCE)
