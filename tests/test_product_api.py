from datetime import date

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
    analysis = client.get("/api/v1/resident/sleep").json()["analysis"]
    assert analysis["source"] == "template"
    assert "62" in analysis["content"]["summary"]


def test_sleep_sync_persists_the_ezviz_contract(client: TestClient) -> None:
    requested: list[date] = []

    async def summary_for_date(target_date: date) -> dict[str, object]:
        requested.append(target_date)
        return {
            "id": "ezviz-sleep-test", "sleep_start": "2026-08-12T22:30:00+08:00",
            "sleep_end": "2026-08-13T06:21:00+08:00", "duration_minutes": 471,
            "respiratory_rate": 15.0, "heart_rate": 62.0, "respiratory_min": 11.0,
            "respiratory_max": 18.0, "heart_rate_min": 50.0, "heart_rate_max": 82.0,
            "bed_exit_count": None, "quality": "usable", "source": "ezviz_sleep_assistant",
            "measured_at": "2026-08-13T06:21:00+08:00", "samples": [],
        }

    client.app.state.ezviz.sleep_summary_for_date = summary_for_date
    response = client.post("/api/v1/devices/sleep/sync?target_date=2026-08-13")
    assert response.status_code == 200
    assert requested == [date(2026, 8, 13)]
    assert response.json()["sleep"]["heart_rate"] == 62.0
    latest = client.get("/api/v1/resident/sleep").json()["latest"]
    assert latest["respiratory_rate"] == 15.0


def test_safety_task_and_action(client: TestClient) -> None:
    result = client.post("/api/v1/ingest/safety-results", json={
        "result": "obstacle", "source": "model", "object_name": "纸箱",
        "location": "卧室外走道", "detail": "纸箱占用了常走区域"
    })
    assert result.status_code == 200
    task = result.json()["task"]
    assert task["title"] == "走道中有纸箱"
    assert result.json()["language"]["source"] == "template"
    action = client.post(f"/api/v1/resident/safety/tasks/{task['id']}/actions", json={"action": "need_help"})
    assert action.status_code == 200
    assert client.get("/api/v1/resident/help").json()["requests"][0]["request_type"] == "safety"


def test_settings_expose_only_product_options(client: TestClient) -> None:
    settings = client.get("/api/v1/resident/settings").json()
    assert set(settings) == {
        "camera_paused", "sleep_alerts_paused", "contact_name", "contact_phone",
        "evidence_retention_days",
    }


def test_resident_feedback_keeps_original_and_digest(client: TestClient) -> None:
    response = client.post("/api/v1/resident/feedback", json={
        "topic": "product", "message": "睡眠页面很清楚，希望字体还能再大一点。",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "睡眠页面很清楚，希望字体还能再大一点。"
    assert body["summary"] == body["message"]
    assert body["source"] == "template"


def test_llm_status_does_not_expose_key(client: TestClient) -> None:
    body = client.get("/api/v1/llm/status").json()
    assert body["configured"] is False
    assert "api_key" not in body


def test_paused_camera_rejects_live_stream(client: TestClient) -> None:
    assert client.put(
        "/api/v1/resident/settings", json={"camera_paused": True}
    ).status_code == 200
    response = client.post("/api/v1/devices/c6c/live")
    assert response.status_code == 409
    assert response.json()["detail"] == "摄像头已暂停，请先恢复检查"


def test_paused_camera_rejects_sdk_session(client: TestClient) -> None:
    assert client.put(
        "/api/v1/resident/settings", json={"camera_paused": True}
    ).status_code == 200
    response = client.post("/api/v1/devices/c6c/sdk-session")
    assert response.status_code == 409
    assert response.json()["detail"] == "摄像头已暂停，请先恢复检查"
