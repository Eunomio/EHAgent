from fastapi import APIRouter, HTTPException

from app.dependencies import EzvizDep, SettingsDep, StoreDep
from app.devices.ezviz import EzvizError

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("")
async def device_status(ezviz: EzvizDep, settings: SettingsDep) -> dict:
    c6c: dict = {"name": "萤石C6c", "configured": ezviz.configured, "online": None}
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
            "configured": settings.sleep_provider != "disabled",
            "connection": settings.sleep_provider,
        },
    }


@router.post("/c6c/test")
async def test_c6c(ezviz: EzvizDep) -> dict:
    try:
        info = await ezviz.device_info()
        return {"success": True, "online": str(info.get("status")) == "1", "device": info}
    except EzvizError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/c6c/capture")
async def capture_c6c(ezviz: EzvizDep, store: StoreDep) -> dict:
    if store.settings().get("camera_paused") == "true":
        raise HTTPException(409, "摄像头已暂停，请先恢复检查")
    try:
        picture_url = await ezviz.capture()
    except EzvizError as exc:
        raise HTTPException(422, str(exc)) from exc
    check = store.add_safety_check("pending_analysis", "ezviz_c6c", "已取得真实图片，等待模型判断", picture_url)
    return {"success": True, "picture_url": picture_url, "check": check}
