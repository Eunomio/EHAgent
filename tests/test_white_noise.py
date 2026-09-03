from pathlib import Path

from app.care import white_noise


def _add_track(folder: Path, name: str, content: bytes) -> None:
    (folder / name).write_bytes(content)


def test_white_noise_library_filters_supported_audio(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(white_noise, "WHITE_NOISE_DIR", tmp_path)
    _add_track(tmp_path, "雨声.mp3", b"first-audio")
    nested = tmp_path / "柔和"
    nested.mkdir()
    _add_track(nested, "风扇声.wav", b"second-audio")
    _add_track(tmp_path, "说明.txt", b"not-audio")

    response = client.get("/api/v1/resident/care/white-noise/tracks")
    assert response.status_code == 200
    assert {item["name"] for item in response.json()["items"]} == {"雨声", "风扇声"}


def test_switch_white_noise_excludes_current_track(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(white_noise, "WHITE_NOISE_DIR", tmp_path)
    _add_track(tmp_path, "雨声.mp3", b"first-audio")
    _add_track(tmp_path, "风扇声.wav", b"second-audio")

    first = client.get("/api/v1/resident/care/white-noise/random").json()
    switched = client.get(
        "/api/v1/resident/care/white-noise/random",
        params={"exclude": first["id"]},
    ).json()
    assert switched["id"] != first["id"]
    assert switched["has_alternative"] is True

    audio = client.get(switched["audio_url"])
    assert audio.status_code == 200
    assert audio.content in {b"first-audio", b"second-audio"}


def test_empty_white_noise_library_returns_clear_error(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(white_noise, "WHITE_NOISE_DIR", tmp_path)
    response = client.get("/api/v1/resident/care/white-noise/random")
    assert response.status_code == 404
    assert "素材库" in response.json()["detail"]
