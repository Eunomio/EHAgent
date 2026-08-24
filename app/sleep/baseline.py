"""Transparent personal-baseline comparison for nightly sleep records."""

from statistics import median
from typing import Any

MIN_BASELINE_NIGHTS = 7
MAX_BASELINE_NIGHTS = 14
ALGORITHM_VERSION = "personal-median-mad-v1"

METRICS: dict[str, dict[str, float | str]] = {
    "duration_minutes": {"label": "睡眠时长", "minimum_change": 45.0},
    "heart_rate": {"label": "平均心率", "minimum_change": 5.0},
    "respiratory_rate": {"label": "平均呼吸频率", "minimum_change": 2.0},
}


def _eligible(record: dict[str, Any]) -> bool:
    return (
        record.get("quality") != "insufficient"
        and record.get("data_status") in {"final", "corrected"}
    )


def _number(record: dict[str, Any], key: str) -> float | None:
    value = record.get(key)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _compare_metric(
    metric: str,
    latest: dict[str, Any],
    baseline_records: list[dict[str, Any]],
) -> dict[str, Any]:
    values = [
        value
        for item in baseline_records
        if (value := _number(item, metric)) is not None
    ]
    current = _number(latest, metric)
    comparison: dict[str, Any] = {
        "label": METRICS[metric]["label"],
        "current": current,
        "baseline_nights": len(values),
        "baseline_median": round(median(values), 2) if values else None,
        "difference": None,
        "percent_change": None,
        "status": "insufficient",
    }
    if current is None or len(values) < MIN_BASELINE_NIGHTS:
        return comparison

    center = float(comparison["baseline_median"])
    difference = current - center
    mad = median(abs(value - center) for value in values)
    robust_z = 0.6745 * difference / mad if mad > 0 else None
    minimum_change = float(METRICS[metric]["minimum_change"])
    exceeds_floor = abs(difference) >= minimum_change
    changed = exceeds_floor and (robust_z is None or abs(robust_z) >= 3.5)
    comparison.update(
        {
            "difference": round(difference, 2),
            "percent_change": round(difference / center * 100, 1) if center else None,
            "status": "changed" if changed else "close_to_baseline",
        }
    )
    return comparison


def compare_to_personal_baseline(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare the latest night with prior valid nights without making a diagnosis."""

    if not history:
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "state": "no_data",
            "message": "还没有可用于比较的睡眠记录。",
            "baseline_nights": 0,
            "minimum_nights": MIN_BASELINE_NIGHTS,
            "metrics": {},
            "changed_metrics": [],
            "window_start": None,
            "window_end": None,
        }

    latest = history[0]
    baseline_records = [
        item for item in history[1:] if _eligible(item)
    ][:MAX_BASELINE_NIGHTS]
    metrics = {
        metric: _compare_metric(metric, latest, baseline_records)
        for metric in METRICS
    }
    changed_metrics = [
        metric for metric, result in metrics.items() if result["status"] == "changed"
    ]
    comparable_metrics = [
        metric for metric, result in metrics.items() if result["status"] != "insufficient"
    ]

    if not _eligible(latest):
        state = "insufficient"
        message = "昨晚数据不完整，暂不与个人平时水平比较。"
    elif len(baseline_records) < MIN_BASELINE_NIGHTS:
        state = "baseline_building"
        remaining = MIN_BASELINE_NIGHTS - len(baseline_records)
        message = f"正在建立个人基线，还需要至少{remaining}晚有效数据。"
    elif not comparable_metrics:
        state = "insufficient"
        message = "可用指标不足，暂不判断昨晚是否偏离个人基线。"
    elif changed_metrics:
        state = "changed"
        labels = "、".join(str(metrics[metric]["label"]) for metric in changed_metrics)
        message = f"昨晚的{labels}与个人近期水平有明显差异，建议结合起床后的实际状态观察。"
    else:
        state = "close_to_baseline"
        message = "昨晚可用指标与个人近期水平接近。"

    return {
        "algorithm_version": ALGORITHM_VERSION,
        "state": state,
        "message": message,
        "baseline_nights": len(baseline_records),
        "minimum_nights": MIN_BASELINE_NIGHTS,
        "metrics": metrics,
        "changed_metrics": changed_metrics,
        "window_start": baseline_records[-1].get("report_date") if baseline_records else None,
        "window_end": baseline_records[0].get("report_date") if baseline_records else None,
    }
