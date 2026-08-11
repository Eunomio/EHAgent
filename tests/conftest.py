"""Shared isolated application fixture."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.base import Base
from app.main import create_app


@pytest.fixture
def test_app(tmp_path: pytest.TempPathFactory) -> Iterator[FastAPI]:
    """Create an application with a private SQLite database."""

    database_path = tmp_path / "test.db"
    settings = Settings(
        _env_file=None,
        app_name="EHAgent Test",
        app_env="test",
        database_url=f"sqlite:///{database_path.as_posix()}",
        engineering_api_key="test-engineering-key",
        replay_root=tmp_path / "replay",
    )
    application = create_app(settings)
    Base.metadata.create_all(application.state.database.engine)
    try:
        yield application
    finally:
        Base.metadata.drop_all(application.state.database.engine)
        application.state.database.dispose()


@pytest.fixture
def client(test_app: FastAPI) -> Iterator[TestClient]:
    """Return a TestClient that runs the application lifespan."""

    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture
def engineering_headers() -> dict[str, str]:
    """Return valid local engineering credentials for API tests."""

    return {"X-Engineering-Key": "test-engineering-key"}
