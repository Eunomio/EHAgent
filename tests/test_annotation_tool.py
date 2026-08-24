from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from annotation_tool.app import create_app


def make_collection(root: Path) -> None:
    camera = root / "c6c01"
    camera.mkdir(parents=True)
    (camera / "c6c01_day_baseline_20260819_170958_098.jpg").write_bytes(b"\xff\xd8\xfftest")
    (camera / "c6c01_day_box_20260819_174910_211.jpg").write_bytes(b"\xff\xd8\xfftest")
    (camera / "metadata.csv").write_text(
        "filename,captured_at,camera_id,lighting,scene,bytes,annotation\n"
        "c6c01_day_baseline_20260819_170958_098.jpg,2026-08-19T17:09:58+08:00,c6c01,day,baseline,8,\n"
        "c6c01_day_box_20260819_174910_211.jpg,2026-08-19T17:49:10+08:00,c6c01,day,box,8,\n",
        encoding="utf-8-sig",
    )


def test_inventory_uses_metadata_and_lists_baseline(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    make_collection(collection)
    client = TestClient(create_app(collection, collection / "labels.json"))

    response = client.get("/api/data")

    assert response.status_code == 200
    images = response.json()["images"]
    assert len(images) == 2
    assert images[0]["lighting"] == "day"
    assert images[0]["is_baseline"] is True
    assert images[1]["scene"] == "box"


def test_save_writes_exact_json_and_jsonl_fields(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    make_collection(collection)
    output = collection / "labels.json"
    client = TestClient(create_app(collection, output))
    payload = {
        "sample_id": "c6c01_day_box_0001",
        "image_path": "c6c01/c6c01_day_box_20260819_174910_211.jpg",
        "baseline_path": "c6c01/c6c01_day_baseline_20260819_170958_098.jpg",
        "lighting": "day",
        "visibility": "usable",
        "hazard_present": True,
        "hazard_types": ["box"],
        "position_zone": "inner_side",
        "walkway_occupation": "under_quarter",
        "walkway_length_occupation": "under_quarter",
        "passage_effect": "detour",
        "trip_risk": "possible",
        "reason": "纸箱占用部分走道，经过时需要绕开。",
    }
    saved = {**payload, "risk_level": "medium", "recommended_action": "create_task"}

    response = client.put("/api/annotations", json=payload)

    assert response.status_code == 200
    assert response.json()["annotation"] == saved
    assert json.loads(output.read_text(encoding="utf-8")) == [saved]
    assert json.loads(output.with_suffix(".jsonl").read_text(encoding="utf-8")) == saved
    assert set(json.loads(output.read_text(encoding="utf-8"))[0]) == set(saved)


def test_rejects_path_outside_collection_and_inconsistent_visibility(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    make_collection(collection)
    client = TestClient(create_app(collection, collection / "labels.json"))

    assert client.get("/images/../../secret.jpg").status_code == 404
    data = client.get("/api/data").json()["images"]
    payload = {
        "sample_id": "sample-1",
        "image_path": data[1]["image_path"],
        "baseline_path": data[0]["image_path"],
        "lighting": "day",
        "visibility": "insufficient",
        "hazard_present": False,
        "hazard_types": [],
        "position_zone": "outside",
        "walkway_occupation": "none",
        "walkway_length_occupation": "none",
        "passage_effect": "none",
        "trip_risk": "none",
        "reason": "画面过暗。",
    }
    assert client.put("/api/annotations", json=payload).status_code == 422


def test_annotation_derives_clear_and_high_results(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    make_collection(collection)
    client = TestClient(create_app(collection, collection / "labels.json"))
    images = client.get("/api/data").json()["images"]
    base = {
        "sample_id": "sample-1",
        "image_path": images[0]["image_path"],
        "baseline_path": images[0]["image_path"],
        "lighting": "day",
        "visibility": "usable",
        "reason": "走道状态清晰。",
    }
    clear_payload = {
        **base,
        "hazard_present": False,
        "hazard_types": [],
        "position_zone": "outside",
        "walkway_occupation": "none",
        "walkway_length_occupation": "none",
        "passage_effect": "none",
        "trip_risk": "none",
    }
    high_payload = {
        **base,
        "image_path": images[1]["image_path"],
        "hazard_present": True,
        "hazard_types": ["box"],
        "position_zone": "center",
        "walkway_occupation": "over_half",
        "walkway_length_occupation": "quarter_to_half",
        "passage_effect": "difficult",
        "trip_risk": "possible",
    }

    clear = client.put("/api/annotations", json=clear_payload).json()["annotation"]
    high = client.put("/api/annotations", json=high_payload).json()["annotation"]

    assert (clear["risk_level"], clear["recommended_action"]) == ("clear", "record_clear")
    assert (high["risk_level"], high["recommended_action"]) == ("high", "remind_resident")


def test_save_walkway_region_for_baseline(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    make_collection(collection)
    walkway_path = collection / "walkway.json"
    client = TestClient(create_app(collection, collection / "labels.json", walkway_path))
    payload = {
        "camera_id": "c6c01",
        "baseline_path": "c6c01/c6c01_day_baseline_20260819_170958_098.jpg",
        "image_width": 768,
        "image_height": 432,
        "walkway_polygon": [[145, 431], [625, 431], [515, 175], [285, 175]],
    }

    response = client.put("/api/walkways", json=payload)

    assert response.status_code == 200
    assert json.loads(walkway_path.read_text(encoding="utf-8")) == [payload]
    data = client.get("/api/walkways").json()
    assert len(data["baselines"]) == 1
    assert data["walkways"]["c6c01"] == payload


def test_rejects_invalid_walkway_region(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    make_collection(collection)
    client = TestClient(create_app(collection, collection / "labels.json"))
    payload = {
        "camera_id": "c6c01",
        "baseline_path": "c6c01/c6c01_day_box_20260819_174910_211.jpg",
        "image_width": 768,
        "image_height": 432,
        "walkway_polygon": [[10, 10], [100, 10], [100, 100]],
    }

    assert client.put("/api/walkways", json=payload).status_code == 400
    payload["baseline_path"] = "c6c01/c6c01_day_baseline_20260819_170958_098.jpg"
    payload["walkway_polygon"] = [[10, 10], [900, 10], [100, 100]]
    assert client.put("/api/walkways", json=payload).status_code == 422
