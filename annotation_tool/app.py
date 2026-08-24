"""Local visual annotation UI for C6c image collections."""

from __future__ import annotations

import argparse
import csv
import json
import re
import threading
from collections import defaultdict
from pathlib import Path
from typing import Annotated, Literal, get_args
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COLLECTION_ROOT = REPO_ROOT / "evidence" / "c6c-collection"
DEFAULT_OUTPUT_PATH = DEFAULT_COLLECTION_ROOT / "labels.json"
WEB_PATH = Path(__file__).with_name("index.html")
WALKWAY_WEB_PATH = Path(__file__).with_name("walkway.html")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
TIMESTAMP_SUFFIX = re.compile(r"_\d{8}_\d{6}_\d{3}$")

Lighting = Literal["day", "light", "dim", "night", "night_ir", "backlight", "unknown"]
Visibility = Literal["usable", "limited", "insufficient"]
RiskLevel = Literal["clear", "low", "medium", "high", "insufficient"]
HazardType = Literal["box", "bag", "shoe", "stool", "cable", "other_obstacle"]
PositionZone = Literal["outside", "boundary", "inner_side", "center", "unknown"]
WalkwayOccupation = Literal["none", "under_quarter", "quarter_to_half", "over_half", "unknown"]
PassageEffect = Literal["none", "narrowed", "detour", "difficult", "blocked", "unknown"]
TripRisk = Literal["none", "possible", "obvious", "unknown"]
RecommendedAction = Literal["record_clear", "recheck", "create_task", "remind_resident"]


class AnnotationDraft(BaseModel):
    """Observable fields selected by the annotator."""

    model_config = ConfigDict(extra="forbid")

    sample_id: Annotated[str, Field(min_length=1, max_length=160)]
    image_path: Annotated[str, Field(min_length=1)]
    baseline_path: Annotated[str, Field(min_length=1)]
    lighting: Lighting
    visibility: Visibility
    hazard_present: bool | None
    hazard_types: list[HazardType]
    position_zone: PositionZone
    walkway_occupation: WalkwayOccupation
    walkway_length_occupation: WalkwayOccupation
    passage_effect: PassageEffect
    trip_risk: TripRisk
    reason: Annotated[str, Field(min_length=1, max_length=200)]

    @model_validator(mode="after")
    def validate_observations(self) -> AnnotationDraft:
        if self.visibility == "insufficient" and self.hazard_present is not None:
            raise ValueError("画面无法判断时，障碍物状态应选择“无法确认”")
        if self.hazard_present is True and not self.hazard_types:
            raise ValueError("确认有障碍物时，至少选择一种障碍物类型")
        if self.hazard_present is not True and self.hazard_types:
            raise ValueError("没有确认障碍物时，障碍物类型应为空")
        if self.hazard_present is False and (
            self.position_zone != "outside"
            or self.walkway_occupation != "none"
            or self.walkway_length_occupation != "none"
            or self.passage_effect != "none"
            or self.trip_risk != "none"
        ):
            raise ValueError("没有障碍物时，位置、占用、通行影响和绊倒风险应使用无影响选项")
        if self.hazard_present is None and (
            self.position_zone != "unknown"
            or self.walkway_occupation != "unknown"
            or self.walkway_length_occupation != "unknown"
            or self.passage_effect != "unknown"
            or self.trip_risk != "unknown"
        ):
            raise ValueError("无法确认障碍物时，其他障碍属性也应选择“无法判断”")
        return self


