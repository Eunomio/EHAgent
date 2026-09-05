"""Small, descriptive weekly overview; no clinical interpretation."""

from datetime import date, datetime, timedelta, timezone
from statistics import mean, median
from typing import Any

from app.store import ProductStore


def weekly_overview(
    store: ProductStore, *, today: date | None = None,
) -> dict[str, Any]:
    local_zone = timezone(timedelta(hours=8))
    today = today or datetime.now(local_zone).date()
    end = today - timedelta(days=today.weekday())
    start = end - timedelta(days=7)
    history = store.sleep_history(400, exclude_demo=True)
    device = history[0].get("device_serial") if history else None
    source = history[0].get("source") if history else None
    nights: dict[str, dict[str, Any]] = {}
    for record in history:
        day = str(record.get("report_date", ""))
        if (start.isoformat() <= day < end.isoformat()
                and record.get("device_serial") == device and record.get("source") == source
                and record.get("quality") != "insufficient"
                and record.get("data_status") in {"final", "corrected"}):
            nights.setdefault(day, record)
    records = list(nights.values())

    def average(key: str) -> float | None:
        values = [record[key] for record in records
                  if isinstance(record.get(key), int | float) and not isinstance(record[key], bool)]
        return round(mean(values), 1) if values else None

    def clock(key: str) -> str | None:
        values = []
        for record in records:
            try:
                value = datetime.fromisoformat(str(record.get(key)))
                if value.tzinfo is None:
                    continue
                value = value.astimezone(local_zone)
                values.append((value.hour * 60 + value.minute - 720) % 1440)
            except ValueError:
                continue
        if not values:
            return None
        minutes = (round(median(values)) + 720) % 1440
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    duration = average("duration_minutes")
    return {
        "title": "上周睡眠概览", "nights": len(records),
        "period_start": start.isoformat(), "period_end": (end - timedelta(days=1)).isoformat(),
        "message": ("上周睡眠记录完整，可以看看平时的休息情况。" if len(records) == 7
                    else "上周记录还不完整，先看看已有的睡眠情况。" if records
                    else "上周还没有可用记录，暂时无法评价睡眠情况。"),
        "duration_minutes": round(duration) if duration is not None else None,
        "sleep_time": clock("sleep_start"), "wake_time": clock("sleep_end"),
        "heart_rate": average("heart_rate"), "respiratory_rate": average("respiratory_rate"),
        "duration_series": [
            {"date": (start + timedelta(days=index)).isoformat(),
             "minutes": nights.get((start + timedelta(days=index)).isoformat(), {}).get("duration_minutes")}
            for index in range(7)
        ],
    }
