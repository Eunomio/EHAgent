from datetime import date, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from app.dependencies import EzvizDep, LlmDep, SettingsDep, StoreDep, VisionSafetyDep
from app.devices.ezviz import EzvizError
from app.vision.service import BaselineMissingError, UnsafeBaselineError, VisionSafetyError
from app.vision.workflow import record_safety_result

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("")
async def device_status(
    ezviz: EzvizDep, settings: SettingsDep
) -> dict[str, Any]:
    c6c: dict[str, Any] = {
        "name": "萤石C6c", "configured": ezviz.configured, "online": None
    }
    if ezviz.configured:
        try:
            info = await ezviz.device_info()
            c6c.update({"online": str(info.get("status")) == "1", "model": info.get("model")})
        except EzvizError as exc:
            c6c["error"] = str(exc)
    return {
        "c6c": c6c,
        "sleep_assistant": {
            "name": settings.sleep_device_name,
            "configured": ezviz.sleep_configured,
            "connection": settings.sleep_provider,
        },
    }


@router.post("/sleep/test")
async def test_sleep_assistant(ezviz: EzvizDep) -> dict[str, Any]:
    try:
        await ezviz.sleep_device_id()
        return {"success": True, "connected": True}
    except EzvizError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/sleep/sync")
async def sync_sleep_assistant(
    ezviz: EzvizDep,
    store: StoreDep,
    llm: LlmDep,
    target_date: date | None = None,
) -> dict[str, Any]:
    """Fetch one EZVIZ sleep day and persist it through the product contract."""

    try:
        summary = await ezviz.sleep_summary_for_date(
            target_date or date.today() - timedelta(days=1)
        )
    except EzvizError as exc:
        raise HTTPException(422, str(exc)) from exc
    record = store.add_sleep(summary)
    copy, source = await llm.analyze_sleep(record, store.sleep_history(7))
    analysis = store.add_llm_output(
        "sleep", record["id"], copy.model_dump(), source, llm.model_name
    )
    return {"success": True, "sleep": record, "analysis": analysis}


@router.post("/c6c/test")
async def test_c6c(ezviz: EzvizDep) -> dict[str, Any]:
    try:
        info = await ezviz.device_info()
        return {"success": True, "online": str(info.get("status")) == "1", "device": info}
    except EzvizError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/c6c/capture")
async def capture_c6c(ezviz: EzvizDep, store: StoreDep) -> dict[str, Any]:
    if store.settings().get("camera_paused") == "true":
        raise HTTPException(409, "摄像头已暂停，请先恢复检查")
    try:
        picture_url = await ezviz.capture()
    except EzvizError as exc:
        raise HTTPException(422, str(exc)) from exc
    check = store.add_safety_check("pending_analysis", "ezviz_c6c", "已取得真实图片，等待模型判断", picture_url)
    return {"success": True, "picture_url": picture_url, "check": check}


@router.post("/c6c/live")
async def live_c6c(ezviz: EzvizDep, store: StoreDep) -> dict[str, Any]:
    if store.settings().get("camera_paused") == "true":
        raise HTTPException(409, "摄像头已暂停，请先恢复检查")
    try:
        stream = await ezviz.live_address()
    except EzvizError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"success": True, **stream}


@router.post("/c6c/sdk-session")
async def c6c_sdk_session(ezviz: EzvizDep, store: StoreDep) -> dict[str, Any]:
    if store.settings().get("camera_paused") == "true":
        raise HTTPException(409, "摄像头已暂停，请先恢复检查")
    try:
        session = await ezviz.sdk_session()
    except EzvizError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"success": True, **session}


@router.get("/c6c/safety/baseline")
def c6c_safety_baseline(vision: VisionSafetyDep) -> dict[str, Any]:
    return vision.baseline_status()


@router.post("/c6c/safety/baseline")
async def set_c6c_safety_baseline(
    ezviz: EzvizDep, store: StoreDep, vision: VisionSafetyDep
) -> dict[str, Any]:
    if store.settings().get("camera_paused") == "true":
        raise HTTPException(409, "摄像头已暂停，请先恢复检查")
    try:
        return await vision.set_baseline(ezviz)
    except UnsafeBaselineError as exc:
        raise HTTPException(409, str(exc)) from exc
    except EzvizError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (httpx.HTTPError, VisionSafetyError) as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/c6c/safety/baseline/invalidate")
def invalidate_c6c_safety_baseline(vision: VisionSafetyDep) -> dict[str, Any]:
    return vision.invalidate_baseline()


@router.get("/c6c/safety/latest")
def latest_c6c_safety(store: StoreDep) -> dict[str, Any]:
    checks = store.recent_checks(1)
    if not checks:
        return {"analysis": None}
    check = checks[0]
    risk_level = check["result"]
    copy = {
        "clear": ("通道畅通", "保持通道整洁"),
        "low": ("通道可以通行", "保持观察即可"),
        "medium": ("通道需要整理", "请将影响通行的物品移到通道外"),
        "high": ("通道通行受阻", "请尽快清理通道"),
        "insufficient": ("暂时看不清通道", "请调整光线后重新检查"),
    }.get(risk_level, ("等待下一次检查", ""))
    task = store.latest_task()
    headline, action_text = copy
    if task and risk_level in {"medium", "high"}:
        headline = task["title"]
        action_text = task["suggestion"]
    return {
        "analysis": {
            "risk_level": risk_level,
            "headline": headline,
            "action_text": action_text,
            "reason": check["detail"],
            "checked_at": check["occurred_at"],
        }
    }


@router.post("/c6c/safety/analyze")
async def analyze_c6c_safety(
    ezviz: EzvizDep,
    store: StoreDep,
    settings: SettingsDep,
    vision: VisionSafetyDep,
) -> dict[str, Any]:
    if store.settings().get("camera_paused") == "true":
        raise HTTPException(409, "摄像头已暂停，请先恢复检查")
    try:
        result = await vision.analyze(ezviz)
    except BaselineMissingError as exc:
        raise HTTPException(409, str(exc)) from exc
    except EzvizError as exc:
        raise HTTPException(422, str(exc)) from exc
    except VisionSafetyError as exc:
        raise HTTPException(502, str(exc)) from exc

    return record_safety_result(store, settings, result)
