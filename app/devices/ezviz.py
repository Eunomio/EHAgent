"""Minimal server-side EZVIZ Open Platform integration."""

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from statistics import fmean
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

    @staticmethod
    def _number_in_range(value: Any, lower: float, upper: float) -> float | None:
        if not isinstance(value, int | float) or isinstance(value, bool):
            return None
        parsed = float(value)
        return parsed if lower <= parsed <= upper else None

    def _sleep_timestamp(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None
        if parsed.tzinfo is None:
            source_zone = timezone(
                timedelta(hours=self.settings.sleep_timestamp_utc_offset_hours)
            )
            parsed = parsed.replace(tzinfo=source_zone)
        return parsed

    async def _sleep_get(self, path: str, params: dict[str, str]) -> Any:
        async def request(access_token: str) -> dict[str, Any]:
            response = await self.client.get(
                f"{self.settings.ezviz_api_base_url}{path}",
                headers={"accessToken": access_token},
                params=params,
            )
            try:
                return dict(response.json())
            except ValueError as exc:
                raise EzvizError("萤石睡眠统计接口返回了无效响应") from exc

        payload = await request(await self.token())
        result_code = str(payload.get("code") or (payload.get("meta") or {}).get("code") or "")
        if result_code == "10002":
            payload = await request(await self.token(force_refresh=True))
            result_code = str(payload.get("code") or (payload.get("meta") or {}).get("code") or "")
        if result_code != "200":
            message = (
                payload.get("message")
                or payload.get("msg")
                or (payload.get("meta") or {}).get("message")
                or "读取睡眠统计失败"
            )
            raise EzvizError(str(message))
        return payload.get("data")

    async def sleep_summary_for_date(self, target_date: date) -> dict[str, Any]:
        """Map EZVIZ daily statistics into the existing sleep-summary contract.

        This intentionally retains only fields that the product contract already
        defines. Sleep score and staging remain source data until the product
        contract is expanded with their semantics and display rules.
        """

        device_id = await self.sleep_device_id()
        base = "/api/service/sleepDetector/v3/third/forward/huayi/analysis/v1/devices"
        params = {"deviceId": device_id, "date": target_date.isoformat()}
        sleep_data, heart_data, breath_data = await self._sleep_get(
            f"{base}/{device_id}/daily/sleep", params
        ), await self._sleep_get(
            f"{base}/{device_id}/daily/average/hearts", params
        ), await self._sleep_get(
            f"{base}/{device_id}/average/breaths", params
        )
        if not isinstance(heart_data, dict) or not isinstance(breath_data, dict):
            raise EzvizError("萤石睡眠统计返回结构不完整")
        if sleep_data is not None and not isinstance(sleep_data, dict):
            raise EzvizError("萤石睡眠分期返回结构不完整")

        sleep_start = self._sleep_timestamp(breath_data.get("sleepDatetime"))
        sleep_end = self._sleep_timestamp(breath_data.get("wakeupDatetime"))
        if sleep_start is None or sleep_end is None or sleep_end <= sleep_start:
            raise EzvizError("萤石接口未返回有效的睡眠起止时间")
        duration_minutes = int((sleep_end - sleep_start).total_seconds() // 60)
        if not 1 <= duration_minutes <= 1440:
            raise EzvizError("萤石接口返回的睡眠时长超出可接受范围")

        samples: dict[datetime, dict[str, Any]] = {}

        def add_sample(timestamp: Any, key: str, value: Any, lower: float, upper: float) -> None:
            at = self._sleep_timestamp(timestamp)
            number = self._number_in_range(value, lower, upper)
            if at is None or number is None:
                return
            samples.setdefault(at, {"at": at.isoformat()})[key] = number

        for item in heart_data.get("minutesList") or []:
            if isinstance(item, dict):
                add_sample(item.get("ts"), "heart_rate", item.get("avg"), 20, 240)
        breath_values: list[float] = []
        for item in breath_data.get("minuteList") or []:
            if not isinstance(item, dict):
                continue
            value = self._number_in_range(item.get("avg"), 1, 80)
            if value is not None:
                breath_values.append(value)
            add_sample(item.get("ts"), "respiratory_rate", item.get("avg"), 1, 80)

        heart_rate = self._number_in_range(heart_data.get("avg"), 20, 240)
        respiratory_rate = round(fmean(breath_values), 2) if breath_values else None
        record_key = sha256(
            f"ezviz-sleep:{device_id}:{target_date.isoformat()}".encode()
        ).hexdigest()[:24]
        return {
            "id": f"ezviz-sleep-{record_key}",
            "external_report_id": f"ezviz-daily-{target_date.isoformat()}",
            "device_serial": self.settings.sleep_device_serial or None,
            "report_date": target_date.isoformat(),
            "timezone": str(sleep_start.tzinfo),
            "sleep_start": sleep_start.isoformat(),
            "sleep_end": sleep_end.isoformat(),
            "duration_minutes": duration_minutes,
            "awake_minutes": None,
            "light_sleep_minutes": None,
            "deep_sleep_minutes": None,
            "rem_sleep_minutes": None,
            "sleep_score": self._number_in_range(
                sleep_data.get("score") if sleep_data else None, 0, 100
            ),
            "respiratory_rate": respiratory_rate,
            "heart_rate": heart_rate,
            "respiratory_min": self._number_in_range(breath_data.get("min"), 1, 80),
            "respiratory_max": self._number_in_range(breath_data.get("max"), 1, 80),
            "heart_rate_min": self._number_in_range(heart_data.get("min"), 20, 240),
            "heart_rate_max": self._number_in_range(heart_data.get("max"), 20, 240),
            "bed_exit_count": None,
            "quality": "usable" if heart_rate is not None or respiratory_rate is not None else "insufficient",
            "data_status": "final",
            "source": "ezviz_sleep_assistant",
            "measured_at": sleep_end.isoformat(),
            "samples": [samples[key] for key in sorted(samples)],
            "stages": [],
        }

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
