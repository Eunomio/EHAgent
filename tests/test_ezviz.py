import asyncio
from datetime import date
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
            ezviz_auto_token=False,
            ezviz_app_key="",
            ezviz_app_secret="",
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
            ezviz_auto_token=False,
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


def test_sleep_device_id_uses_server_token_without_returning_identifier() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/service/sleepDetector/v3/third/huayi/deviceId"
            assert request.headers["accessToken"] == "test-token"
            assert request.url.params["deviceCode"] == "SLEEP123"
            return httpx.Response(200, json={"data": "internal-device-id", "meta": {"code": 200}})

        settings = Settings(
            ezviz_access_token="test-token",
            ezviz_auto_token=False,
            ezviz_app_key="",
            ezviz_app_secret="",
            sleep_provider="ezviz",
            sleep_device_serial="SLEEP123",
            sleep_device_id="",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = EzvizClient(settings, client)
            assert await service.sleep_device_id() == "internal-device-id"

    asyncio.run(scenario())


def test_sleep_device_id_uses_configured_id_without_network_request() -> None:
    settings = Settings(
        sleep_provider="ezviz",
        sleep_device_id="known-device-id",
        ezviz_access_token="test-token",
        ezviz_auto_token=False,
        ezviz_app_key="",
        ezviz_app_secret="",
    )
    service = EzvizClient(settings)
    assert asyncio.run(service.sleep_device_id()) == "known-device-id"


def test_sleep_summary_maps_daily_statistics_to_product_contract() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["accessToken"] == "test-token"
            assert request.url.params["deviceId"] == "known-device-id"
            assert request.url.params["date"] == "2026-08-13"
            if request.url.path.endswith("/daily/sleep"):
                return httpx.Response(200, json={"code": 200, "data": {"score": 88, "list": [], "items": []}})
            if request.url.path.endswith("/daily/average/hearts"):
                return httpx.Response(200, json={"code": 200, "data": {
                    "avg": 62, "min": 50, "max": 82,
                    "minutesList": [
                        {"avg": 60, "min": 58, "max": 63, "ts": "2026-08-12 22:30:00"},
                        {"avg": 64, "min": 60, "max": 68, "ts": "2026-08-12 22:31:00"},
                    ],
                }})
            if request.url.path.endswith("/average/breaths"):
                return httpx.Response(200, json={"code": 200, "data": {
                    "min": 11, "max": 18, "sleepDatetime": "2026-08-12 22:30:00",
                    "wakeupDatetime": "2026-08-13 06:21:00",
                    "minuteList": [
                        {"avg": 16, "ts": "2026-08-12 22:30:00"},
                        {"avg": 14, "ts": "2026-08-12 22:40:00"},
                    ],
                }})
            raise AssertionError(request.url.path)

        settings = Settings(
            sleep_provider="ezviz", sleep_device_id="known-device-id",
            ezviz_access_token="test-token", ezviz_auto_token=False,
            sleep_timestamp_utc_offset_hours=8,
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            summary = await EzvizClient(settings, client).sleep_summary_for_date(date(2026, 8, 13))

        assert summary["duration_minutes"] == 471
        assert summary["respiratory_rate"] == 15
        assert summary["respiratory_min"] == 11
        assert summary["respiratory_max"] == 18
        assert summary["heart_rate"] == 62
        assert summary["heart_rate_min"] == 50
        assert summary["heart_rate_max"] == 82
        assert summary["bed_exit_count"] is None
        assert summary["quality"] == "usable"
        assert summary["source"] == "ezviz_sleep_assistant"
        assert summary["sleep_start"] == "2026-08-12T22:30:00+08:00"
        assert summary["sleep_end"] == "2026-08-13T06:21:00+08:00"
        assert summary["samples"] == [
            {"at": "2026-08-12T22:30:00+08:00", "heart_rate": 60.0, "respiratory_rate": 16.0},
            {"at": "2026-08-12T22:31:00+08:00", "heart_rate": 64.0},
            {"at": "2026-08-12T22:40:00+08:00", "respiratory_rate": 14.0},
        ]

    asyncio.run(scenario())