def derive_assessment(draft: AnnotationDraft) -> tuple[RiskLevel, RecommendedAction]:
    if draft.visibility == "insufficient" or draft.hazard_present is None:
        return "insufficient", "recheck"
    if draft.hazard_present is False:
        return ("low", "recheck") if draft.visibility == "limited" else ("clear", "record_clear")
    if (
        draft.passage_effect in {"difficult", "blocked"}
        or draft.walkway_occupation == "over_half"
        or draft.trip_risk == "obvious"
        or len(draft.hazard_types) >= 2
    ):
        return "high", "remind_resident"
    if (
        draft.passage_effect == "detour"
        or draft.walkway_occupation == "quarter_to_half"
        or (draft.walkway_length_occupation == "over_half" and draft.passage_effect == "narrowed")
        or draft.trip_risk == "possible"
        or draft.position_zone == "center"
    ):
        return "medium", "create_task"
    if (
        draft.passage_effect == "narrowed"
        or draft.walkway_occupation == "under_quarter"
        or draft.position_zone in {"boundary", "inner_side"}
        or draft.visibility == "limited"
    ):
        return "low", "recheck"
    return "clear", "record_clear"


class Annotation(AnnotationDraft):
    """Saved V2 annotation with deterministic result fields."""

    risk_level: RiskLevel
    recommended_action: RecommendedAction

    @model_validator(mode="after")
    def validate_derived_fields(self) -> Annotation:
        expected = derive_assessment(self)
        if (self.risk_level, self.recommended_action) != expected:
            raise ValueError("风险等级或建议动作与可观察属性不一致")
        return self


class WalkwayRegion(BaseModel):
    """One camera's walkway polygon in baseline-image pixel coordinates."""

    model_config = ConfigDict(extra="forbid")

    camera_id: Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")]
    baseline_path: Annotated[str, Field(min_length=1)]
    image_width: Annotated[int, Field(ge=1, le=20_000)]
    image_height: Annotated[int, Field(ge=1, le=20_000)]
    walkway_polygon: Annotated[list[tuple[int, int]], Field(min_length=3, max_length=32)]

    @model_validator(mode="after")
    def validate_points(self) -> WalkwayRegion:
        for x, y in self.walkway_polygon:
            if not 0 <= x < self.image_width or not 0 <= y < self.image_height:
                raise ValueError("过道边界点必须位于图片范围内")
        if len(set(self.walkway_polygon)) < 3:
            raise ValueError("至少需要三个不同的过道边界点")
        return self


