from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_path=tmp_path / "test.db",
        evidence_root=tmp_path / "evidence",
        llm_enabled=False,
        llm_api_key="",
        vlm_enabled=False,
        vlm_api_key="",
        sleep_provider="disabled",
        sleep_device_serial="",
        sleep_device_id="",
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client

