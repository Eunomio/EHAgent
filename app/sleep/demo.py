"""Deterministic local-only sleep dataset for product demonstrations."""

import json
from pathlib import Path
from typing import Any

from app.store import ProductStore

DEMO_DATASET_ID = "afternoon-demo-20260824-v1"

DEMO_NIGHTS = [
    ("2026-08-17", "2026-08-16T23:10:00+08:00", "2026-08-17T06:30:00+08:00", 440, 62.0, 14.4, 1),
    ("2026-08-18", "2026-08-17T22:55:00+08:00", "2026-08-18T06:20:00+08:00", 445, 61.0, 14.1, 1),
    ("2026-08-19", "2026-08-18T23:20:00+08:00", "2026-08-19T06:35:00+08:00", 435, 63.0, 14.7, 0),
    ("2026-08-20", "2026-08-19T23:05:00+08:00", "2026-08-20T06:25:00+08:00", 440, 62.0, 14.3, 1),
    ("2026-08-21", "2026-08-20T22:50:00+08:00", "2026-08-21T06:15:00+08:00", 445, 60.0, 14.0, 0),
    ("2026-08-22", "2026-08-21T23:15:00+08:00", "2026-08-22T06:40:00+08:00", 445, 63.0, 14.6, 1),
    ("2026-08-23", "2026-08-22T23:00:00+08:00", "2026-08-23T06:20:00+08:00", 440, 62.0, 14.2, 1),
    ("2026-08-24", "2026-08-24T00:10:00+08:00", "2026-08-24T05:40:00+08:00", 330, 70.0, 18.0, 2),
]


def demo_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for report_date, start, end, duration, heart, breath, exits in DEMO_NIGHTS:
        records.append(
            {
                "external_report_id": f"demo-{DEMO_DATASET_ID}-{report_date}",
                "device_serial": "demo:local",
                "demo_dataset_id": DEMO_DATASET_ID,
                "report_date": report_date,
                "timezone": "Asia/Shanghai",
                "sleep_start": start,
                "sleep_end": end,
                "duration_minutes": duration,
                "respiratory_rate": breath,
                "heart_rate": heart,
                "bed_exit_count": exits,
                "bed_exit_status": "available",
                "quality": "usable",
                "data_status": "final",
                "source": "demo_generated",
                "measured_at": end,
                "samples": [],
                "stages": [],
            }
        )
    return records


def import_demo_dataset(store: ProductStore, runtime_root: Path) -> list[dict[str, Any]]:
    records = demo_records()
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "demo_sleep_20260824.json").write_text(
        json.dumps(
            {"dataset_id": DEMO_DATASET_ID, "source": "demo_generated", "records": records},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return [store.add_sleep(record) for record in records]
