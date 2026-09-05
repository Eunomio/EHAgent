"""Transparent fixed rules that create proactive care events."""

from datetime import datetime
from statistics import median
from typing import Any

from app.sleep.baseline import compare_to_personal_baseline
from app.store import ProductStore


def create_sleep_change_event(
    store: ProductStore, latest: dict[str, Any]
) -> dict[str, Any] | None:
    """Create a traceable inquiry for a sudden or sustained sleep change."""

    history = store.sleep_report_history(16)
    if not history or history[0].get("id") != latest.get("id"):
        return None
    return_delay_event = _create_return_delay_event(store, latest, history)
    if return_delay_event is not None:
        return return_delay_event
    if len(history) < 9:
        return None
    current = compare_to_personal_baseline(history)
    previous = compare_to_personal_baseline(history[1:])
    if current.get("state") != "changed" or previous.get("state") != "changed":
        return None
    changed = list(dict.fromkeys(
        list(current.get("changed_metrics", [])) + list(previous.get("changed_metrics", []))
    ))
    labels = {
        "duration_minutes": "睡眠时长",
        "heart_rate": "平均心率",
        "respiratory_rate": "平均呼吸频率",
    }
    readable = "、".join(labels.get(item, item) for item in changed) or "睡眠情况"
    return store.create_proactive_event(
        event_type="sleep_change",
        title="小安想了解一下您最近的状态",
        message=(
            f"我注意到最近两晚的{readable}与您平时相比有些变化。"
            "这不代表身体或心理出了问题。您今天感觉怎么样？最近有什么事情影响休息吗？"
        ),
        reason=f"睡眠助手发现连续两晚的{readable}与个人基线有明显差异",
        source=str(latest.get("source") or "sleep_assistant"),
        source_ref=str(latest.get("id") or ""),
        priority="normal",
        context={
            "latest_report_id": latest.get("id"),
            "changed_metrics": changed,
            "current_baseline_result": current,
            "previous_baseline_result": previous,
        },
    )


def _awake_after_return_minutes(record: dict[str, Any]) -> int | None:
    durations: list[int] = []
    for stage in record.get("stages", []):
        if stage.get("stage") != "awake":
            continue
        try:
            start = datetime.fromisoformat(str(stage["start"]))
            end = datetime.fromisoformat(str(stage["end"]))
        except (KeyError, TypeError, ValueError):
            continue
        durations.append(round((end - start).total_seconds() / 60))
    return max(durations, default=None)


def _create_return_delay_event(
    store: ProductStore,
    latest: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Ask the next morning after each clearly prolonged post-awakening delay."""

    if len(history) < 8 or latest.get("bed_exit_status") != "available":
        return None
    if not isinstance(latest.get("bed_exit_count"), int) or latest["bed_exit_count"] < 1:
        return None
    current = _awake_after_return_minutes(latest)
    baseline_values = [
        value
        for item in history[1:8]
        if (value := _awake_after_return_minutes(item)) is not None
    ]
    if current is None or len(baseline_values) < 7:
        return None
    baseline_median = float(median(baseline_values))
    clearly_longer = current >= 45 and current - baseline_median >= 30
    if not clearly_longer:
        return None
    return store.create_proactive_event(
        event_type="sleep_change",
        title="小安想了解一下您昨晚的休息",
        message="我发现您昨天半夜醒了以后，过了好久才睡着，是发生什么事了吗？",
        reason=(
            f"睡眠助手发现昨晚起夜后约{current}分钟处于清醒状态，"
            f"个人近7晚中位数约{round(baseline_median)}分钟"
        ),
        source=str(latest.get("source") or "sleep_assistant"),
        source_ref=str(latest.get("id") or ""),
        priority="high",
        context={
            "script_id": "sleep_return_delay_v1",
            "latest_report_id": latest.get("id"),
            "awake_after_return_minutes": current,
            "baseline_median_minutes": round(baseline_median, 1),
            "baseline_nights": 7,
            "rule": "current>=45 and current-baseline_median>=30",
        },
    )
