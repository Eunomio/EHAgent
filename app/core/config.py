from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EH_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )
    app_name: str = "居安Agent"
    app_env: str = "development"
    bind_host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = "INFO"
    database_path: Path = Path("runtime/ehagent.db")
    evidence_root: Path = Path("evidence")
    ezviz_api_base_url: str = "https://open.ys7.com"
    ezviz_app_key: str = ""
    ezviz_app_secret: str = ""
    ezviz_access_token: str = ""
    ezviz_auto_token: bool = False
    ezviz_device_serial: str = ""
    ezviz_channel_no: int = Field(default=1, ge=1)
    ezviz_verify_code: str = ""
    sleep_provider: str = "disabled"
    sleep_device_name: str = "萤石无感睡眠伴侣"
    sleep_device_serial: str = ""
    sleep_device_id: str = ""
    sleep_timestamp_utc_offset_hours: int = Field(default=0, ge=-12, le=14)
    sleep_auto_sync_enabled: bool = True
    sleep_sync_hour: int = Field(default=10, ge=0, le=23)
    sleep_sync_minute: int = Field(default=0, ge=0, le=59)
    sleep_sync_lookback_days: int = Field(default=3, ge=1, le=14)
    sleep_sync_utc_offset_hours: int = Field(default=8, ge=-12, le=14)
    safety_area_name: str = "卧室外走道"
    llm_enabled: bool = False
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model: str = "gpt-5.4-nano"
    llm_api_base: str = "https://api.openai.com/v1"
    llm_timeout_seconds: float = Field(default=15, ge=1, le=60)
    llm_max_output_tokens: int = Field(default=500, ge=100, le=2000)
    vlm_enabled: bool | None = None
    vlm_api_key: str = ""
    vlm_model: str = ""
    vlm_api_base: str = ""
    vlm_timeout_seconds: float = Field(default=60, ge=5, le=120)
    vlm_auto_check_enabled: bool = True
    vlm_change_poll_seconds: float = Field(default=6, ge=5, le=300)
    vlm_change_threshold: float = Field(default=0.025, ge=0.005, le=0.5)
    vlm_change_confirmations: int = Field(default=2, ge=1, le=5)
    vlm_change_cooldown_seconds: float = Field(default=30, ge=10, le=600)
    assistant_web_search_enabled: bool = True
    assistant_location: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
