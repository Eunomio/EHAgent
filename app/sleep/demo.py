"""Version-controlled, deterministic sleep dataset for product demonstrations."""

import json
from pathlib import Path
from typing import Any

from app.store import ProductStore

DEMO_DATASET_ID = "sleep-return-care-20260904-v1"
DEMO_FIXTURE_PATH = Path(__file__).with_name("demo_sleep_healthy_baseline.json")
DEMO_ABNORMAL_FIXTURE_PATH = Path(__file__).with_name("demo_sleep_return_delay.json")


def _fixture_records(path: Path, group: str) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("dataset_id") != DEMO_DATASET_ID
        or payload.get("source") != "demo_generated"
        or payload.get("group") != group
        or not isinstance(payload.get("records"), list)
    ):
        raise ValueError("演示睡眠数据文件格式不正确")
    return [dict(record) for record in payload["records"]]


def healthy_baseline_records() -> list[dict[str, Any]]:
    return _fixture_records(DEMO_FIXTURE_PATH, "healthy_baseline")


def abnormal_comparison_records() -> list[dict[str, Any]]:
    return _fixture_records(DEMO_ABNORMAL_FIXTURE_PATH, "return_to_sleep_change")


def demo_records() -> list[dict[str, Any]]:
    return [*healthy_baseline_records(), *abnormal_comparison_records()]


def import_demo_dataset(store: ProductStore) -> list[dict[str, Any]]:
    return [store.add_sleep(record) for record in demo_records()]
