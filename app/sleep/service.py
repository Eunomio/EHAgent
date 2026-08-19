from typing import Any

from app.core.config import Settings
from app.llm.service import LlmService
from app.sleep.models import SleepReportIn
from app.store import ProductStore


class SleepDeviceMismatch(ValueError):
    """Raised when a report belongs to another configured device."""


class SleepService:
    def __init__(self, store: ProductStore, llm: LlmService, settings: Settings) -> None:
        self.store = store
        self.llm = llm
        self.settings = settings

    @property
    def configured(self) -> bool:
        provider = self.settings.sleep_provider
        if provider == "ezviz":
            return bool(
                self.settings.sleep_device_serial or self.settings.sleep_device_id
            )
        if provider == "webhook":
            return bool(self.settings.sleep_device_serial)
        return provider == "authorized_export"

    async def ingest(self, report: SleepReportIn) -> dict[str, Any]:
        configured_serial = self.settings.sleep_device_serial.strip()
        incoming_serial = (report.device_serial or "").strip()
        if (
            report.source == "ezviz_sleep_assistant"
            and configured_serial
            and incoming_serial != configured_serial
        ):
            raise SleepDeviceMismatch("睡眠报告来自另一台设备，请检查设备序列号")

        payload = report.model_dump(mode="json")
        if payload["report_date"] is None:
            payload["report_date"] = report.sleep_end.date().isoformat()
        if payload["external_report_id"] is None and incoming_serial:
            payload["external_report_id"] = (
                f"{incoming_serial}:{report.sleep_start.isoformat()}:{report.sleep_end.isoformat()}"
            )
        record = self.store.add_sleep(payload)
        copy, source = await self.llm.analyze_sleep(record, self.store.sleep_history(7))
        analysis = self.store.add_llm_output(
            "sleep", record["id"], copy.model_dump(), source, self.llm.model_name
        )
        return {**record, "analysis": analysis}

    def status(self) -> dict[str, Any]:
        latest = self.store.latest_sleep()
        return {
            "name": self.settings.sleep_device_name,
            "configured": self.configured,
            "connection": self.settings.sleep_provider,
            "serial_configured": bool(self.settings.sleep_device_serial),
            "last_report_at": latest.get("measured_at") if latest else None,
            "last_data_status": latest.get("data_status") if latest else None,
        }
