from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import LlmDep, SettingsDep, StoreDep
from app.sleep.baseline import compare_to_personal_baseline
from app.sleep.night_awakening import waiting_payload

router = APIRouter(prefix="/resident", tags=["resident"])


def resident_sleep(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if record is None:
        return None
    hidden = {"device_serial", "external_report_id"}
    return {key: value for key, value in record.items() if key not in hidden}


class TaskAction(BaseModel):
    action: Literal["done", "later", "need_help", "not_risk", "pause"]


class HelpCreate(BaseModel):
    request_type: Literal["contact", "safety", "sleep"] = "contact"
    message: str = Field(default="希望家人联系我", min_length=1, max_length=300)


class HelpUpdate(BaseModel):
    status: Literal["seen", "contacted", "completed"]


class SettingUpdate(BaseModel):
    camera_paused: bool | None = None
    sleep_alerts_paused: bool | None = None
    contact_name: str | None = Field(default=None, max_length=40)
    contact_phone: str | None = Field(default=None, max_length=30)
    evidence_retention_days: int | None = Field(default=None, ge=1, le=30)
    proactive_care_paused: bool | None = None
    psychological_care_enabled: bool | None = None
    quiet_start: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    quiet_end: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    daily_proactive_limit: int | None = Field(default=None, ge=1, le=5)
    assistant_device_control_consent: Literal["unset", "allowed", "denied"] | None = None


class FeedbackCreate(BaseModel):
    topic: Literal["product", "safety", "sleep", "help", "other"] = "product"
    message: str = Field(min_length=2, max_length=800)


def settings_payload(store: StoreDep) -> dict[str, Any]:
    raw = store.settings()
    return {
        "camera_paused": raw.get("camera_paused") == "true",
        "sleep_alerts_paused": raw.get("sleep_alerts_paused") == "true",
        "contact_name": raw.get("contact_name", "家人"),
        "contact_phone": raw.get("contact_phone", ""),
        "evidence_retention_days": int(raw.get("evidence_retention_days", "7")),
        "proactive_care_paused": raw.get("proactive_care_paused") == "true",
        "psychological_care_enabled": raw.get("psychological_care_enabled", "true") == "true",
        "quiet_start": raw.get("quiet_start", "21:30"),
        "quiet_end": raw.get("quiet_end", "08:00"),
        "daily_proactive_limit": int(raw.get("daily_proactive_limit", "2")),
        "assistant_device_control_consent": raw.get(
            "assistant_device_control_consent", "unset"
        ),
    }


def sleep_alert(history: list[dict[str, Any]]) -> dict[str, str] | None:
    if len(history) < 7:
        return None
    baseline = sorted(item["duration_minutes"] for item in history[:7])[3]
    if all(item["duration_minutes"] < baseline * 0.7 for item in history[:2]):
        return {"title": "最近两晚睡眠时间和平时有些不同", "message": "您今天感觉怎么样？", "severity": "attention"}
    return None


def sleep_sync_payload(
    store: StoreDep, latest: dict[str, Any] | None
) -> dict[str, Any] | None:
    if latest and latest.get("source") == "demo_generated":
        return {
            "status": "success",
            "target_date": latest.get("report_date"),
            "last_success_at": latest.get("received_at"),
            "last_attempt_at": latest.get("received_at"),
            "message": "演示数据已就绪",
        }
    return store.latest_sleep_sync()


def night_awakening_payload(
    store: StoreDep, latest: dict[str, Any] | None
) -> dict[str, Any]:
    if latest is None:
        return waiting_payload(event_interface_verified=False)
    assessment = store.latest_night_awakening(
        source=latest["source"],
        demo_dataset_id=latest.get("demo_dataset_id"),
    )
    if assessment:
        return assessment
    return waiting_payload(
        event_interface_verified=latest.get("bed_exit_status") == "available"
    )


@router.get("/dashboard")
def dashboard(store: StoreDep, settings: SettingsDep) -> dict[str, Any]:
    preferences = settings_payload(store)
    sleep_history = store.sleep_report_history(15)
    sleep = sleep_history[0] if sleep_history else None
    sleep_analysis = store.latest_llm_output("sleep", sleep["id"]) if sleep else None
    task = store.latest_task()
    hour = datetime.now().hour
    greeting = "早上好" if hour < 11 else "下午好" if hour < 18 else "晚上好"
    return {
        "greeting": greeting,
        "subtitle": "今天也安心生活",
        "safety": {
            "status": "paused" if preferences["camera_paused"] else "attention" if task else "ready",
            "headline": "摄像头已暂停" if preferences["camera_paused"] else task["title"] if task else "等待下一次检查",
            "detail": task["suggestion"] if task else f"检查区域：{settings.safety_area_name}",
            "task": task,
        },
        "sleep": {
            "status": "ready" if sleep else "empty",
            "summary": resident_sleep(sleep),
            "analysis": sleep_analysis,
            "baseline": compare_to_personal_baseline(sleep_history),
            "data_source": sleep.get("source") if sleep else None,
            "bed_exit": {
                "count": sleep.get("bed_exit_count") if sleep else None,
                "status": sleep.get("bed_exit_status") if sleep else "unavailable",
            },
            "sync": sleep_sync_payload(store, sleep),
            "night_awakening": night_awakening_payload(store, sleep),
            "headline": (
                f"睡了{sleep['duration_minutes'] // 60}小时{sleep['duration_minutes'] % 60}分钟"
                if sleep
                else "睡眠数据暂未同步"
            ),
        },
        "help": {
            "pending": sum(item["status"] != "completed" for item in store.help_requests()),
            "contact_name": preferences["contact_name"],
            "contact_phone": preferences["contact_phone"],
        },
        "care": {
            "active": store.latest_proactive_event(),
            "paused": preferences["proactive_care_paused"],
            "confirmed_profile_count": len(store.profile_facts(("confirmed",))),
        },
    }


@router.get("/safety")
def safety(store: StoreDep, settings: SettingsDep) -> dict[str, Any]:
    return {
        "area_name": settings.safety_area_name,
        "camera_paused": settings_payload(store)["camera_paused"],
        "task": store.latest_task(),
        "recent_checks": store.recent_checks(),
    }


@router.post("/safety/tasks/{task_id}/actions")
def act_on_task(task_id: str, payload: TaskAction, store: StoreDep) -> dict[str, Any]:
    task = store.act_on_task(task_id, payload.action)
    if task is None:
        raise HTTPException(404, "没有找到这条安全提醒")
    return task


@router.get("/sleep")
def sleep(store: StoreDep, settings: SettingsDep) -> dict[str, Any]:
    history = store.sleep_report_history(15)
    latest = history[0] if history else None
    return {
        "device_name": settings.sleep_device_name,
        "latest": resident_sleep(latest),
        "history": [resident_sleep(item) for item in history],
        "analysis": store.latest_llm_output("sleep", latest["id"]) if latest else None,
        "baseline": compare_to_personal_baseline(history),
        "baseline_ready": len(history) >= 8,
        "alert": sleep_alert(history),
        "alerts_paused": settings_payload(store)["sleep_alerts_paused"],
        "data_source": latest.get("source") if latest else None,
        "bed_exit": {
            "count": latest.get("bed_exit_count") if latest else None,
            "status": latest.get("bed_exit_status") if latest else "unavailable",
        },
        "sync": sleep_sync_payload(store, latest),
        "night_awakening": night_awakening_payload(store, latest),
    }


@router.get("/help")
def help_page(store: StoreDep) -> dict[str, Any]:
    preferences = settings_payload(store)
    return {
        "contact_name": preferences["contact_name"],
        "contact_phone": preferences["contact_phone"],
        "requests": store.help_requests(),
    }


@router.post("/help")
def create_help(payload: HelpCreate, store: StoreDep) -> dict[str, Any]:
    return store.create_help_request(payload.request_type, payload.message)


@router.post("/feedback")
async def create_feedback(
    payload: FeedbackCreate, store: StoreDep, llm: LlmDep
) -> dict[str, Any]:
    digest, source = await llm.summarize_feedback(payload.topic, payload.message)
    return store.create_feedback(
        payload.topic, payload.message, digest.summary, digest.category,
        digest.needs_follow_up, source,
    )


@router.get("/feedback")
def list_feedback(store: StoreDep) -> dict[str, Any]:
    return {"items": store.feedback()}


@router.put("/help/{request_id}")
def update_help(
    request_id: str, payload: HelpUpdate, store: StoreDep
) -> dict[str, Any]:
    request = store.update_help(request_id, payload.status)
    if request is None:
        raise HTTPException(404, "没有找到这条联系请求")
    return request


@router.get("/settings")
def get_settings(store: StoreDep) -> dict[str, Any]:
    return settings_payload(store)


@router.put("/settings")
def update_settings(payload: SettingUpdate, store: StoreDep) -> dict[str, Any]:
    raw = payload.model_dump(exclude_none=True)
    store.update_settings(
        {key: str(value).lower() if isinstance(value, bool) else str(value) for key, value in raw.items()}
    )
    return settings_payload(store)
