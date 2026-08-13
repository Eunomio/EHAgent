from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(database_path=tmp_path / "test.db", evidence_root=tmp_path / "evidence")
    with TestClient(create_app(settings)) as test_client:
        yield test_client

