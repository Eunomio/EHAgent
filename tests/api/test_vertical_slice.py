"""End-to-end API tests for the explainable competition vertical slice."""

import pytest
from fastapi.testclient import TestClient


def enter_commissioning(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/engineering/runtime/transition",
        headers=headers,
        json={"target": "COMMISSIONING", "reason": "Run vertical slice"},
    )
    assert response.status_code == 200


def test_replay_task_feedback_and_rescan_close_the_loop(
    client: TestClient,
    engineering_headers: dict[str, str],
) -> None:
    materials = client.get(
        "/api/v1/engineering/demo-materials", headers=engineering_headers
    )
    assert materials.status_code == 200
    assert {item["case_id"] for item in materials.json()} == {
        "corridor_clutter",
        "corridor_clear",
        "quality_insufficient",
    }
    enter_commissioning(client, engineering_headers)

    analysis = client.post(
        "/api/v1/engineering/demo-analyses",
        headers=engineering_headers,
        json={"case_id": "corridor_clutter"},
    )
    assert analysis.status_code == 200
    result = analysis.json()
    assert result["outcome"] == "TASK_CREATED"
    assert result["source_type"] == "REPLAY"
    assert [stage["key"] for stage in result["stages"]] == [
        "observe",
        "quality",
        "reason",
        "act",
    ]
    task_id = result["task"]["task_id"]

    resident = client.get("/api/v1/tasks/current")
    assert resident.status_code == 200
    assert resident.json()["task"]["is_demo"] is True
    assert resident.json()["task"]["status"] == "OPEN"

    feedback_headers = {"Idempotency-Key": "done-once-0001"}
    feedback = client.post(
        f"/api/v1/tasks/{task_id}/feedback",
        headers=feedback_headers,
        json={"action": "DONE"},
    )
    assert feedback.status_code == 200
    assert feedback.json()["task"]["status"] == "RESCAN_PENDING"

    duplicate = client.post(
        f"/api/v1/tasks/{task_id}/feedback",
        headers=feedback_headers,
        json={"action": "DONE"},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True

    rescan = client.post(
        "/api/v1/engineering/demo-analyses",
        headers=engineering_headers,
        json={"case_id": "corridor_clear"},
    )
    assert rescan.status_code == 200
    assert rescan.json()["outcome"] == "RESOLVED"
    assert rescan.json()["task"]["status"] == "RESOLVED"
    assert rescan.json()["task"]["evidence_label"] == "整改后的通畅走廊"

    activated = client.post(
        "/api/v1/engineering/runtime/transition",
        headers=engineering_headers,
        json={"target": "ACTIVE", "reason": "Verify demo task isolation"},
    )
    assert activated.status_code == 200
    assert client.get("/api/v1/tasks/current").json()["task"] is None


def test_quality_gate_and_manual_source_are_explicit(
    client: TestClient,
    engineering_headers: dict[str, str],
) -> None:
    enter_commissioning(client, engineering_headers)
    insufficient = client.post(
        "/api/v1/engineering/demo-analyses",
        headers=engineering_headers,
        json={"case_id": "quality_insufficient"},
    )
    assert insufficient.status_code == 200
    assert insufficient.json()["outcome"] == "EVIDENCE_INSUFFICIENT"
    assert insufficient.json()["task"] is None

    manual = client.post(
        "/api/v1/engineering/demo-analyses",
        headers=engineering_headers,
        json={
            "case_id": "corridor_clutter",
            "file_name": "my-corridor.png",
            "preview_data_url": "data:image/png;base64,AA==",
        },
    )
    assert manual.status_code == 200
    assert manual.json()["source_type"] == "MANUAL"
    assert manual.json()["task"]["source_type"] == "MANUAL"


def test_demo_analysis_requires_engineering_mode(
    client: TestClient,
    engineering_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/engineering/demo-analyses",
        headers=engineering_headers,
        json={"case_id": "corridor_clutter"},
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    ("action", "expected_status"),
    [
        ("DONE", "RESCAN_PENDING"),
        ("DEFER", "DEFERRED"),
        ("NOT_A_RISK", "DISPUTED"),
        ("PAUSE", "PAUSED"),
    ],
)
def test_all_four_resident_actions(
    client: TestClient,
    engineering_headers: dict[str, str],
    action: str,
    expected_status: str,
) -> None:
    enter_commissioning(client, engineering_headers)
    analysis = client.post(
        "/api/v1/engineering/demo-analyses",
        headers=engineering_headers,
        json={"case_id": "corridor_clutter"},
    ).json()
    response = client.post(
        f"/api/v1/tasks/{analysis['task']['task_id']}/feedback",
        headers={"Idempotency-Key": f"action-{action.lower()}-0001"},
        json={"action": action},
    )
    assert response.status_code == 200
    assert response.json()["task"]["status"] == expected_status
