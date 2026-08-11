"""Stable camera-source contract used by current and future providers."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.events import CaptureMode, SourceType


class AdapterErrorCode(StrEnum):
    """Provider-independent error categories."""

    NOT_CONFIGURED = "NOT_CONFIGURED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    DEVICE_OFFLINE = "DEVICE_OFFLINE"
    CAPABILITY_UNSUPPORTED = "CAPABILITY_UNSUPPORTED"
    SOURCE_EMPTY = "SOURCE_EMPTY"
    INVALID_FRAME = "INVALID_FRAME"
    TIMEOUT = "TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AdapterError(RuntimeError):
    """Adapter failure safe to map into an internal API error."""

    def __init__(self, code: AdapterErrorCode, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class CameraRef:
    """Internal camera reference containing no provider credentials."""

    provider: str
    device_id: str
    channel_no: int
    display_name: str


@dataclass(frozen=True, slots=True)
class CameraCapabilities:
    """Capabilities verified for a concrete camera binding."""

    snapshot: bool
    live_stream: bool
    event_push: bool = False
    playback: bool = False
    ptz: bool = False


@dataclass(frozen=True, slots=True)
class CameraHealth:
    """Normalized adapter and device health."""

    status: str
    checked_at: datetime
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    """Single frame crossing the adapter boundary."""

    frame_id: str
    captured_at: datetime
    received_at: datetime
    mime_type: str
    content: bytes
    source_type: SourceType
    capture_mode: CaptureMode
    width: int | None = None
    height: int | None = None
    provider_trace_id: str | None = None


class CameraSource(ABC):
    """Abstract camera input independent from vendor SDKs and response objects."""

    @abstractmethod
    async def health(self) -> CameraHealth:
        """Return normalized source health."""

    @abstractmethod
    async def list_cameras(self) -> list[CameraRef]:
        """List cameras visible to this adapter."""

    @abstractmethod
    async def get_capabilities(self, camera: CameraRef) -> CameraCapabilities:
        """Return capabilities verified for a camera."""

    @abstractmethod
    async def capture_frame(self, camera: CameraRef) -> CapturedFrame:
        """Capture one frame."""

    async def frames(self, camera: CameraRef) -> AsyncIterator[CapturedFrame]:
        """Yield frames when a provider supports streaming."""

        del camera
        raise AdapterError(
            AdapterErrorCode.CAPABILITY_UNSUPPORTED,
            "This camera source does not provide a live stream",
        )
        yield  # pragma: no cover

    async def close(self) -> None:
        """Release resources. Stateless adapters need no special action."""

        return None
