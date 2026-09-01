"""Transparent fixed rules that create proactive care events."""

from typing import Any

from app.sleep.baseline import compare_to_personal_baseline
from app.store import ProductStore


def create_sleep_change_event(
    store: ProductStore, latest: dict[str, Any]
) -> dict[str, Any] | None:
    """Create one inquiry only after two consecutive changed sleep reports."""

    history = store.sleep_report_history(16)
    if not history or history[0].get("id") != latest.get("id") or len(history) < 9:
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
