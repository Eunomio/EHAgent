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