class AnnotationStore:
    def __init__(self, collection_root: Path, output_path: Path, walkway_path: Path | None = None) -> None:
        self.collection_root = collection_root.resolve()
        self.output_path = output_path.resolve()
        self.jsonl_path = self.output_path.with_suffix(".jsonl")
        self.walkway_path = (walkway_path or output_path.with_name("walkway.json")).resolve()
        self._lock = threading.Lock()
        self._metadata = self._read_metadata()
        self._images = self._scan_images()
        self._paths = {str(item["image_path"]) for item in self._images}
        self._annotations = self._load_annotations()
        self._walkways = self._load_walkways()

    def _read_metadata(self) -> dict[str, dict[str, str]]:
        rows: dict[str, dict[str, str]] = {}
        if not self.collection_root.exists():
            return rows
        for csv_path in sorted(self.collection_root.rglob("metadata.csv")):
            try:
                with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
                    for row in csv.DictReader(file):
                        filename = (row.get("filename") or "").strip()
                        if filename:
                            rows[filename] = {key: value or "" for key, value in row.items() if key}
            except (OSError, csv.Error, UnicodeError):
                continue
        return rows

    def _scan_images(self) -> list[dict[str, object]]:
        if not self.collection_root.exists():
            return []
        paths = sorted(
            path
            for path in self.collection_root.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
        counters: dict[str, int] = defaultdict(int)
        items: list[dict[str, object]] = []
        lighting_values = set(get_args(Lighting))
        for path in paths:
            relative = path.relative_to(self.collection_root).as_posix()
            metadata = self._metadata.get(path.name, {})
            stem_prefix = TIMESTAMP_SUFFIX.sub("", path.stem)
            counters[stem_prefix] += 1
            sample_id = f"{stem_prefix}_{counters[stem_prefix]:04d}"
            camera_id = metadata.get("camera_id") or relative.split("/", 1)[0]
            lighting = metadata.get("lighting") or self._lighting_from_name(path.stem)
            scene = metadata.get("scene") or metadata.get("batch") or self._scene_from_name(path.stem)
            items.append(
                {
                    "sample_id": sample_id,
                    "image_path": relative,
                    "image_url": f"/images/{quote(relative)}",
                    "filename": path.name,
                    "captured_at": metadata.get("captured_at", ""),
                    "camera_id": camera_id,
                    "lighting": lighting if lighting in lighting_values else "unknown",
                    "scene": scene,
                    "is_baseline": "baseline" in scene.lower() or "baseline" in path.stem.lower(),
                }
            )
        return items

    @staticmethod
    def _lighting_from_name(stem: str) -> str:
        lowered = stem.lower()
        for value in ("night_ir", "backlight", "night", "dim", "light", "day"):
            if f"_{value}_" in f"_{lowered}_":
                return value
        return "unknown"

    @staticmethod
    def _scene_from_name(stem: str) -> str:
        lowered = stem.lower()
        if "baseline" in lowered:
            return "baseline"
        for value in ("box", "bag", "shoe", "stool", "cable", "mixed", "clear"):
            if f"_{value}_" in f"_{lowered}_":
                return value
        return "unknown"

    def _load_annotations(self) -> dict[str, Annotation]:
        loaded: dict[str, Annotation] = {}
        if self.output_path.exists():
            try:
                raw = json.loads(self.output_path.read_text(encoding="utf-8"))
                records = raw if isinstance(raw, list) else list(raw.values())
                for record in records:
                    try:
                        if "walkway_length_occupation" not in record:
                            record = {
                                **record,
                                "walkway_length_occupation": "none"
                                if record.get("hazard_present") is False
                                else "unknown",
                            }
                        annotation = Annotation.model_validate(record)
                    except (ValueError, TypeError):
                        continue
                    if annotation.image_path in self._paths:
                        loaded[annotation.image_path] = annotation
            except (OSError, ValueError, TypeError):
                pass
        for row in self._metadata.values():
            raw_annotation = row.get("annotation", "").strip()
            if not raw_annotation:
                continue
            try:
                annotation = Annotation.model_validate_json(raw_annotation)
            except ValueError:
                continue
            if annotation.image_path in self._paths and annotation.image_path not in loaded:
                loaded[annotation.image_path] = annotation
        return loaded

    def _load_walkways(self) -> dict[str, WalkwayRegion]:
        loaded: dict[str, WalkwayRegion] = {}
        if not self.walkway_path.exists():
            return loaded
        try:
            raw = json.loads(self.walkway_path.read_text(encoding="utf-8"))
            records = raw if isinstance(raw, list) else list(raw.values())
            for record in records:
                region = WalkwayRegion.model_validate(record)
                if region.baseline_path in self._paths:
                    loaded[region.camera_id] = region
        except (OSError, ValueError, TypeError):
            return {}
        return loaded

    def inventory(self) -> dict[str, object]:
        annotated = set(self._annotations)
        items = [{**item, "annotated": item["image_path"] in annotated} for item in self._images]
        return {
            "images": items,
            "annotations": {path: value.model_dump(mode="json") for path, value in self._annotations.items()},
            "output_path": str(self.output_path),
        }

    def image_file(self, relative_path: str) -> Path:
        candidate = (self.collection_root / relative_path).resolve()
        try:
            candidate.relative_to(self.collection_root)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="图片不存在") from exc
        if not candidate.is_file() or candidate.suffix.lower() not in IMAGE_EXTENSIONS:
            raise HTTPException(status_code=404, detail="图片不存在")
        return candidate

    def walkway_inventory(self) -> dict[str, object]:
        baselines = [item for item in self._images if item["is_baseline"]]
        return {
            "baselines": baselines,
            "walkways": {camera: region.model_dump(mode="json") for camera, region in self._walkways.items()},
            "output_path": str(self.walkway_path),
        }

    def save_walkway(self, region: WalkwayRegion) -> dict[str, object]:
        image = next((item for item in self._images if item["image_path"] == region.baseline_path), None)
        if image is None:
            raise HTTPException(status_code=400, detail="基准图不在采集目录中")
        if not image["is_baseline"]:
            raise HTTPException(status_code=400, detail="请选择 baseline 场景的图片")
        if image["camera_id"] != region.camera_id:
            raise HTTPException(status_code=400, detail="基准图与摄像头编号不一致")
        with self._lock:
            self._walkways[region.camera_id] = region
            records = [self._walkways[camera].model_dump(mode="json") for camera in sorted(self._walkways)]
            self.walkway_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.walkway_path.with_suffix(self.walkway_path.suffix + ".tmp")
            temporary.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(self.walkway_path)
        return {"saved": True, "camera_id": region.camera_id, "output_path": str(self.walkway_path)}

    def save(self, draft: AnnotationDraft) -> dict[str, object]:
        if draft.image_path not in self._paths:
            raise HTTPException(status_code=404, detail="当前图片不在采集目录中")
        if draft.baseline_path not in self._paths:
            raise HTTPException(status_code=400, detail="基准图不在采集目录中")
        risk_level, recommended_action = derive_assessment(draft)
        annotation = Annotation.model_validate(
            {**draft.model_dump(mode="json"), "risk_level": risk_level, "recommended_action": recommended_action}
        )
        with self._lock:
            self._annotations[annotation.image_path] = annotation
            self._write_files()
        return {
            "saved": True,
            "annotated_count": len(self._annotations),
            "total_count": len(self._images),
            "output_path": str(self.output_path),
            "annotation": annotation.model_dump(mode="json"),
        }

    def _write_files(self) -> None:
        records = [self._annotations[path].model_dump(mode="json") for path in sorted(self._annotations)]
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        json_temp = self.output_path.with_suffix(self.output_path.suffix + ".tmp")
        jsonl_temp = self.jsonl_path.with_suffix(self.jsonl_path.suffix + ".tmp")
        json_temp.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        jsonl_temp.write_text(
            "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records),
            encoding="utf-8",
        )
        json_temp.replace(self.output_path)
        jsonl_temp.replace(self.jsonl_path)


