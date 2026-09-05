from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

MODULE = runpy.run_path(str(Path(__file__).parents[1] / "scripts" / "test-vlm-safety.py"))


def test_experiment_prompt_uses_hazard_avoidability_principle() -> None:
    prompt = MODULE["prompt_text"](
        {"image_path": "camera/toy-car.jpg"},
        {"image_width": 1920, "image_height": 1080, "walkway_polygon": [[0, 0], [1, 1]]},
    )

    assert "物理致害潜势—情境可规避性" in prompt
    assert "可察觉性和可避让性" in prompt
    assert "单个低矮小物品" in prompt
    assert "不等于行走者能提前看见" in prompt


def test_request_contains_baseline_current_and_schema() -> None:
    label = {"image_path": "c6c01/current.jpg"}
    walkway = {"image_width": 768, "image_height": 432, "walkway_polygon": [[1, 2], [3, 4], [5, 6]]}

    body = MODULE["request_body"](
        "vision-model",
        label,
        walkway,
        "data:image/jpeg;base64,base",
        "data:image/jpeg;base64,current",
        500,
    )

    content = body["input"][0]["content"]
    images = [item for item in content if item["type"] == "input_image"]
    assert [item["image_url"] for item in images] == ["data:image/jpeg;base64,current", "data:image/jpeg;base64,base"]
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True


def test_chat_request_uses_ecnu_multimodal_and_response_format() -> None:
    label = {"image_path": "c6c01/current.jpg"}
    walkway = {"image_width": 768, "image_height": 432, "walkway_polygon": [[1, 2], [3, 4], [5, 6]]}

    body = MODULE["chat_request_body"](
        "ecnu-plus",
        label,
        walkway,
        "data:image/jpeg;base64,base",
        "data:image/jpeg;base64,current",
        500,
    )

    content = body["messages"][1]["content"]
    images = [item for item in content if item["type"] == "image_url"]
    assert [item["image_url"]["url"] for item in images] == [
        "data:image/jpeg;base64,current",
        "data:image/jpeg;base64,base",
    ]
    assert body["response_format"]["type"] == "json_schema"


def test_prediction_evaluation_ignores_reason_wording() -> None:
    prediction_type = MODULE["VisionPrediction"]
    prediction = prediction_type(
        visibility="usable",
        hazard_present=True,
        hazard_types=["box"],
        position_zone="inner_side",
        walkway_occupation="under_quarter",
        walkway_length_occupation="under_quarter",
        passage_effect="detour",
        trip_risk="possible",
        reason="模型使用了不同的表述。",
    )
    label: dict[str, Any] = {
        **prediction.model_dump(),
        "reason": "人工标注的判断依据。",
    }

    result = MODULE["evaluation"](prediction, label)

    assert all(result["field_matches"].values())
    assert result["matched_count"] == 8
    assert result["match_rate"] == 1.0


def test_clear_evaluation_ignores_location_fields() -> None:
    prediction_type = MODULE["VisionPrediction"]
    prediction = prediction_type(
        visibility="usable",
        hazard_present=False,
        hazard_types=[],
        position_zone="unknown",
        walkway_occupation="unknown",
        walkway_length_occupation="unknown",
        passage_effect="unknown",
        trip_risk="unknown",
        reason="走道畅通。",
    )
    label = {
        **prediction.model_dump(),
        "position_zone": "outside",
        "walkway_occupation": "none",
        "walkway_length_occupation": "none",
        "passage_effect": "none",
        "trip_risk": "none",
    }

    result = MODULE["evaluation"](prediction, label)

    assert result["ignored_fields"] == [
        "position_zone",
        "walkway_occupation",
        "walkway_length_occupation",
        "passage_effect",
        "trip_risk",
    ]
    assert result["matched_count"] == 3
    assert result["total_count"] == 3


def test_parse_prediction_accepts_json_code_fence() -> None:
    text = """```json
{"visibility":"usable","hazard_present":false,"hazard_types":[],"position_zone":"outside","walkway_occupation":"none","walkway_length_occupation":"none","passage_effect":"none","trip_risk":"none","reason":"走道畅通。"}
```"""

    result = MODULE["parse_prediction"](text)

    assert result.hazard_present is False


def test_parse_json_object_keeps_incompatible_model_output() -> None:
    text = '{"risk_level":"low","action":"recheck"}'

    result = MODULE["parse_json_object"](text)

    assert result == {"risk_level": "low", "action": "recheck"}


def test_requires_longitudinal_occupation_in_current_labels() -> None:
    labels = [{"image_path": "c6c01/old.jpg"}]

    try:
        MODULE["require_current_labels"](labels)
    except ValueError as exc:
        assert "缺少纵向占用字段" in str(exc)
    else:
        raise AssertionError("old labels should be rejected")


def test_normalize_prediction_maps_common_aliases_and_keeps_raw() -> None:
    raw = {
        "visibility": "clear",
        "hazard_types": ["cardboard_box", "carton"],
    }

    normalized, changes = MODULE["normalize_prediction"](raw)

    assert raw == {"visibility": "clear", "hazard_types": ["cardboard_box", "carton"]}
    assert normalized == {
        "visibility": "usable",
        "hazard_types": ["box"],
    }
    assert len(changes) == 3


def test_derive_assessment_uses_observable_fields() -> None:
    prediction_type = MODULE["VisionPrediction"]
    prediction = prediction_type(
        visibility="usable",
        hazard_present=True,
        hazard_types=["box"],
        position_zone="inner_side",
        walkway_occupation="under_quarter",
        walkway_length_occupation="under_quarter",
        passage_effect="detour",
        trip_risk="possible",
        reason="需要绕开。",
    )

    assert MODULE["derive_assessment"](prediction) == {
        "risk_level": "medium",
        "recommended_action": "create_task",
    }
