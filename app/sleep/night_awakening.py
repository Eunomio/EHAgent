"""Deterministic, non-clinical attention guidance for nighttime awakenings."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.sleep.baseline import compare_to_personal_baseline

ALGORITHM_VERSION = "night-awakening-attention-v1"
ACTIVE_MINUTES = 30
GUIDANCE = ["先在床边坐稳片刻", "打开照明", "扶稳后再行走"]
DISCLAIMER = "这是根据睡眠变化给出的预防性提示，不代表已经预测到跌倒。"

ADVERSE_DIRECTIONS = {
    "duration_minutes": "lower",
    "heart_rate": "higher",
    "respiratory_rate": "higher",
}


def _direction(value: float | None) -> str | None:
    if value is None:
        return None
    if value > 0:
        return "higher"
    if value < 0:
        return "lower"
    return "same"


def assess_night_awakening(
    history: list[dict[str, Any]],
    *,
    detected_at: str,
    event_source: str,
    event_reliable: bool,
    snapshot_status: str = "provisional",
    sleep_session_ended: bool = False,
) -> dict[str, Any]:
    """Build an auditable attention result without estimating fall probability."""

    latest = history[0] if history else None
    baseline = compare_to_personal_baseline(history)
    source_coherent = bool(
        latest
        and event_source == latest.get("source")
        and all(item.get("source") == latest.get("source") for item in history)
        and (
            latest.get("source") != "demo_generated"
            or all(
                item.get("demo_dataset_id") == latest.get("demo_dataset_id")
                for item in history
            )
        )
    )

    reasons: list[dict[str, Any]] = []
    adverse_changes = 0
    comparable_metrics = 0
    for metric, result in baseline.get("metrics", {}).items():
        comparable = result.get("status") != "insufficient"
        if metric == "duration_minutes" and not sleep_session_ended:
            comparable = False
        direction = _direction(result.get("difference"))
        adverse = bool(
            comparable
            and result.get("status") == "changed"
            and direction == ADVERSE_DIRECTIONS.get(metric)
        )
        comparable_metrics += int(comparable)
        adverse_changes += int(adverse)
        reasons.append(
            {
                "metric": metric,
                "label": result.get("label"),
                "current": result.get("current"),
                "baseline_median": result.get("baseline_median"),
                "difference": result.get("difference"),
                "direction": direction,
                "comparison_status": (
                    result.get("status") if comparable else "not_comparable"
                ),
                "adverse_change": adverse,
            }
        )

    insufficient_reasons: list[str] = []
    if not event_reliable:
        insufficient_reasons.append("event_unreliable")
    if not source_coherent:
        insufficient_reasons.append("source_mismatch")
    if baseline.get("state") not in {"changed", "close_to_baseline"}:
        insufficient_reasons.append("baseline_unavailable")
    if comparable_metrics < 2:
        insufficient_reasons.append("metrics_insufficient")

    if insufficient_reasons:
        attention = "insufficient"
        message = "本次起夜的数据不足，暂时不能与个人平时水平可靠比较。"
    elif adverse_changes >= 2:
        attention = "extra_care"
        message = "本次起夜建议多留意"
    else:
        attention = "routine_care"
        message = "本次起夜按平时的安全习惯慢慢起身"

    detected = datetime.fromisoformat(detected_at)
    expires_at = (detected + timedelta(minutes=ACTIVE_MINUTES)).isoformat(
        timespec="seconds"
    )
    return {
        "state": "active",
        "attention": attention,
        "event": {
            "type": "out_of_bed",
            "detected_at": detected_at,
            "source": event_source,
            "reliable": event_reliable,
        },
        "snapshot_status": snapshot_status,
        "sleep_session_ended": sleep_session_ended,
        "sleep_report_id": latest.get("id") if latest else None,
        "demo_dataset_id": latest.get("demo_dataset_id") if latest else None,
        "baseline": {
            "algorithm_version": baseline.get("algorithm_version"),
            "state": baseline.get("state"),
            "baseline_nights": baseline.get("baseline_nights", 0),
            "window_start": baseline.get("window_start"),
            "window_end": baseline.get("window_end"),
        },
        "reasons": reasons,
        "reason_codes": insufficient_reasons,
        "guidance": GUIDANCE,
        "algorithm_version": ALGORITHM_VERSION,
        "message": message,
        "disclaimer": DISCLAIMER,
        "expires_at": expires_at,
        "resolved_at": None,
    }


def waiting_payload(*, event_interface_verified: bool) -> dict[str, Any]:
    return {
        "state": "waiting",
        "attention": None,
        "event": None,
        "snapshot_status": None,
        "reasons": [],
        "reason_codes": [],
        "guidance": GUIDANCE,
        "algorithm_version": ALGORITHM_VERSION,
        "message": "尚未监测到起夜",
        "disclaimer": DISCLAIMER,
        "event_interface_status": (
            "verified" if event_interface_verified else "pending_verification"
        ),
    }
