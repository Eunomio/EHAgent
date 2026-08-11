"""Camera adapter contract tests."""

import asyncio
from datetime import UTC, datetime

import pytest

from app.adapters.base import AdapterError, CameraRef, CapturedFrame
from app.adapters.manual import ManualCameraAdapter
from app.adapters.replay import ReplayCameraAdapter
from app.domain.events import CaptureMode, SourceType


def test_replay_adapter_reads_deterministic_local_frame(tmp_path: pytest.TempPathFactory) -> None:
    replay_root = tmp_path / "replay"
    replay_root.mkdir()
    expected = b"not-a-real-image-yet"
    (replay_root / "safe_001.jpg").write_bytes(expected)
    adapter = ReplayCameraAdapter(replay_root)
    camera = asyncio.run(adapter.list_cameras())[0]

    frame = asyncio.run(adapter.capture_frame(camera))

    assert frame.content == expected
    assert frame.source_type is SourceType.REPLAY
    assert frame.capture_mode is CaptureMode.FILE


def test_replay_adapter_rejects_empty_source(tmp_path: pytest.TempPathFactory) -> None:
    adapter = ReplayCameraAdapter(tmp_path)
    camera = asyncio.run(adapter.list_cameras())[0]

    with pytest.raises(AdapterError):
        asyncio.run(adapter.capture_frame(camera))


def test_manual_adapter_requires_explicit_frame() -> None:
    adapter = ManualCameraAdapter()
    camera = CameraRef("manual", "manual-local", 1, "Manual")
    with pytest.raises(AdapterError):
        asyncio.run(adapter.capture_frame(camera))

    now = datetime.now(UTC)
    expected = CapturedFrame(
        frame_id="fixture-1",
        captured_at=now,
        received_at=now,
        mime_type="image/jpeg",
        content=b"fixture",
        source_type=SourceType.MANUAL,
        capture_mode=CaptureMode.FILE,
    )
    adapter.set_frame(expected)
    assert asyncio.run(adapter.capture_frame(camera)) == expected
