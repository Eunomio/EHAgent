import asyncio
import logging
import time
from collections import deque
from typing import Any

import httpx

from app.core.config import Settings
from app.devices.ezviz import EzvizClient, EzvizError
from app.store import ProductStore
from app.vision.service import UnsafeBaselineError, VisionSafetyError, VisionSafetyService
from app.vision.workflow import record_safety_result

logger = logging.getLogger(__name__)


class VisionChangeMonitor:
    def __init__(
        self,
        settings: Settings,
        ezviz: EzvizClient,
        vision: VisionSafetyService,
        store: ProductStore,
    ) -> None:
        self.settings = settings
        self.ezviz = ezviz
        self.vision = vision
        self.store = store
        self.baseline_marker: str | None = None
        self.reference: tuple[int, ...] | None = None
        self.candidate: tuple[int, ...] | None = None
        self.confirmations = 0
        self.next_baseline_attempt_at = 0.0
        self.alarm_cursor_ms = int(time.time() * 1000)
        self.next_alarm_poll_at = 0.0
        self.next_local_check_at = 0.0
        self.pending_alarm_at: float | None = None
        self.alarm_api_healthy = False
        self.last_alarm_warning_at = float("-inf")
        self.seen_alarm_ids: set[str] = set()
        self.seen_alarm_order: deque[str] = deque()

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.vlm_auto_check_enabled
            and self.vision.configured
            and self.ezviz.configured
        )

    async def run(self) -> None:
        while True:
            interval = (
                1.0
                if self.settings.ezviz_alarm_detection_enabled
                else self.settings.vlm_change_poll_seconds
            )
            await asyncio.sleep(interval)
            try:
                analyzed = await self.check_once()
                if analyzed:
                    await asyncio.sleep(self.settings.vlm_change_cooldown_seconds)
            except asyncio.CancelledError:
                raise
            except (EzvizError, VisionSafetyError, httpx.HTTPError, OSError, ValueError):
                logger.warning("automatic camera safety check failed", exc_info=True)

    async def check_once(self) -> bool:
        if not self.enabled or self.store.settings().get("camera_paused") == "true":
            self._reset()
            return False
        baseline = self.vision.baseline_status()
        if not baseline["ready"]:
            self._reset()
            now = time.monotonic()
            if now < self.next_baseline_attempt_at:
                return False
            try:
                await self.vision.set_baseline(self.ezviz)
                logger.info("camera walkway reference identified automatically")
            except UnsafeBaselineError:
                logger.info("camera walkway reference is not ready for automatic setup")
            finally:
                if self.vision.baseline_status()["ready"]:
                    self.next_baseline_attempt_at = 0.0
                else:
                    self.next_baseline_attempt_at = time.monotonic() + 60
            return False
        self.next_baseline_attempt_at = 0.0
        if self.vision.analysis_lock.locked():
            return False

        self._ensure_reference(baseline)
        event_trigger = False
        if self.settings.ezviz_alarm_detection_enabled:
            event_trigger, local_fallback = await self._alarm_decision()
            if not event_trigger and not local_fallback:
                return False
        else:
            local_fallback = True

        now = time.monotonic()
        if local_fallback:
            fallback_interval = (
                self.settings.ezviz_alarm_fallback_seconds
                if self.alarm_api_healthy
                else self.settings.vlm_change_poll_seconds
            )
            self.next_local_check_at = now + fallback_interval

        analyzed = await self._check_current_frame(
            required_confirmations=1 if event_trigger else self.settings.vlm_change_confirmations
        )
        if local_fallback and not analyzed and self.confirmations > 0:
            self.next_local_check_at = now + self.settings.vlm_change_poll_seconds
        return analyzed

    def _ensure_reference(self, baseline: dict[str, object]) -> None:
        marker = str(baseline.get("captured_at") or "")
        if self.reference is None or marker != self.baseline_marker:
            baseline_image = (self.vision.root / "baseline.jpg").read_bytes()
            self.reference = self.vision.image_signature(baseline_image)
            self.baseline_marker = marker
            self.candidate = None
            self.confirmations = 0

    async def _alarm_decision(self) -> tuple[bool, bool]:
        """Return ``(event_trigger, local_fallback_due)`` for this loop."""

        now = time.monotonic()
        if now >= self.next_alarm_poll_at:
            self.next_alarm_poll_at = now + self.settings.ezviz_alarm_poll_seconds
            end_ms = int(time.time() * 1000)
            start_ms = max(self.alarm_cursor_ms - 5_000, end_ms - 7 * 24 * 60 * 60 * 1000)
            try:
                alarms = await self.ezviz.alarm_list(start_ms, end_ms)
                self.alarm_cursor_ms = end_ms
                self.alarm_api_healthy = True
                if self.next_local_check_at == 0.0:
                    self.next_local_check_at = now + self.settings.ezviz_alarm_fallback_seconds
                new_alarm = False
                for alarm in alarms:
                    new_alarm = self._remember_new_alarm(alarm) or new_alarm
                if new_alarm:
                    # Extend the deadline when more movement arrives so the captured
                    # frame represents the settled room instead of a moving person.
                    self.pending_alarm_at = now + self.settings.ezviz_alarm_settle_seconds
            except (EzvizError, httpx.HTTPError, OSError, ValueError):
                if now - self.last_alarm_warning_at >= 60:
                    logger.warning(
                        "EZVIZ alarm detection unavailable; using local image fallback",
                        exc_info=True,
                    )
                    self.last_alarm_warning_at = now
                self.alarm_api_healthy = False
                self.next_alarm_poll_at = now + 15
                self.next_local_check_at = min(self.next_local_check_at or now, now)

        if self.pending_alarm_at is not None and now >= self.pending_alarm_at:
            self.pending_alarm_at = None
            self.next_local_check_at = now + self.settings.ezviz_alarm_fallback_seconds
            return True, False
        return False, now >= self.next_local_check_at

    def _remember_new_alarm(self, alarm: dict[str, Any]) -> bool:
        serial = str(alarm.get("deviceSerial") or alarm.get("deviceSeril") or "")
        if serial and serial.upper() != self.settings.ezviz_device_serial.upper():
            return False
        channel = alarm.get("channelNo", alarm.get("cameraNo", alarm.get("channelID")))
        if channel not in {None, ""}:
            try:
                if int(str(channel)) != self.settings.ezviz_channel_no:
                    return False
            except (TypeError, ValueError):
                return False
        alarm_id = str(
            alarm.get("alarmId")
            or alarm.get("alarmID")
            or f"{alarm.get('alarmStart')}:{alarm.get('alarmType')}:{alarm.get('alarmPicUrl')}"
        )
        if alarm_id in self.seen_alarm_ids:
            return False
        if len(self.seen_alarm_order) >= 256:
            self.seen_alarm_ids.discard(self.seen_alarm_order.popleft())
        self.seen_alarm_ids.add(alarm_id)
        self.seen_alarm_order.append(alarm_id)
        return True

    async def _check_current_frame(self, required_confirmations: int) -> bool:
        picture_url = await self.ezviz.capture()
        image, content_type = await self.ezviz.download_picture(picture_url)
        self.vision._validate_image(image, content_type)
        signature = self.vision.image_signature(image)
        reference = self.reference
        if reference is None:
            self.reference = signature
            return False

        threshold = self.settings.vlm_change_threshold
        if self.vision.signature_difference(reference, signature) < threshold:
            self.candidate = None
            self.confirmations = 0
            return False

        if (
            self.candidate is None
            or self.vision.signature_difference(self.candidate, signature) >= threshold / 2
        ):
            self.candidate = signature
            self.confirmations = 1
        else:
            self.confirmations += 1
        if self.confirmations < required_confirmations:
            return False

        result = await self.vision.analyze_image(image, content_type)
        record_safety_result(
            self.store,
            self.settings,
            result,
            source="camera_safety_auto",
        )
        self.reference = signature
        self.candidate = None
        self.confirmations = 0
        return True

    def _reset(self) -> None:
        self.baseline_marker = None
        self.reference = None
        self.candidate = None
        self.confirmations = 0
        self.pending_alarm_at = None
        self.next_local_check_at = 0.0
        self.alarm_cursor_ms = int(time.time() * 1000)
        self.next_alarm_poll_at = 0.0
        self.alarm_api_healthy = False
