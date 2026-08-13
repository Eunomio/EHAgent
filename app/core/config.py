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
    ezviz_device_serial: str = ""
    ezviz_channel_no: int = Field(default=1, ge=1)
    ezviz_verify_code: str = ""
    sleep_provider: str = "disabled"
    sleep_device_name: str = "萤石无感睡眠伴侣"
    safety_area_name: str = "卧室外走道"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
