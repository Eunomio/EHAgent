"""Minimal server-side EZVIZ Open Platform integration."""

from time import time
from typing import Any

import httpx

from app.core.config import Settings


class EzvizError(RuntimeError):
    pass


class EzvizClient:
    def __init__(
        self, settings: Settings, client: httpx.AsyncClient | None = None
    ) -> None:
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=15)
        self._owns_client = client is None
        self._token = "" if settings.ezviz_auto_token else settings.ezviz_access_token
        self._token_expire_at: int | None = None

    @property
    def configured(self) -> bool:
        has_token = bool(self._token)
        has_app = bool(self.settings.ezviz_app_key and self.settings.ezviz_app_secret)
        return bool(self.settings.ezviz_device_serial and (has_token or has_app))

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def token(self, force_refresh: bool = False) -> str:
        now_ms = int(time() * 1000)
        if (
            not force_refresh
            and self._token
            and (
                self._token_expire_at is None
                or now_ms < self._token_expire_at - 12 * 60 * 60 * 1000
            )
        ):
            return self._token
        if not self.settings.ezviz_app_key or not self.settings.ezviz_app_secret:
            if self._token:
                return self._token
            raise EzvizError("请先在.env中配置萤石AppKey和AppSecret")
        response = await self.client.post(
            f"{self.settings.ezviz_api_base_url}/api/lapp/token/get",
            data={"appKey": self.settings.ezviz_app_key, "appSecret": self.settings.ezviz_app_secret},
        )
        payload = response.json()
        if str(payload.get("code")) != "200":
            raise EzvizError(payload.get("msg") or "获取萤石访问令牌失败")
        self._token = str(payload["data"]["accessToken"])
        self._token_expire_at = int(payload["data"]["expireTime"])
        return self._token

    @property
    def sleep_configured(self) -> bool:
        return bool(
            self.settings.sleep_provider == "ezviz"
            and (self.settings.sleep_device_id or self.settings.sleep_device_serial)
            and (self.settings.ezviz_app_key and self.settings.ezviz_app_secret or self._token)
        )

    async def sleep_device_id(self) -> str:
        if not self.sleep_configured:
            raise EzvizError("请先在.env中配置萤石睡眠伴侣设备序列号和开放平台凭证")
        if self.settings.sleep_device_id:
            return self.settings.sleep_device_id

        async def request(access_token: str) -> dict[str, Any]:
            response = await self.client.get(
                f"{self.settings.ezviz_api_base_url}/api/service/sleepDetector/v3/third/huayi/deviceId",
                headers={"accessToken": access_token},
                params={"deviceCode": self.settings.sleep_device_serial},
            )
            return dict(response.json())

        payload = await request(await self.token())
        result_code = str(payload.get("code") or (payload.get("meta") or {}).get("code") or "")
        if result_code == "10002":
            payload = await request(await self.token(force_refresh=True))
            result_code = str(payload.get("code") or (payload.get("meta") or {}).get("code") or "")
        if result_code != "200" or not payload.get("data"):
            raise EzvizError(
                str(payload.get("msg") or (payload.get("meta") or {}).get("message") or "读取睡眠伴侣设备ID失败")
            )
        return str(payload["data"])

    async def device_info(self) -> dict[str, Any]:
        if not self.settings.ezviz_device_serial:
            raise EzvizError("请先配置C6c设备序列号")
        response = await self.client.post(
            f"{self.settings.ezviz_api_base_url}/api/lapp/device/info",
            data={"accessToken": await self.token(), "deviceSerial": self.settings.ezviz_device_serial},
        )
        payload = response.json()
        if str(payload.get("code")) != "200":
            raise EzvizError(payload.get("msg") or "读取C6c状态失败")
        return dict(payload.get("data") or {})

    async def capture(self) -> str:
        response = await self.client.post(
            f"{self.settings.ezviz_api_base_url}/api/lapp/device/capture",
            data={
                "accessToken": await self.token(),
                "deviceSerial": self.settings.ezviz_device_serial,
                "channelNo": self.settings.ezviz_channel_no,
            },
        )
        payload = response.json()
        if str(payload.get("code")) != "200":
            raise EzvizError(payload.get("msg") or "C6c抓图失败")
        url = (payload.get("data") or {}).get("picUrl")
        if not url:
            raise EzvizError("萤石接口未返回图片地址")
        return str(url)

    async def live_address(self) -> dict[str, Any]:
        """Request a short-lived HLS address without exposing app credentials."""

        if not self.settings.ezviz_device_serial:
            raise EzvizError("请先配置C6c设备序列号")
        form: dict[str, Any] = {
            "accessToken": await self.token(),
            "deviceSerial": self.settings.ezviz_device_serial,
            "channelNo": self.settings.ezviz_channel_no,
            "protocol": 2,
            "quality": 2,
            "expireTime": 1800,
        }
        if self.settings.ezviz_verify_code:
            form["code"] = self.settings.ezviz_verify_code
        response = await self.client.post(
            f"{self.settings.ezviz_api_base_url}/api/lapp/v2/live/address/get",
            data=form,
        )
        payload = response.json()
        if str(payload.get("code")) != "200":
            raise EzvizError(payload.get("msg") or "获取C6c直播地址失败")
        data = dict(payload.get("data") or {})
        url = data.get("url")
        if not url:
            raise EzvizError("萤石接口未返回直播地址")
        return {
            "url": str(url),
            "protocol": "hls",
            "expires_in": 1800,
        }

    async def sdk_session(self) -> dict[str, Any]:
        """Return the client-side values required by EZOpenSDK.

        AppSecret is deliberately retained by the backend. The Android client
        receives the access token that the official SDK requires for playback.
        """

        if not self.settings.ezviz_app_key:
            raise EzvizError("请先在 .env 中配置萤石 AppKey")
        if not self.settings.ezviz_device_serial:
            raise EzvizError("请先配置 C6c 设备序列号")
        return {
            "app_key": self.settings.ezviz_app_key,
            "access_token": await self.token(),
            "device_serial": self.settings.ezviz_device_serial,
            "channel_no": self.settings.ezviz_channel_no,
            "verify_code": self.settings.ezviz_verify_code,
        }
