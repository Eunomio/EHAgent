from typing import Any

import httpx

from app.core.config import Settings


class SpeechTranscriptionError(RuntimeError):
    """A resident-facing speech transcription failure."""


class SpeechTranscriptionService:
    def __init__(
        self, settings: Settings, client: httpx.AsyncClient | None = None
    ) -> None:
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=settings.asr_timeout_seconds)
        self._owns_client = client is None

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.asr_enabled
            and self.settings.asr_api_key
            and self.settings.asr_model
            and self.settings.asr_api_base
        )

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def transcribe(self, audio: bytes, content_type: str) -> str:
        if not self.configured:
            raise SpeechTranscriptionError("语音输入服务暂未配置")
        if len(audio) < 512:
            raise ValueError("录音时间太短，请重新说一次")
        if len(audio) > self.settings.asr_max_audio_bytes:
            raise ValueError("录音时间过长，请分开说")

        extension = {
            "audio/mp4": "m4a",
            "audio/m4a": "m4a",
            "audio/aac": "aac",
            "audio/wav": "wav",
        }.get(content_type.split(";", 1)[0].lower(), "m4a")
        try:
            response = await self.client.post(
                f"{self.settings.asr_api_base.rstrip('/')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.settings.asr_api_key}"},
                data={
                    "model": self.settings.asr_model,
                    "language": self.settings.asr_language,
                    "response_format": "json",
                },
                files={"file": (f"voice.{extension}", audio, content_type)},
                timeout=self.settings.asr_timeout_seconds,
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SpeechTranscriptionError("语音暂时没有识别出来，请稍后再试") from exc

        text = str(payload.get("text", "")).strip()
        if not text:
            raise SpeechTranscriptionError("没有听清，请靠近手机再说一次")
        return text[:1000]
