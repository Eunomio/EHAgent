from __future__ import annotations

import hashlib
import secrets
from pathlib import Path
from typing import Any

WHITE_NOISE_DIR = Path(__file__).resolve().parent / "white_noise"
SUPPORTED_AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


def white_noise_tracks() -> list[dict[str, Any]]:
    if not WHITE_NOISE_DIR.is_dir():
        return []
    tracks = []
    for path in sorted(WHITE_NOISE_DIR.rglob("*"), key=lambda item: str(item).casefold()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES:
            continue
        relative_path = path.relative_to(WHITE_NOISE_DIR)
        track_id = hashlib.sha256(str(relative_path).encode("utf-8")).hexdigest()[:16]
        tracks.append({
            "id": track_id,
            "name": path.stem.replace("_", " ").strip() or "白噪音",
            "path": path,
        })
    return tracks


def random_white_noise(exclude_id: str | None = None) -> dict[str, Any] | None:
    tracks = white_noise_tracks()
    if not tracks:
        return None
    alternatives = [track for track in tracks if track["id"] != exclude_id]
    candidates = alternatives or tracks
    selected = secrets.choice(candidates)
    return {
        **selected,
        "has_alternative": len(tracks) > 1,
    }


def white_noise_path(track_id: str) -> Path | None:
    return next(
        (track["path"] for track in white_noise_tracks() if track["id"] == track_id),
        None,
    )
