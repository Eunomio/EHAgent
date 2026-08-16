"""EHAgent local product API."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.devices.ezviz import EzvizClient
from app.llm.service import LlmService
from app.store import ProductStore


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)
    database_path = Path(resolved.database_path).resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    Path(resolved.evidence_root).resolve().mkdir(parents=True, exist_ok=True)
    store = ProductStore(database_path)
    store.initialize()
    ezviz = EzvizClient(resolved)
    llm = LlmService(resolved)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await ezviz.close()
        await llm.close()

    app = FastAPI(
        title=resolved.app_name,
        version=__version__,
        description="居安Agent本地产品服务",
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.store = store
    app.state.ezviz = ezviz
    app.state.llm = llm
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"name": resolved.app_name, "version": __version__, "status": "ready"}

    return app


app = create_app()
