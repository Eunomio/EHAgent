import asyncio
from urllib.parse import parse_qs

import httpx

from app.core.config import Settings
from app.devices.ezviz import EzvizClient


def test_live_address_uses_short_lived_hls_without_returning_credentials() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/lapp/v2/live/address/get"
            form = parse_qs(request.content.decode())
            assert form["accessToken"] == ["test-token"]
            assert form["deviceSerial"] == ["C6C123"]
            assert form["channelNo"] == ["1"]
            assert form["protocol"] == ["2"]
            assert form["expireTime"] == ["1800"]
            assert form["code"] == ["ABCDEF"]
            return httpx.Response(
                200,
                json={
                    "code": "200",
                    "data": {"url": "https://example.test/live/index.m3u8"},
                },
            )

        settings = Settings(
            ezviz_access_token="test-token",
            ezviz_device_serial="C6C123",
            ezviz_verify_code="ABCDEF",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = EzvizClient(settings, client)
            result = await service.live_address()
        assert result == {
            "url": "https://example.test/live/index.m3u8",
            "protocol": "hls",
            "expires_in": 1800,
        }
        assert "test-token" not in result
        assert "ABCDEF" not in result

    asyncio.run(scenario())


def test_sdk_session_keeps_app_secret_on_backend() -> None:
    async def scenario() -> None:
        settings = Settings(
            ezviz_app_key="test-app-key",
            ezviz_app_secret="server-only-secret",
            ezviz_access_token="test-token",
            ezviz_device_serial="C6C123",
            ezviz_channel_no=1,
            ezviz_verify_code="ABCDEF",
        )
        service = EzvizClient(settings)
        try:
            result = await service.sdk_session()
        finally:
            await service.close()

        assert result == {
            "app_key": "test-app-key",
            "access_token": "test-token",
            "device_serial": "C6C123",
            "channel_no": 1,
            "verify_code": "ABCDEF",
        }
        assert "app_secret" not in result
        assert "server-only-secret" not in result.values()

    asyncio.run(scenario())
