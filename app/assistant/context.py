from datetime import datetime
from typing import Any

from app.core.config import Settings
from app.store import ProductStore


class ResidentContextBuilder:
    """Build a small, factual snapshot for one assistant turn."""

    def __init__(self, store: ProductStore, settings: Settings) -> None:
        self.store = store
        self.settings = settings

    def build(self) -> tuple[dict[str, Any], list[str]]:
        context: dict[str, Any] = {
            "current_time": datetime.now().astimezone().isoformat(timespec="minutes"),
        }
        used = ["当前日期和时间"]

        if self.settings.assistant_location:
            context["location"] = self.settings.assistant_location
            used.append("所在地区")

        sleep = self.store.latest_sleep()
        if sleep:
            context["latest_sleep"] = {
                key: sleep.get(key)
                for key in (
                    "sleep_start", "sleep_end", "duration_minutes", "respiratory_rate",
                    "heart_rate", "bed_exit_count", "quality", "sleep_score",
                    "awake_minutes", "light_sleep_minutes", "deep_sleep_minutes",
                    "rem_sleep_minutes", "measured_at",
                )
            }
            used.append("最近一次睡眠摘要")

        task = self.store.latest_task()
        if task:
            context["open_safety_task"] = {
                key: task.get(key)
                for key in ("title", "location", "explanation", "suggestion", "status", "updated_at")
            }
            used.append("待处理的居家安全提醒")

        settings = self.store.settings()
        context["product_state"] = {
            "camera_paused": settings.get("camera_paused") == "true",
            "sleep_alerts_paused": settings.get("sleep_alerts_paused") == "true",
            "contact_name": settings.get("contact_name") or "家人",
            "camera_configured": bool(self.settings.ezviz_device_serial),
            "sleep_device_configured": (
                self.settings.sleep_provider == "authorized_export"
                or (
                    self.settings.sleep_provider in {"webhook", "ezviz_webhook"}
                    and bool(self.settings.sleep_device_serial)
                )
            ),
        }
        used.append("设备与提醒状态")
        return context, used
