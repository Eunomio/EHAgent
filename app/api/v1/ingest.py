import json
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.dependencies import LlmDep, SettingsDep, SleepDep, StoreDep
from app.sleep.models import SleepReportIn
from app.sleep.service import SleepDeviceMismatch

router = APIRouter(prefix="/ingest", tags=["data ingest"])


class SafetyResultIn(BaseModel):
    result: Literal["clear", "obstacle", "insufficient"]
    source: Literal["model", "ezviz_ai", "reviewed_import"]
    location: str = Field(default="卧室外走道", max_length=80)
    object_name: str | None = Field(default=None, max_length=80)
    detail: str = Field(max_length=300)
    suggestion: str | None = Field(default=None, max_length=300)
    evidence_url: str | None = None


async def save_sleep_report(
    payload: SleepReportIn,
    sleep: SleepDep,
) -> dict[str, Any]:
    try:
        return await sleep.ingest(payload)
    except SleepDeviceMismatch as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/sleep-reports")
async def ingest_sleep(
    payload: SleepReportIn,
    sleep: SleepDep,
) -> dict[str, Any]:
    return await save_sleep_report(payload, sleep)


@router.post("/sleep-summaries", deprecated=True)
async def ingest_sleep_summary(
    payload: SleepReportIn,
    sleep: SleepDep,
) -> dict[str, Any]:
    return await save_sleep_report(payload, sleep)


@router.post("/safety-results")
async def ingest_safety(
    payload: SafetyResultIn, store: StoreDep, llm: LlmDep
) -> dict[str, Any]:
    check = store.add_safety_check(payload.result, payload.source, payload.detail, payload.evidence_url)
    if payload.result == "clear":
        store.resolve_pending_task()
        return {"check": check, "task": None}
    if payload.result == "insufficient":
        return {"check": check, "task": None}
    object_name = payload.object_name or "物品"
    copy, language_source = await llm.explain_safety(
        payload.location, object_name, payload.detail
    )
    task = store.create_safety_task(
        title=copy.title, location=payload.location,
        explanation=copy.explanation,
        suggestion=payload.suggestion or copy.suggestion,
        source=payload.source, evidence_url=payload.evidence_url,
    )
    language = store.add_llm_output(
        "safety", task["id"], copy.model_dump(), language_source, llm.model_name
    )
    return {"check": check, "task": task, "language": language}


@router.post("/vision-samples")
async def upload_vision_sample(
    request: Request,
    store: StoreDep,
    settings: SettingsDep,
    annotation: str = Query(...),
    source: Literal["c6c_collection", "controlled_collection"] = Query(...),
) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(415, "只接受JPEG、PNG或WebP图片")
    try:
        parsed = json.loads(annotation)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, "annotation必须是JSON") from exc
    content = await request.body()
    if len(content) > 12 * 1024 * 1024:
        raise HTTPException(413, "单张图片不能超过12MB")
    extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[content_type]
    root = Path(settings.evidence_root).resolve() / "vision-samples"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{uuid4()}{extension}"
    path.write_bytes(content)
    sample_id = store.add_vision_sample(str(path), parsed, source)
    return {"id": sample_id, "stored": True, "annotation": parsed}