def create_app(
    collection_root: Path = DEFAULT_COLLECTION_ROOT,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    walkway_path: Path | None = None,
) -> FastAPI:
    store = AnnotationStore(collection_root, output_path, walkway_path)
    app = FastAPI(title="C6c 图片标注工具", docs_url=None, redoc_url=None)
    app.state.annotation_store = store

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse(WEB_PATH.read_text(encoding="utf-8"))

    @app.get("/walkway", response_class=HTMLResponse)
    async def walkway_page() -> HTMLResponse:
        return HTMLResponse(WALKWAY_WEB_PATH.read_text(encoding="utf-8"))

    @app.get("/api/data")
    async def data() -> dict[str, object]:
        return store.inventory()

    @app.get("/images/{relative_path:path}")
    async def image(relative_path: str) -> FileResponse:
        return FileResponse(store.image_file(relative_path))

    @app.put("/api/annotations")
    async def save(annotation: AnnotationDraft) -> dict[str, object]:
        return store.save(annotation)

    @app.get("/api/walkways")
    async def walkways() -> dict[str, object]:
        return store.walkway_inventory()

    @app.put("/api/walkways")
    async def save_walkway(region: WalkwayRegion) -> dict[str, object]:
        return store.save_walkway(region)

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动 C6c 图片可视化标注工具。")
    parser.add_argument("--collection-root", type=Path, default=DEFAULT_COLLECTION_ROOT, help="采集图片根目录")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="JSON 输出文件")
    parser.add_argument("--walkway-output", type=Path, default=None, help="过道区域 JSON 输出文件")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认仅限本机")
    parser.add_argument("--port", type=int, default=8010, help="监听端口，默认 8010")
    return parser.parse_args()


def main() -> None:
    import uvicorn

    args = parse_args()
    uvicorn.run(create_app(args.collection_root, args.output, args.walkway_output), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
