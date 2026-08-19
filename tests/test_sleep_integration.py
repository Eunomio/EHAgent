import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.store import ProductStore


def sleep_report(serial: str = "SLEEP001") -> dict[str, object]:
    return {
        "external_report_id": "report-20260817",
        "device_serial": serial,
        "report_date": "2026-08-17",
        "timezone": "Asia/Shanghai",
        "sleep_start": "2026-08-16T22:30:00+08:00",
        "sleep_end": "2026-08-17T06:10:00+08:00",
        "duration_minutes": 430,
        "awake_minutes": 30,
        "light_sleep_minutes": 230,
        "deep_sleep_minutes": 110,
        "rem_sleep_minutes": 60,
        "sleep_score": 81,
        "respiratory_rate": 16.2,
        "respiratory_min": 13.1,
        "respiratory_max": 19.8,
        "heart_rate": 62,
        "heart_rate_min": 53,
        "heart_rate_max": 78,
        "bed_exit_count": 1,
        "quality": "good",
        "data_status": "final",
        "source": "ezviz_sleep_assistant",
        "measured_at": "2026-08-17T06:15:00+08:00",
        "samples": [{
            "at": "2026-08-17T01:00:00+08:00",
            "respiratory_rate": 16.0,
            "heart_rate": 61,
            "in_bed": True,
            "body_movement": 0.2,
        }],
        "stages": [{
            "start": "2026-08-16T22:30:00+08:00",
            "end": "2026-08-16T23:10:00+08:00",
            "stage": "light",
        }],
    }


def configured_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_path=tmp_path / "sleep.db",
        evidence_root=tmp_path / "evidence",
        sleep_provider="ezviz",
        sleep_device_serial="SLEEP001",
        sleep_device_id="known-device-id",
        ezviz_access_token="test-token",
    )
    return TestClient(create_app(settings))


def test_sleep_device_requires_matching_serial(tmp_path: Path) -> None:
    with configured_client(tmp_path) as client:
        assert client.post(
            "/api/v1/ingest/sleep-reports", json=sleep_report("OTHER")
        ).status_code == 409
        response = client.post(
            "/api/v1/ingest/sleep-reports", json=sleep_report()
        )
        assert response.status_code == 200
        assert response.json()["device_serial"] == "SLEEP001"


def test_sleep_device_status_reflects_real_configuration(tmp_path: Path) -> None:
    with configured_client(tmp_path) as client:
        before = client.get("/api/v1/devices").json()["sleep_assistant"]
        assert before["configured"] is True
        assert before["connection"] == "ezviz"

        client.post(
            "/api/v1/ingest/sleep-reports",
            json=sleep_report(),
        )
        latest = client.get("/api/v1/resident/sleep").json()["latest"]
        assert latest["measured_at"] == "2026-08-17T06:15:00+08:00"
        assert latest["data_status"] == "final"


def test_ezviz_report_requires_device_serial(client: TestClient) -> None:
    payload = sleep_report()
    payload.pop("device_serial")
    response = client.post("/api/v1/ingest/sleep-reports", json=payload)
    assert response.status_code == 422


def test_existing_sleep_database_is_migrated(tmp_path: Path) -> None:
    database = tmp_path / "old.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE sleep_summary ("
            "id TEXT PRIMARY KEY, sleep_start TEXT NOT NULL, sleep_end TEXT NOT NULL, "
            "duration_minutes INTEGER NOT NULL, respiratory_rate REAL, heart_rate REAL, "
            "respiratory_min REAL, respiratory_max REAL, heart_rate_min REAL, "
            "heart_rate_max REAL, bed_exit_count INTEGER, quality TEXT NOT NULL, "
            "source TEXT NOT NULL, measured_at TEXT NOT NULL, "
            "samples_json TEXT NOT NULL DEFAULT '[]')"
        )
    store = ProductStore(database)
    store.initialize()
    with sqlite3.connect(database) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(sleep_summary)")
        }
    assert {"device_serial", "external_report_id", "stages_json", "data_status"} <= columns
