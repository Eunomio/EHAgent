from fastapi.testclient import TestClient


def test_real_empty_dashboard(client: TestClient) -> None:
    response = client.get("/api/v1/resident/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["sleep"]["summary"] is None
    assert body["safety"]["task"] is None


def test_sleep_summary_keeps_vitals(client: TestClient) -> None:
    payload = {
        "sleep_start": "2026-08-12T22:41:00+08:00",
        "sleep_end": "2026-08-13T06:32:00+08:00",
        "duration_minutes": 471,
        "respiratory_rate": 16.2,
        "heart_rate": 62,
        "bed_exit_count": 1,
        "quality": "good",
        "source": "ezviz_sleep_assistant",
        "measured_at": "2026-08-13T06:35:00+08:00",
        "samples": [],
    }
    assert client.post("/api/v1/ingest/sleep-summaries", json=payload).status_code == 200
    latest = client.get("/api/v1/resident/sleep").json()["latest"]
    assert latest["heart_rate"] == 62
    assert latest["respiratory_rate"] == 16.2


def test_safety_task_and_action(client: TestClient) -> None:
    result = client.post("/api/v1/ingest/safety-results", json={
        "result": "obstacle", "source": "model", "object_name": "纸箱",
        "location": "卧室外走道", "detail": "纸箱占用了常走区域"
    })
    assert result.status_code == 200
    task = result.json()["task"]
    assert task["title"] == "走道中有纸箱"
    action = client.post(f"/api/v1/resident/safety/tasks/{task['id']}/actions", json={"action": "need_help"})
    assert action.status_code == 200
    assert client.get("/api/v1/resident/help").json()["requests"][0]["request_type"] == "safety"


def test_settings_expose_only_product_options(client: TestClient) -> None:
    settings = client.get("/api/v1/resident/settings").json()
    assert set(settings) == {
        "camera_paused", "sleep_alerts_paused", "contact_name", "contact_phone",
        "evidence_retention_days",
    }
