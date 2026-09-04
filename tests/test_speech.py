import asyncio

import httpx

from app.core.config import Settings
from app.speech.service import SpeechTranscriptionError, SpeechTranscriptionService


def test_transcription_uses_configured_audio_endpoint() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/audio/transcriptions"
            assert request.headers["Authorization"] == "Bearer asr-key"
            body = request.read()
            assert b'filename="voice.m4a"' in body
            assert b'name="model"' in body
            assert b"whisper-test" in body
            return httpx.Response(200, json={"text": "今天天气很好"})

        settings = Settings(
            asr_enabled=True,
            asr_api_key="asr-key",
            asr_model="whisper-test",
            asr_api_base="https://example.test/v1",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = SpeechTranscriptionService(settings, client)
            text = await service.transcribe(b"a" * 1024, "audio/mp4")
        assert text == "今天天气很好"

    asyncio.run(scenario())


def test_transcription_rejects_unconfigured_service() -> None:
    async def scenario() -> None:
        service = SpeechTranscriptionService(Settings(asr_enabled=False))
        try:
            try:
                await service.transcribe(b"a" * 1024, "audio/mp4")
            except SpeechTranscriptionError as exc:
                assert str(exc) == "语音输入服务暂未配置"
            else:
                raise AssertionError("expected SpeechTranscriptionError")
        finally:
            await service.close()

    asyncio.run(scenario())


def test_transcription_rejects_short_audio() -> None:
    async def scenario() -> None:
        service = SpeechTranscriptionService(
            Settings(
                asr_enabled=True,
                asr_api_key="asr-key",
                asr_api_base="https://example.test/v1",
            )
        )
        try:
            try:
                await service.transcribe(b"short", "audio/mp4")
            except ValueError as exc:
                assert "太短" in str(exc)
            else:
                raise AssertionError("expected ValueError")
        finally:
            await service.close()

    asyncio.run(scenario())
