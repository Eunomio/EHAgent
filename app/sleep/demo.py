"""Version-controlled, deterministic sleep dataset for product demonstrations."""

import json
from pathlib import Path
from typing import Any

from app.store import ProductStore

DEMO_DATASET_ID = "initial-review-20260902-v1"
DEMO_FIXTURE_PATH = Path(__file__).with_name("demo_sleep_20260824.json")


def demo_records() -> list[dict[str, Any]]:
    payload = json.loads(DEMO_FIXTURE_PATH.read_text(encoding="utf-8"))
    if (
        payload.get("dataset_id") != DEMO_DATASET_ID
        or payload.get("source") != "demo_generated"
        or not isinstance(payload.get("records"), list)
    ):
        raise ValueError("演示睡眠数据文件格式不正确")
    return [dict(record) for record in payload["records"]]


def import_demo_dataset(store: ProductStore) -> list[dict[str, Any]]:
    return [store.add_sleep(record) for record in demo_records()]
