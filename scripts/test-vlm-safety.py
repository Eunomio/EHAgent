"""Run a standalone VLM safety experiment against collected C6c images."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COLLECTION_ROOT = REPO_ROOT / "evidence" / "c6c-collection"
DEFAULT_RESULTS_ROOT = REPO_ROOT / "evidence" / "vlm-experiments"


class ExperimentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EH_", env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    llm_api_key: str = ""
    llm_model: str = ""
    llm_api_base: str = "https://api.openai.com/v1"
    llm_timeout_seconds: float = 60
    llm_max_output_tokens: int = 500


class VisionPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visibility: Literal["usable", "limited", "insufficient"]
    hazard_present: bool | None
    hazard_types: list[Literal["box", "bag", "shoe", "stool", "cable", "other_obstacle"]]
    position_zone: Literal["outside", "boundary", "inner_side", "center", "unknown"]
    walkway_occupation: Literal["none", "under_quarter", "quarter_to_half", "over_half", "unknown"]
    walkway_length_occupation: Literal["none", "under_quarter", "quarter_to_half", "over_half", "unknown"]
    passage_effect: Literal["none", "narrowed", "detour", "difficult", "blocked", "unknown"]
    trip_risk: Literal["none", "possible", "obvious", "unknown"]
    reason: str = Field(min_length=1, max_length=200)


def derive_assessment(prediction: VisionPrediction) -> dict[str, str]:
    if prediction.visibility == "insufficient" or prediction.hazard_present is None:
        return {"risk_level": "insufficient", "recommended_action": "recheck"}
    if prediction.hazard_present is False:
        if prediction.visibility == "limited":
            return {"risk_level": "low", "recommended_action": "recheck"}
        return {"risk_level": "clear", "recommended_action": "record_clear"}
    if (
        prediction.passage_effect in {"difficult", "blocked"}
        or prediction.walkway_occupation == "over_half"
        or prediction.trip_risk == "obvious"
        or len(prediction.hazard_types) >= 2
    ):
        return {"risk_level": "high", "recommended_action": "remind_resident"}
    if (
        prediction.passage_effect == "detour"
        or prediction.walkway_occupation == "quarter_to_half"
        or (prediction.walkway_length_occupation == "over_half" and prediction.passage_effect == "narrowed")
        or prediction.trip_risk == "possible"
        or prediction.position_zone == "center"
    ):
        return {"risk_level": "medium", "recommended_action": "create_task"}
    if (
        prediction.passage_effect == "narrowed"
        or prediction.walkway_occupation == "under_quarter"
        or prediction.position_zone in {"boundary", "inner_side"}
        or prediction.visibility == "limited"
    ):
        return {"risk_level": "low", "recommended_action": "recheck"}
    return {"risk_level": "clear", "recommended_action": "record_clear"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="独立调用视觉大模型分析 C6c 图片，不启动产品后端。")
    parser.add_argument("--collection-root", type=Path, default=DEFAULT_COLLECTION_ROOT, help="图片和标注根目录")
    parser.add_argument("--image", help="只分析指定的相对图片路径")
    parser.add_argument("--limit", type=int, default=1, help="最多分析多少张，默认 1")
    parser.add_argument("--all", action="store_true", help="分析 labels.json 中的全部图片")
    parser.add_argument("--model", help="临时覆盖 .env 中的 EH_LLM_MODEL")
    parser.add_argument(
        "--api-mode",
        choices=("chat", "responses"),
        default="chat",
        help="接口格式，默认使用 ECNU 原生支持多模态和 JSON Schema 的 chat",
    )
    parser.add_argument("--dry-run", action="store_true", help="只检查输入，不发送模型请求")
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT, help="实验结果根目录")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit 必须大于 0")
    return args


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"缺少文件：{path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 JSON：{path}；{exc}") from exc


def select_labels(labels: list[dict[str, Any]], image: str | None, limit: int, use_all: bool) -> list[dict[str, Any]]:
    if image:
        selected = [label for label in labels if label.get("image_path") == image]
        if not selected:
            raise ValueError(f"labels.json 中没有找到图片：{image}")
        return selected
    return labels if use_all else labels[:limit]


def require_current_labels(labels: list[dict[str, Any]]) -> None:
    missing = [
        str(label.get("image_path") or "unknown")
        for label in labels
        if "walkway_length_occupation" not in label
    ]
    if missing:
        preview = "、".join(missing[:3])
        suffix = " 等" if len(missing) > 3 else ""
        raise ValueError(
            f"有 {len(missing)} 条标签缺少纵向占用字段，请在标注页面逐张补充并保存：{preview}{suffix}"
        )


def image_data_url(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"图片不存在：{path}")
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def camera_id_from_path(image_path: str) -> str:
    parts = Path(image_path).parts
    if not parts:
        raise ValueError(f"无法从图片路径取得摄像头编号：{image_path}")
    return parts[0]


def prompt_text(label: dict[str, Any], walkway: dict[str, Any]) -> str:
    polygon = walkway["walkway_polygon"]
    return (
        "你正在判断居家走道是否安全。第一张图片是当前截图，第二张图片是同一摄像头的畅通基准图。"
        f"图片原始尺寸为 {walkway['image_width']}×{walkway['image_height']}，"
        f"过道区域的多边形像素坐标为 {json.dumps(polygon, ensure_ascii=False)}。"
        "只依据图片中可见内容判断。hazard_present 使用 true、false 或 null；null 表示无法确认。"
        "position_zone 只能是 outside、boundary、inner_side、center、unknown。"
        "walkway_occupation 表示物品所在位置处横向占掉的过道通行宽度比例，不是物品覆盖整块过道的面积。"
        "它只能是 none、under_quarter、quarter_to_half、over_half、unknown。"
        "walkway_length_occupation 表示物品沿行走方向占用过道长度的比例，"
        "只能是 none、under_quarter、quarter_to_half、over_half、unknown。"
        "passage_effect 只能是 none、narrowed、detour、difficult、blocked、unknown。"
        "trip_risk 只能是 none、possible、obvious、unknown。reason 使用一句简短中文说明可观察依据。"
        "必须且只能返回以下八个字段：visibility、hazard_present、hazard_types、position_zone、"
        "walkway_occupation、walkway_length_occupation、passage_effect、trip_risk、reason。每个字段都必须出现。"
        "visibility 只能是 usable、limited 或 insufficient，禁止填写 clear。"
        "hazard_types 只能从 box、bag、shoe、stool、cable、other_obstacle 中选择，"
        "纸箱必须写 box，禁止使用 boxes、carton、package、packaging、cardboard_box 等同义词。"
        "输出示例："
        '{"visibility":"usable","hazard_present":true,"hazard_types":["box"],'
        '"position_zone":"inner_side","walkway_occupation":"under_quarter",'
        '"walkway_length_occupation":"under_quarter",'
        '"passage_effect":"detour","trip_risk":"possible",'
        '"reason":"纸箱占用少量走道，经过时需要绕开。"}'
        f"当前图片路径：{label['image_path']}。"
    )


def request_body(
    model: str,
    label: dict[str, Any],
    walkway: dict[str, Any],
    baseline_url: str,
    current_url: str,
    max_output_tokens: int,
) -> dict[str, Any]:
    return {
        "model": model,
        "instructions": "比较畅通基准图和当前截图，判断当前过道安全情况，并严格按照 JSON Schema 输出。",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "第一张：当前截图，是本次需要判断的图片。"},
                    {"type": "input_image", "image_url": current_url, "detail": "high"},
                    {"type": "input_text", "text": "第二张：畅通基准图，只用于比较。"},
                    {"type": "input_image", "image_url": baseline_url, "detail": "high"},
                    {"type": "input_text", "text": prompt_text(label, walkway)},
                ],
            }
        ],
        "max_output_tokens": max_output_tokens,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "walkway_safety",
                "strict": True,
                "schema": VisionPrediction.model_json_schema(),
            }
        },
    }


def chat_request_body(
    model: str,
    label: dict[str, Any],
    walkway: dict[str, Any],
    baseline_url: str,
    current_url: str,
    max_output_tokens: int,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "比较当前截图和畅通基准图，判断当前过道安全情况，并严格按照 JSON Schema 输出。",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "第一张：当前截图，是本次需要判断的图片。"},
                    {"type": "image_url", "image_url": {"url": current_url}},
                    {"type": "text", "text": "第二张：畅通基准图，只用于比较。"},
                    {"type": "image_url", "image_url": {"url": baseline_url}},
                    {"type": "text", "text": prompt_text(label, walkway)},
                ],
            },
        ],
        "stream": False,
        "temperature": 0.1,
        "max_tokens": max_output_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "walkway_safety", "schema": VisionPrediction.model_json_schema()},
        },
    }


def output_text(payload: dict[str, Any]) -> str:
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return str(content["text"])
    if isinstance(payload.get("output_text"), str):
        return str(payload["output_text"])
    raise ValueError("模型响应中没有找到 output_text")


def chat_output_text(payload: dict[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("模型响应中没有找到 choices[0].message.content") from exc
    if not isinstance(content, str) or not content:
        raise ValueError("模型响应中的 message.content 为空")
    return content


def parse_prediction(text: str) -> VisionPrediction:
    return VisionPrediction.model_validate(parse_json_object(text))


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("模型输出的 JSON 顶层必须是对象")
    return parsed


HAZARD_ALIASES = {
    "boxes": "box",
    "cardboard_box": "box",
    "carton": "box",
    "package": "box",
    "packaging": "box",
    "bags": "bag",
    "shoes": "shoe",
    "slippers": "shoe",
    "chair": "stool",
    "wire": "cable",
    "wires": "cable",
    "cord": "cable",
    "debris": "other_obstacle",
    "obstacle": "other_obstacle",
    "obstacles": "other_obstacle",
    "clutter": "other_obstacle",
}


def normalize_prediction(raw: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    normalized = dict(raw)
    changes: list[str] = []
    if normalized.get("visibility") == "clear":
        normalized["visibility"] = "usable"
        changes.append("visibility: clear -> usable")
    hazards = normalized.get("hazard_types")
    if isinstance(hazards, list):
        normalized_hazards: list[Any] = []
        for hazard in hazards:
            replacement = HAZARD_ALIASES.get(str(hazard).lower(), hazard)
            if replacement != hazard:
                changes.append(f"hazard_types: {hazard} -> {replacement}")
            if replacement not in normalized_hazards:
                normalized_hazards.append(replacement)
        normalized["hazard_types"] = normalized_hazards
    return normalized, changes


def evaluation(prediction: VisionPrediction, label: dict[str, Any]) -> dict[str, Any]:
    predicted = prediction.model_dump(mode="json")
    fields = ["visibility", "hazard_present", "hazard_types"]
    ignored_fields: list[str] = []
    detail_fields = [
        "position_zone",
        "walkway_occupation",
        "walkway_length_occupation",
        "passage_effect",
        "trip_risk",
    ]
    if label.get("hazard_present") is True:
        fields.extend(detail_fields)
    else:
        ignored_fields.extend(detail_fields)
    matches: dict[str, bool] = {}
    for field in fields:
        if field == "hazard_types":
            matches[field] = set(predicted[field]) == set(label.get(field, []))
        else:
            matches[field] = predicted[field] == label.get(field)
    return {
        "evaluated_fields": fields,
        "ignored_fields": ignored_fields,
        "field_matches": matches,
        "matched_count": sum(matches.values()),
        "total_count": len(matches),
        "match_rate": round(sum(matches.values()) / len(matches), 4),
    }


def find_walkway(walkways: Iterable[dict[str, Any]], camera_id: str) -> dict[str, Any]:
    for walkway in walkways:
        if walkway.get("camera_id") == camera_id:
            return walkway
    raise ValueError(f"walkway.json 中没有摄像头 {camera_id} 的过道区域")


def run_one(
    client: httpx.Client,
    settings: ExperimentSettings,
    model: str,
    collection_root: Path,
    label: dict[str, Any],
    walkways: list[dict[str, Any]],
    dry_run: bool,
    api_mode: str,
) -> dict[str, Any]:
    image_path = str(label["image_path"])
    baseline_path = str(label["baseline_path"])
    camera_id = camera_id_from_path(image_path)
    walkway = find_walkway(walkways, camera_id)
    current_file = collection_root / Path(image_path)
    baseline_file = collection_root / Path(baseline_path)
    baseline_url = image_data_url(baseline_file)
    current_url = image_data_url(current_file)
    body_builder = chat_request_body if api_mode == "chat" else request_body
    body = body_builder(model, label, walkway, baseline_url, current_url, settings.llm_max_output_tokens)
    if dry_run:
        return {
            "image_path": image_path,
            "baseline_path": baseline_path,
            "camera_id": camera_id,
            "model": model,
            "api_mode": api_mode,
            "dry_run": True,
            "request_image_count": 2,
            "walkway_points": len(walkway["walkway_polygon"]),
        }
    endpoint = "chat/completions" if api_mode == "chat" else "responses"
    response = client.post(
        f"{settings.llm_api_base.rstrip('/')}/{endpoint}",
        headers={"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"},
        json=body,
    )
    response.raise_for_status()
    raw_response = response.json()
    raw_text = chat_output_text(raw_response) if api_mode == "chat" else output_text(raw_response)
    raw_prediction = parse_json_object(raw_text)
    normalized_prediction, normalizations = normalize_prediction(raw_prediction)
    try:
        prediction = VisionPrediction.model_validate(normalized_prediction)
    except ValidationError as exc:
        return {
            "image_path": image_path,
            "baseline_path": baseline_path,
            "camera_id": camera_id,
            "model": model,
            "api_mode": api_mode,
            "raw_prediction": raw_prediction,
            "normalizations": normalizations,
            "validation_error": str(exc),
            "usage": raw_response.get("usage"),
            "error": "模型返回了 JSON，但字段不符合要求",
        }
    return {
        "image_path": image_path,
        "baseline_path": baseline_path,
        "camera_id": camera_id,
        "model": model,
        "api_mode": api_mode,
        "raw_prediction": raw_prediction,
        "normalizations": normalizations,
        "prediction": prediction.model_dump(mode="json"),
        "ground_truth": {key: label.get(key) for key in VisionPrediction.model_fields},
        "evaluation": evaluation(prediction, label),
        "derived_assessment": derive_assessment(prediction),
        "ground_truth_assessment": {
            "risk_level": label.get("risk_level"),
            "recommended_action": label.get("recommended_action"),
        },
        "usage": raw_response.get("usage"),
    }


def main() -> int:
    args = parse_args()
    collection_root = args.collection_root.resolve()
    try:
        labels_raw = read_json(collection_root / "labels.json")
        walkways_raw = read_json(collection_root / "walkway.json")
        if not isinstance(labels_raw, list) or not isinstance(walkways_raw, list):
            raise ValueError("labels.json 和 walkway.json 的顶层必须是数组")
        labels = select_labels(labels_raw, args.image, args.limit, args.all)
        require_current_labels(labels)
        settings = ExperimentSettings()
        model = args.model or settings.llm_model
        if not model:
            raise ValueError("请在 .env 中配置 EH_LLM_MODEL，或使用 --model")
        if not args.dry_run and not settings.llm_api_key:
            raise ValueError("请在 .env 中配置 EH_LLM_API_KEY")
        results: list[dict[str, Any]] = []
        with httpx.Client(timeout=max(60, settings.llm_timeout_seconds)) as client:
            for index, label in enumerate(labels, 1):
                print(f"[{index}/{len(labels)}] 分析 {label.get('image_path')}")
                try:
                    result = run_one(
                        client,
                        settings,
                        model,
                        collection_root,
                        label,
                        walkways_raw,
                        args.dry_run,
                        args.api_mode,
                    )
                    results.append(result)
                    if result.get("error"):
                        print(f"  字段校验失败：{result['error']}", file=sys.stderr)
                    elif result.get("evaluation"):
                        risk = result["derived_assessment"]["risk_level"]
                        evaluation_result = result["evaluation"]
                        print(
                            f"  风险：{risk}；字段匹配：{evaluation_result['matched_count']}/"
                            f"{evaluation_result['total_count']}；"
                            f"一致率：{evaluation_result['match_rate']:.1%}"
                        )
                    elif result.get("dry_run"):
                        print("  输入检查通过")
                except (httpx.HTTPError, ValueError, ValidationError, KeyError, TypeError) as exc:
                    results.append({"image_path": label.get("image_path"), "model": model, "error": str(exc)[:1000]})
                    print(f"  失败：{exc}", file=sys.stderr)
        timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        output_dir = args.results_root.resolve() / timestamp
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "results.json"
        output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        succeeded = sum("error" not in result for result in results)
        evaluated = [result for result in results if result.get("evaluation")]
        print(f"完成：成功 {succeeded}/{len(results)}；结果：{output_path}")
        if evaluated:
            total_matched = sum(result["evaluation"]["matched_count"] for result in evaluated)
            total_fields = sum(result["evaluation"]["total_count"] for result in evaluated)
            print(f"评测：字段一致 {total_matched}/{total_fields}（{total_matched / total_fields:.1%}）")
            field_totals: dict[str, int] = {}
            field_matches: dict[str, int] = {}
            for result in evaluated:
                for field, matched in result["evaluation"]["field_matches"].items():
                    field_totals[field] = field_totals.get(field, 0) + 1
                    field_matches[field] = field_matches.get(field, 0) + int(matched)
            field_summary = "；".join(
                f"{field} {field_matches[field]}/{field_totals[field]}"
                for field in field_totals
            )
            print(f"分字段：{field_summary}")
        return 0 if succeeded == len(results) else 1
    except (OSError, ValueError, ValidationError) as exc:
        print(f"无法开始实验：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
