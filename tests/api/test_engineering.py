"""Engineering access, runtime and manual-event tests."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.models import ObservationEventRecord


def test_engineering_endpoint_requires_key(client: TestClient) -> None:
    response = client.post(
        "/api/v1/engineering/runtime/transition",
        json={"target": "COMMISSIONING", "reason": "Start local development"},
    )
    assert response.status_code == 401


def test_runtime_transition_and_manual_event(
    client: TestClient,
    engineering_headers: dict[str, str],
) -> None:
    transition = client.post(
        "/api/v1/engineering/runtime/transition",
        headers=engineering_headers,
        json={"target": "COMMISSIONING", "reason": "Start local development"},
    )
    assert transition.status_code == 200
    assert transition.json()["mode"] == "COMMISSIONING"

    event_response = client.post(
        "/api/v1/engineering/manual-events",
        headers=engineering_headers,
        json={
            "event_type": "scene_scan",
            "scene_id": "corridor_a",
            "observations": {"fixture": True},
        },
    )
    assert event_response.status_code == 201
    event = event_response.json()
    assert event["source"]["source_type"] == "MANUAL"
    assert event["runtime_mode"] == "COMMISSIONING"

    database = client.app.state.database
    with database.session() as session:
        count = session.scalar(select(func.count()).select_from(ObservationEventRecord))
    assert count == 1


def test_manual_event_is_rejected_outside_test_modes(
    client: TestClient,
    engineering_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/engineering/manual-events",
        headers=engineering_headers,
        json={"event_type": "scene_scan", "scene_id": "corridor_a"},
    )
    assert response.status_code == 409
