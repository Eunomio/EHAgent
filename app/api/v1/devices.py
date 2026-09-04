import base64
import binascii
import json
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.dependencies import (
    EzvizDep,
    LlmDep,
    SettingsDep,
    SleepSyncDep,
    StoreDep,
    VisionSafetyDep,
)
from app.devices.ezviz import EzvizError
from app.sleep.demo import DEMO_DATASET_ID, import_demo_dataset
from app.sleep.night_awakening import assess_night_awakening
from app.vision.service import BaselineMissingError, UnsafeBaselineError, VisionSafetyError
from app.vision.workflow import record_safety_result

router = APIRouter(prefix="/devices", tags=["devices"])


class SafetyFrameIn(BaseModel):
    image_base64: str = Field(min_length=16, max_length=16 * 1024 * 1024)
    preview: bool = False


@router.get("")
async def device_status(
    ezviz: EzvizDep, settings: SettingsDep, store: StoreDep
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
    latest_sleep = store.latest_sleep()
    return {
        "c6c": c6c,
        "sleep_assistant": {
            "name": settings.sleep_device_name,
            "configured": ezviz.sleep_configured,
            "connection": settings.sleep_provider,
            "last_report_at": latest_sleep.get("measured_at") if latest_sleep else None,
            "demo_active": bool(
                latest_sleep and latest_sleep.get("source") == "demo_generated"
            ),
            "demo_dataset_id": (
                latest_sleep.get("demo_dataset_id")
                if latest_sleep and latest_sleep.get("source") == "demo_generated"
                else None
            ),
            "sync": store.latest_sleep_sync(),
        },
    }


@router.post("/sleep/demo")
async def load_sleep_demo(
    store: StoreDep, settings: SettingsDep, llm: LlmDep
) -> dict[str, Any]:
    if settings.app_env == "production":
        raise HTTPException(403, "生产环境不能导入演示睡眠数据")
    records = import_demo_dataset(store)
    latest = records[-1]
    copy, source = await llm.analyze_sleep(latest, records[-2::-1][:7])
    store.add_llm_output(
        "sleep", latest["id"], copy.model_dump(), source, llm.model_name
    )
    event = store.create_proactive_event(
        event_type="sleep_change",
        title="小安想了解一下您昨晚的休息",
        message="我发现您昨天半夜醒了以后，过了好久才睡着，是发生什么事了吗？",
        reason="睡眠助手发现第4、5晚起夜后约1小时才再次入睡",
        source="demo_generated",
        source_ref=str(records[4]["id"]),
        priority="high",
        context={"script_id": "sleep_return_delay_v1", "dataset_id": DEMO_DATASET_ID},
    )
    return {
        "success": True,
        "dataset_id": DEMO_DATASET_ID,
        "imported": len(records),
        "latest": latest,
        "proactive_event": event,
    }


@router.delete("/sleep/demo")
def clear_sleep_demo(store: StoreDep, settings: SettingsDep) -> dict[str, Any]:
    if settings.app_env == "production":
        raise HTTPException(403, "生产环境不能清除演示睡眠数据")
    return {
        "success": True,
        "dataset_id": DEMO_DATASET_ID,
        "deleted": store.delete_demo_sleep(DEMO_DATASET_ID),
    }


@router.post("/sleep/demo/night-awakening")
def activate_demo_night_awakening(
    store: StoreDep, settings: SettingsDep
) -> dict[str, Any]:
    if settings.app_env == "production":
        raise HTTPException(403, "生产环境不能激活演示起夜关注")
    history = store.sleep_report_history(15)
    latest = history[0] if history else None
    if (
        latest is None
        or latest.get("source") != "demo_generated"
        or latest.get("demo_dataset_id") != DEMO_DATASET_ID
    ):
        raise HTTPException(409, "请先导入7晚睡眠数据")
    assessment = assess_night_awakening(
        history,
        detected_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        event_source="demo_generated",
        event_reliable=True,
        snapshot_status="provisional",
        sleep_session_ended=True,
    )
    return {"success": True, "night_awakening": store.add_night_awakening(assessment)}


@router.delete("/sleep/demo/night-awakening")
def reset_demo_night_awakening(
    store: StoreDep, settings: SettingsDep
) -> dict[str, Any]:
    if settings.app_env == "production":
        raise HTTPException(403, "生产环境不能重置演示起夜关注")
    return {
        "success": True,
        "dataset_id": DEMO_DATASET_ID,
        "deleted": store.delete_demo_night_awakening(DEMO_DATASET_ID),
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
    sleep_sync: SleepSyncDep,
    target_date: date | None = None,
) -> dict[str, Any]:
    """Fetch one EZVIZ sleep day and persist it through the product contract."""

    try:
        return await sleep_sync.sync_date(target_date or date.today() - timedelta(days=1))
    except EzvizError as exc:
        raise HTTPException(422, str(exc)) from exc


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
    try:
        stored = json.loads(check.get("analysis_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        stored = {}
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
            "check_id": check["id"],
            "hazard_regions": stored.get("hazard_regions", []),
            "notification_required": bool(stored.get("notification_required")),
            "speech_auto_play": bool(stored.get("speech_auto_play")),
            "speech_url": (
                f"/api/v1/devices/c6c/safety/{check['id']}/speech"
                if risk_level in {"medium", "high"}
                else None
            ),
        }
    }


@router.get("/c6c/safety/{check_id}/speech")
async def c6c_safety_speech(
    check_id: str,
    store: StoreDep,
    vision: VisionSafetyDep,
) -> Response:
    check = store.safety_check(check_id)
    if not check:
        raise HTTPException(404, "没有找到这次通道检查")
    if check["result"] not in {"medium", "high"}:
        raise HTTPException(409, "本次检查无需语音提醒")
    task = store.latest_task()
    headline = task["title"] if task else "通道需要整理"
    suggestion = task["suggestion"] if task else "请将影响通行的物品移到通道外"
    text = f"{headline}。{check['detail']}。{suggestion}。"
    try:
        audio = await vision.warning_audio(check_id, text)
    except (httpx.HTTPError, OSError, VisionSafetyError) as exc:
        raise HTTPException(503, "语音提醒暂时不可用") from exc
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


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


@router.post("/c6c/safety/analyze-frame")
async def analyze_c6c_safety_frame(
    payload: SafetyFrameIn,
    store: StoreDep,
    settings: SettingsDep,
    vision: VisionSafetyDep,
) -> dict[str, Any]:
    if store.settings().get("camera_paused") == "true":
        raise HTTPException(409, "摄像头已暂停，请先恢复检查")
    try:
        image = base64.b64decode(payload.image_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, "当前画面数据无效") from exc
    if len(image) > 12 * 1024 * 1024:
        raise HTTPException(413, "单张图片不能超过12MB")
    try:
        result = await vision.analyze_image(image, "image/jpeg")
    except BaselineMissingError as exc:
        raise HTTPException(409, str(exc)) from exc
    except VisionSafetyError as exc:
        raise HTTPException(502, str(exc)) from exc

    if payload.preview:
        return {
            **result,
            "notification_required": False,
            "speech_auto_play": False,
            "recheck": False,
            "check_id": None,
            "task_id": None,
        }
    return record_safety_result(store, settings, result)
