"""Process, version and dependency health endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import __version__
from app.api.dependencies import get_app_settings, get_database, get_runtime_service
from app.core.config import Settings
from app.db.session import Database
from app.domain.runtime import RuntimeMode
from app.services.runtime_service import RuntimeService

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """Health response safe for local status pages."""

    status: str
    version: str
    environment: str
    database: str
    runtime_mode: RuntimeMode
    checked_at: datetime


class VersionResponse(BaseModel):
    """Application version response."""

    application: str
    version: str
    api_version: str


@router.get("/health", response_model=HealthResponse)
def health(
    settings: Annotated[Settings, Depends(get_app_settings)],
    database: Annotated[Database, Depends(get_database)],
    runtime_service: Annotated[RuntimeService, Depends(get_runtime_service)],
) -> HealthResponse:
    """Check the foundational backend and database."""

    database_ok = database.ping()
    runtime = runtime_service.get()
    return HealthResponse(
        status="ok" if database_ok else "degraded",
        version=__version__,
        environment=settings.app_env,
        database="ok" if database_ok else "error",
        runtime_mode=runtime.mode,
        checked_at=datetime.now(UTC),
    )


@router.get("/version", response_model=VersionResponse)
def version(settings: Annotated[Settings, Depends(get_app_settings)]) -> VersionResponse:
    """Return the public application and API versions."""

    return VersionResponse(application=settings.app_name, version=__version__, api_version="v1")
