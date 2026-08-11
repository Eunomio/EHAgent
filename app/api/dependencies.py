"""FastAPI dependencies and engineering access guard."""

import secrets
from typing import cast

from fastapi import Header, HTTPException, Request, status

from app.core.config import Settings
from app.db.session import Database
from app.services.observation_service import ObservationService
from app.services.runtime_service import RuntimeService

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "testclient"}


def get_app_settings(request: Request) -> Settings:
    """Resolve settings from the current application instance."""

    return cast(Settings, request.app.state.settings)


def get_database(request: Request) -> Database:
    """Resolve the database owned by the current application instance."""

    return cast(Database, request.app.state.database)


def get_runtime_service(request: Request) -> RuntimeService:
    """Resolve the runtime service owned by the application."""

    return cast(RuntimeService, request.app.state.runtime_service)


def get_observation_service(request: Request) -> ObservationService:
    """Resolve the observation service owned by the application."""

    return cast(ObservationService, request.app.state.observation_service)


def require_engineering_access(
    request: Request,
    x_engineering_key: str | None = Header(default=None),
) -> None:
    """Require loopback access and the configured engineering API key."""

    client_host = request.client.host if request.client else ""
    if client_host not in LOOPBACK_HOSTS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Engineering endpoints are available only from the local computer",
        )

    expected = request.app.state.settings.engineering_api_key
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Engineering API key is not configured",
        )
    if x_engineering_key is None or not secrets.compare_digest(x_engineering_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid engineering credentials",
        )
