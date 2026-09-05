from datetime import date, datetime, timedelta, timezone

from app.sleep.overview import weekly_overview
from app.store import ProductStore


def add_night(store, day, **overrides):
    end = datetime.combine(day, datetime.min.time(), tzinfo=timezone(timedelta(hours=8)))
    end += timedelta(hours=6, minutes=30)
    payload = {
        "external_report_id": "test-" + day.isoformat(), "device_serial": "TEST-ONLY",
        "report_date": day.isoformat(), "sleep_start": (end - timedelta(hours=8)).isoformat(),
        "sleep_end": end.isoformat(), "measured_at": end.isoformat(), "duration_minutes": 440,
        "heart_rate": 62.0, "respiratory_rate": 14.0, "quality": "usable",
        "data_status": "final", "source": "authorized_export",
    }
    return store.add_sleep({**payload, **overrides})


def test_week_uses_calendar_dates_and_excludes_demo_and_missing(tmp_path):
    store = ProductStore(tmp_path / "week.db")
    store.initialize()
    start = date(2026, 8, 24)
    for index in range(7):
        if index != 3:
            add_night(store, start + timedelta(days=index))
    add_night(store, start + timedelta(days=3), quality="insufficient")
    add_night(store, start + timedelta(days=7), duration_minutes=200)
    add_night(store, start + timedelta(days=8), source="demo_generated", duration_minutes=999)
    result = weekly_overview(store, today=date(2026, 9, 5))
    assert result["period_start"] == "2026-08-24"
    assert result["period_end"] == "2026-08-30"
    assert result["nights"] == 6
    assert result["duration_minutes"] == 440
    assert result["duration_series"][3]["minutes"] is None
    assert result["sleep_time"] == "22:30"
    assert result["wake_time"] == "06:30"
    assert "不完整" in result["message"]


def test_empty_week_preserves_missing_values(tmp_path):
    store = ProductStore(tmp_path / "empty.db")
    store.initialize()
    add_night(store, date(2026, 8, 24), source="demo_generated")
    result = weekly_overview(store, today=date(2026, 9, 5))
    assert result["nights"] == 0
    assert "无法评价" in result["message"]
    for key in ("duration_minutes", "sleep_time", "wake_time", "heart_rate", "respiratory_rate"):
        assert result[key] is None
    assert all(item["minutes"] is None for item in result["duration_series"])


def test_actual_endpoints_exclude_newer_demo_reports(client):
    store = client.app.state.store
    real = add_night(store, date(2026, 8, 24))
    demo = add_night(store, date(2026, 9, 4), source="demo_generated")
    dashboard = client.get("/api/v1/resident/dashboard?data_mode=actual").json()
    assert dashboard["sleep"]["summary"]["id"] == real["id"]
    report = client.get("/api/v1/resident/sleep?data_mode=actual").json()
    assert [item["id"] for item in report["history"]] == [real["id"]]
    assert "weekly_overview" in report
    event = store.create_proactive_event(
        event_type="sleep_change", title="Synthetic care", message="Synthetic message",
        reason="UI isolation test", source="qa_synthetic", source_ref=demo["id"], priority="high",
    )
    assert event is not None
    assert client.get("/api/v1/resident/dashboard").json()["care"]["active"] is not None
    assert client.get("/api/v1/resident/dashboard?data_mode=actual").json()["care"]["active"] is None


def test_safety_status_reports_in_progress_even_before_first_result(client):
    lock = client.app.state.vision_safety.analysis_lock
    assert not client.get("/api/v1/devices/c6c/safety/latest").json()["checking"]
    client.portal.call(lock.acquire)
    try:
        result = client.get("/api/v1/devices/c6c/safety/latest").json()
        assert result == {"analysis": None, "checking": True}
    finally:
        client.portal.call(lock.release)
    assert not client.get("/api/v1/devices/c6c/safety/latest").json()["checking"]

    task = client.app.state.store.create_safety_task(
        title="Synthetic task", location="QA", explanation="QA", suggestion="QA", source="qa_synthetic",
    )
    client.app.state.store.add_safety_check("medium", "qa_synthetic", "QA", None, {})
    result = client.get("/api/v1/devices/c6c/safety/latest").json()
    assert result["analysis"]["task_id"] == task["id"]
