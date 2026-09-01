from datetime import date, timedelta
from typing import Any

from app.core.config import Settings
from app.devices.ezviz import EzvizClient, EzvizError
from app.sleep.sync import SleepSyncService
from app.store import ProductStore
from app.vision.service import VisionSafetyError, VisionSafetyService
from app.vision.workflow import record_safety_result

SETTING_COMMANDS = {
    "camera_pause": ("camera_paused", "true", "已暂停通道检查。"),
    "camera_resume": ("camera_paused", "false", "已恢复通道检查。"),
    "sleep_pause": ("sleep_alerts_paused", "true", "已暂停睡眠提醒。"),
    "sleep_resume": ("sleep_alerts_paused", "false", "已恢复睡眠提醒。"),
    "care_pause": ("proactive_care_paused", "true", "已暂停主动关怀。"),
    "care_resume": ("proactive_care_paused", "false", "已恢复主动关怀。"),
}


class DeviceToolGateway:
    """Execute registered device tools selected by the assistant brain."""

    def __init__(
        self,
        store: ProductStore,
        settings: Settings,
        ezviz: EzvizClient,
        vision: VisionSafetyService,
        sleep_sync: SleepSyncService,
    ) -> None:
        self.store = store
        self.settings = settings
        self.ezviz = ezviz
        self.vision = vision
        self.sleep_sync = sleep_sync

    def state(self) -> dict[str, Any]:
        settings = self.store.settings()
        return {
            "camera_configured": self.ezviz.configured,
            "sleep_assistant_configured": self.ezviz.sleep_configured,
            "camera_paused": settings.get("camera_paused") == "true",
            "sleep_alerts_paused": settings.get("sleep_alerts_paused") == "true",
            "proactive_care_paused": settings.get("proactive_care_paused") == "true",
        }

    async def execute(self, tool_name: str) -> dict[str, Any]:
        try:
            if tool_name == "inspect_home_safety":
                return await self._inspect_home_safety()
            if tool_name == "camera_status":
                return await self._camera_status()
            if tool_name == "read_latest_sleep":
                return self._read_latest_sleep()
            if tool_name == "sync_latest_sleep":
                synced = await self.sleep_sync.sync_date(date.today() - timedelta(days=1))
                return self._sleep_result(synced.get("sleep"), "已从睡眠助手同步。")
            setting = SETTING_COMMANDS.get(tool_name)
            if setting:
                key, value, summary = setting
                self.store.update_settings({key: value})
                return self._result(tool_name, True, summary)
            return self._result(tool_name, False, "小安暂时没有这个设备工具。")
        except (EzvizError, VisionSafetyError) as exc:
            return self._result(tool_name, False, str(exc))
        except Exception:
            return self._result(tool_name, False, "设备暂时没有响应，请稍后再试。")

    async def _inspect_home_safety(self) -> dict[str, Any]:
        if self.store.settings().get("camera_paused") == "true":
            return self._result(
                "inspect_home_safety", False, "通道检查目前已暂停，请先在隐私设置中恢复。"
            )
        if not self.ezviz.configured:
            return self._result("inspect_home_safety", False, "摄像头尚未连接。")
        result = await self.vision.analyze(self.ezviz)
        recorded = record_safety_result(
            self.store, self.settings, result, source="assistant_device_tool"
        )
        assessment = recorded["assessment"]
        summary = (
            f"我刚刚通过摄像头检查了{self.settings.safety_area_name}。"
            f"{assessment['headline']}。{recorded['reason']}"
        )
        action_text = assessment.get("action_text")
        if action_text:
            summary += f"{action_text}。"
        return self._result(
            "inspect_home_safety",
            True,
            summary,
            {
                "risk_level": assessment["risk_level"],
                "headline": assessment["headline"],
                "reason": recorded["reason"],
                "action_text": action_text,
                "check_id": recorded.get("check_id"),
            },
        )

    async def _camera_status(self) -> dict[str, Any]:
        if not self.ezviz.configured:
            return self._result("camera_status", False, "摄像头尚未配置。")
        info = await self.ezviz.device_info()
        online = str(info.get("status")) == "1"
        summary = "摄像头当前在线。" if online else "摄像头当前离线。"
        return self._result("camera_status", True, summary, {"online": online})

    def _read_latest_sleep(self) -> dict[str, Any]:
        return self._sleep_result(self.store.latest_sleep())

    def _sleep_result(
        self, sleep: dict[str, Any] | None, prefix: str = ""
    ) -> dict[str, Any]:
        if sleep is None:
            return self._result("read_latest_sleep", False, "暂时没有可用的睡眠记录。")
        minutes = int(sleep["duration_minutes"])
        summary = f"{prefix}最近一次睡眠共{minutes // 60}小时{minutes % 60}分钟。"
        if sleep.get("heart_rate") is not None:
            summary += f"平均心率{sleep['heart_rate']}次/分。"
        if sleep.get("respiratory_rate") is not None:
            summary += f"平均呼吸{sleep['respiratory_rate']}次/分。"
        return self._result(
            "read_latest_sleep",
            True,
            summary,
            {
                key: sleep.get(key)
                for key in (
                    "duration_minutes", "heart_rate", "respiratory_rate",
                    "bed_exit_count", "sleep_score", "measured_at",
                )
            },
        )

    @staticmethod
    def _result(
        tool_name: str,
        success: bool,
        summary: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "tool_name": tool_name,
            "success": success,
            "summary": summary,
            "data": data or {},
        }
