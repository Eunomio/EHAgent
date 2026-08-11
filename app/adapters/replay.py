"""Replay adapter for deterministic local images during commissioning."""

import mimetypes
from datetime import UTC, datetime
from pathlib import Path

from app.adapters.base import (
    AdapterError,
    AdapterErrorCode,
    CameraCapabilities,
    CameraHealth,
    CameraRef,
    CameraSource,
    CapturedFrame,
)
from app.domain.events import CaptureMode, SourceType

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class ReplayCameraAdapter(CameraSource):
    """Read deterministic frames from an explicitly configured local directory."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._cursor = 0

    def _files(self) -> list[Path]:
        if not self._root.exists() or not self._root.is_dir():
            return []
        return sorted(
            path
            for path in self._root.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )

    async def health(self) -> CameraHealth:
        files = self._files()
        status = "ONLINE" if files else "DEGRADED"
        return CameraHealth(
            status=status,
            checked_at=datetime.now(UTC),
            detail=f"{len(files)} replay frame(s) available",
        )

    async def list_cameras(self) -> list[CameraRef]:
        return [
            CameraRef(
                provider="replay",
                device_id="replay-local",
                channel_no=1,
                display_name="Local replay directory",
            )
        ]

    async def get_capabilities(self, camera: CameraRef) -> CameraCapabilities:
        del camera
        return CameraCapabilities(snapshot=True, live_stream=False)

    async def capture_frame(self, camera: CameraRef) -> CapturedFrame:
        del camera
        files = self._files()
        if not files:
            raise AdapterError(
                AdapterErrorCode.SOURCE_EMPTY,
                f"No replay images found under {self._root}",
            )

        path = files[self._cursor % len(files)]
        self._cursor += 1
        now = datetime.now(UTC)
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return CapturedFrame(
            frame_id=f"replay:{path.name}:{self._cursor}",
            captured_at=now,
            received_at=now,
            mime_type=mime_type,
            content=path.read_bytes(),
            source_type=SourceType.REPLAY,
            capture_mode=CaptureMode.FILE,
        )
