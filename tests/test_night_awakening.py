import json
from datetime import datetime, timedelta
from pathlib import Path

from app.sleep.demo import DEMO_DATASET_ID, DEMO_FIXTURE_PATH, demo_records
from app.sleep.night_awakening import (
    ALGORITHM_VERSION,
    assess_night_awakening,
    waiting_payload,
)
from app.store import ProductStore


def history() -> list[dict[str, object]]:
    return list(reversed(demo_records()))


def comparable_history() -> list[dict[str, object]]:
    template = demo_records()[0]
    baseline = [
        {
            **template,
            "external_report_id": f"baseline-{index}",
            "report_date": f"2026-08-{18 + index:02d}",
            "duration_minutes": 440,
            "heart_rate": 62.0,
            "respiratory_rate": 14.3,
        }
        for index in range(7)
    ]
    latest = {
        **template,
        "external_report_id": "changed-latest",
        "report_date": "2026-08-25",
        "duration_minutes": 330,
        "heart_rate": 70.0,
        "respiratory_rate": 18.0,
    }
    return [latest, *reversed(baseline)]


def test_demo_sleep_fixture_is_packaged_with_source() -> None:
    payload = json.loads(DEMO_FIXTURE_PATH.read_text(encoding="utf-8"))

    assert payload["dataset_id"] == DEMO_DATASET_ID
    assert payload["source"] == "demo_generated"
    assert len(payload["records"]) == 7
    assert payload["records"][3]["awake_minutes"] == 91
    assert payload["records"][4]["awake_minutes"] == 100
    assert payload["records"][-1]["duration_minutes"] == 407


def assess(records: list[dict[str, object]], **overrides: object) -> dict[str, object]:
    arguments = {
        "detected_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "event_source": "demo_generated",
        "event_reliable": True,
        "snapshot_status": "provisional",
        "sleep_session_ended": True,
    }
    arguments.update(overrides)
    return assess_night_awakening(records, **arguments)  # type: ignore[arg-type]


def test_waiting_payload_does_not_claim_event_interface_is_verified() -> None:
    result = waiting_payload(event_interface_verified=False)
    assert result["state"] == "waiting"
    assert result["event_interface_status"] == "pending_verification"
    assert "预测到跌倒" in result["disclaimer"]


def test_seven_night_demo_still_needs_more_baseline_for_risk_comparison() -> None:
    result = assess(history())
    assert result["attention"] == "insufficient"
    assert result["algorithm_version"] == ALGORITHM_VERSION
    assert "baseline_unavailable" in result["reason_codes"]


def test_one_adverse_change_stays_routine_care() -> None:
    records = comparable_history()
    records[0] = {
        **records[0],
        "heart_rate": 62,
        "respiratory_rate": 14.3,
    }
    result = assess(records)
    assert result["attention"] == "routine_care"
    assert sum(item["adverse_change"] for item in result["reasons"]) == 1


def test_reverse_direction_changes_do_not_raise_attention() -> None:
    records = comparable_history()
    records[0] = {
        **records[0],
        "duration_minutes": 550,
        "heart_rate": 52,
        "respiratory_rate": 10,
    }
    result = assess(records)
    assert result["attention"] == "routine_care"
    assert not any(item["adverse_change"] for item in result["reasons"])


def test_duration_is_not_comparable_before_sleep_session_ends() -> None:
    result = assess(comparable_history(), sleep_session_ended=False)
    duration = next(
        item for item in result["reasons"] if item["metric"] == "duration_minutes"
    )
    assert duration["comparison_status"] == "not_comparable"
    assert duration["adverse_change"] is False
    assert result["attention"] == "extra_care"


def test_fewer_than_seven_baseline_nights_is_insufficient() -> None:
    result = assess(history()[:7])
    assert result["attention"] == "insufficient"
    assert "baseline_unavailable" in result["reason_codes"]


def test_unreliable_or_mixed_source_event_is_insufficient() -> None:
    unreliable = assess(history(), event_reliable=False)
    assert unreliable["attention"] == "insufficient"
    assert "event_unreliable" in unreliable["reason_codes"]

    mixed = history()
    mixed[-1] = {**mixed[-1], "source": "ezviz_sleep_assistant"}
    mismatch = assess(mixed)
    assert mismatch["attention"] == "insufficient"
    assert "source_mismatch" in mismatch["reason_codes"]


def test_expiry_is_thirty_minutes_after_detection() -> None:
    detected = datetime.now().astimezone().replace(microsecond=0)
    result = assess(history(), detected_at=detected.isoformat())
    assert datetime.fromisoformat(result["expires_at"]) == detected + timedelta(minutes=30)


def test_store_auto_resolves_after_thirty_minutes(tmp_path: Path) -> None:
    store = ProductStore(tmp_path / "night.db")
    store.initialize()
    records = [store.add_sleep(item) for item in demo_records()]
    detected = datetime.now().astimezone().replace(microsecond=0) - timedelta(minutes=31)
    result = assess(list(reversed(records)), detected_at=detected.isoformat())
    stored = store.add_night_awakening(result)
    assert stored["state"] == "active"

    latest = store.latest_night_awakening(
        source="demo_generated",
        demo_dataset_id=records[-1]["demo_dataset_id"],
    )
    assert latest is not None
    assert latest["state"] == "resolved"
    assert latest["resolved_at"] == latest["expires_at"]


def test_in_bed_resolution_marks_active_assessment_resolved(tmp_path: Path) -> None:
    store = ProductStore(tmp_path / "in-bed.db")
    store.initialize()
    records = [store.add_sleep(item) for item in demo_records()]
    stored = store.add_night_awakening(assess(list(reversed(records))))
    assert stored["state"] == "active"

    resolved = store.resolve_night_awakening(
        source="demo_generated",
        demo_dataset_id=records[-1]["demo_dataset_id"],
    )
    assert resolved is not None
    assert resolved["state"] == "resolved"
    assert resolved["resolved_at"] is not None
