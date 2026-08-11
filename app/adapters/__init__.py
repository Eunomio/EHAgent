"""Input adapters and their stable contracts."""

from app.adapters.base import (
    AdapterError,
    CameraCapabilities,
    CameraHealth,
    CameraRef,
    CameraSource,
    CapturedFrame,
)
from app.adapters.manual import ManualCameraAdapter
from app.adapters.replay import ReplayCameraAdapter

__all__ = [
    "AdapterError",
    "CameraCapabilities",
    "CameraHealth",
    "CameraRef",
    "CameraSource",
    "CapturedFrame",
    "ManualCameraAdapter",
    "ReplayCameraAdapter",
]
