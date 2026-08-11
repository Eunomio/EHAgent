"""FastAPI application factory and composition root."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app import __version__
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.services.demo_agent_service import DemoAgentService
from app.services.observation_service import ObservationService
from app.services.runtime_service import RuntimeService
from app.services.task_service import TaskService


def _ensure_sqlite_parent(database_url: str) -> None:
    """Create only the explicit local SQLite parent directory."""

    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return
    database_path = Path(database_url.removeprefix(prefix))
    database_path.parent.mkdir(parents=True, exist_ok=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an isolated application instance suitable for production and tests."""

    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    _ensure_sqlite_parent(resolved_settings.database_url)

    database = Database(resolved_settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        database.dispose()

    application = FastAPI(
        title=resolved_settings.app_name,
        version=__version__,
        description="Local-first EHAgent explainable demo API",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.database = database
    application.state.runtime_service = RuntimeService(database)
    application.state.observation_service = ObservationService(database)
    application.state.task_service = TaskService(database)
    application.state.demo_agent_service = DemoAgentService(
        database, application.state.observation_service
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Engineering-Key", "Idempotency-Key"],
    )
    application.include_router(api_router)

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    def root() -> str:
        return (
            "<main style='font-family:system-ui;padding:2rem'>"
            "<h1>居安Agent</h1>"
            f"<p>v{__version__} 本地风险Agent服务已运行。前端开发模式请访问 Vite 服务。</p>"
            "<p><a href='/docs'>打开本地API文档</a></p>"
            "</main>"
        )

    return application


app = create_app()
