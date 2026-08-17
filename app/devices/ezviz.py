"""Minimal server-side EZVIZ Open Platform integration."""

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
        self._token = settings.ezviz_access_token

    @property
    def configured(self) -> bool:
        has_token = bool(self._token)
        has_app = bool(self.settings.ezviz_app_key and self.settings.ezviz_app_secret)
        return bool(self.settings.ezviz_device_serial and (has_token or has_app))

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def token(self) -> str:
        if self._token:
            return self._token
        if not self.settings.ezviz_app_key or not self.settings.ezviz_app_secret:
            raise EzvizError("请先在.env中配置萤石AppKey和AppSecret")
        response = await self.client.post(
            f"{self.settings.ezviz_api_base_url}/api/lapp/token/get",
            data={"appKey": self.settings.ezviz_app_key, "appSecret": self.settings.ezviz_app_secret},
        )
        payload = response.json()
        if str(payload.get("code")) != "200":
            raise EzvizError(payload.get("msg") or "获取萤石访问令牌失败")
        self._token = str(payload["data"]["accessToken"])
        return self._token

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
