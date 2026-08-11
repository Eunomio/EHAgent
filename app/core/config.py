"""Typed application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Backend settings; sensitive values must never be serialized to API responses."""

    model_config = SettingsConfigDict(
        env_prefix="EHAGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "居安Agent"
    app_env: str = "development"
    app_timezone: str = "Asia/Shanghai"
    bind_host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    database_url: str = "sqlite:///./runtime/ehagent.db"
    log_level: str = "INFO"
    engineering_api_key: str = ""
    camera_provider: str = "replay"
    replay_root: Path = Path("tests/fixtures/replay")

    ezviz_api_base_url: str = "https://open.ys7.com"
    ezviz_app_key: str = ""
    ezviz_app_secret: str = ""
    ezviz_access_token: str = ""
    ezviz_token_expires_at: str = ""
    ezviz_device_serial: str = ""
    ezviz_channel_no: int = Field(default=1, ge=1)
    ezviz_device_verify_code: str = ""

    @field_validator("app_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Reject invalid IANA timezone names during startup."""

        ZoneInfo(value)
        return value

    @field_validator("camera_provider")
    @classmethod
    def validate_camera_provider(cls, value: str) -> str:
        """Keep provider selection explicit in the skeleton release."""

        normalized = value.lower().strip()
        supported = {"replay", "manual", "ezviz"}
        if normalized not in supported:
            raise ValueError(f"camera_provider must be one of {sorted(supported)}")
        return normalized


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
