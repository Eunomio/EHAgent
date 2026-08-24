import asyncio
import logging
import time

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

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.vlm_auto_check_enabled
            and self.vision.configured
            and self.ezviz.configured
        )

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self.settings.vlm_change_poll_seconds)
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

        marker = str(baseline.get("captured_at") or "")
        if self.reference is None or marker != self.baseline_marker:
            baseline_image = (self.vision.root / "baseline.jpg").read_bytes()
            self.reference = self.vision.image_signature(baseline_image)
            self.baseline_marker = marker
            self.candidate = None
            self.confirmations = 0

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
        if self.confirmations < self.settings.vlm_change_confirmations:
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
