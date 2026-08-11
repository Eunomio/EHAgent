"""Manual camera adapter for explicit engineering fixtures and error paths."""

from datetime import UTC, datetime

from app.adapters.base import (
    AdapterError,
    AdapterErrorCode,
    CameraCapabilities,
    CameraHealth,
    CameraRef,
    CameraSource,
    CapturedFrame,
)


class ManualCameraAdapter(CameraSource):
    """Return a frame supplied explicitly by a test or engineering tool."""

    def __init__(self) -> None:
        self._frame: CapturedFrame | None = None

    def set_frame(self, frame: CapturedFrame) -> None:
        """Set the next deterministic frame without pretending it is real-device data."""

        self._frame = frame

    async def health(self) -> CameraHealth:
        status = "ONLINE" if self._frame is not None else "DEGRADED"
        detail = "manual frame configured" if self._frame is not None else "no manual frame"
        return CameraHealth(status=status, checked_at=datetime.now(UTC), detail=detail)

    async def list_cameras(self) -> list[CameraRef]:
        return [
            CameraRef(
                provider="manual",
                device_id="manual-local",
                channel_no=1,
                display_name="Manual engineering source",
            )
        ]

    async def get_capabilities(self, camera: CameraRef) -> CameraCapabilities:
        del camera
        return CameraCapabilities(snapshot=True, live_stream=False)

    async def capture_frame(self, camera: CameraRef) -> CapturedFrame:
        del camera
        if self._frame is None:
            raise AdapterError(
                AdapterErrorCode.SOURCE_EMPTY,
                "No manual frame has been configured",
            )
        return self._frame
