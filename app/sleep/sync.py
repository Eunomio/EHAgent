"""Idempotent EZVIZ sleep synchronization and daily scheduling."""

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from app.core.config import Settings
from app.devices.ezviz import EzvizClient, EzvizError
from app.llm.service import LlmService
from app.store import ProductStore


class SleepSyncService:
    def __init__(
        self,
        settings: Settings,
        ezviz: EzvizClient,
        store: ProductStore,
        llm: LlmService,
    ) -> None:
        self.settings = settings
        self.ezviz = ezviz
        self.store = store
        self.llm = llm

    async def sync_date(self, target_date: date) -> dict[str, Any]:
        run_id = self.store.start_sleep_sync(target_date.isoformat(), "ezviz_sleep_assistant")
        try:
            summary = await self.ezviz.sleep_summary_for_date(target_date)
            bed_events = list(summary.pop("bed_events", []))
            record = self.store.add_sleep(summary)
            serial = str(record.get("device_serial") or "")
            if serial and record.get("bed_exit_status") == "available":
                self.store.replace_sleep_bed_events(record["id"], serial, bed_events)
            history = self.store.sleep_history(7, exclude_demo=True)
            copy, source = await self.llm.analyze_sleep(record, history)
            analysis = self.store.add_llm_output(
                "sleep", record["id"], copy.model_dump(), source, self.llm.model_name
            )
        except EzvizError as exc:
            self.store.finish_sleep_sync(run_id, "failed", str(exc), "ezviz_error")
            raise
        except Exception as exc:
            self.store.finish_sleep_sync(run_id, "failed", "睡眠同步暂时失败", type(exc).__name__)
            raise
        self.store.finish_sleep_sync(run_id, "success", "睡眠数据已同步")
        return {"success": True, "sleep": record, "analysis": analysis}

    async def run(self) -> None:
        if not self.settings.sleep_auto_sync_enabled or not self.ezviz.sleep_configured:
            return
        today = self._now().date()
        for days_ago in range(self.settings.sleep_sync_lookback_days, 0, -1):
            try:
                await self.sync_date(today - timedelta(days=days_ago))
            except Exception:
                continue
        while True:
            now = self._now()
            next_run = datetime.combine(
                now.date(),
                time(self.settings.sleep_sync_hour, self.settings.sleep_sync_minute),
                tzinfo=now.tzinfo,
            )
            if next_run <= now:
                next_run += timedelta(days=1)
            await asyncio.sleep((next_run - now).total_seconds())
            try:
                await self.sync_date(next_run.date() - timedelta(days=1))
            except Exception:
                continue

    def _now(self) -> datetime:
        zone = timezone(timedelta(hours=self.settings.sleep_sync_utc_offset_hours))
        return datetime.now(zone)
