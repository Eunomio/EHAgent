"""EHAgent local product API."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.assistant.device_tools import DeviceToolGateway
from app.assistant.service import AssistantService
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.devices.ezviz import EzvizClient
from app.llm.service import LlmService
from app.sleep.service import SleepService
from app.sleep.sync import SleepSyncService
from app.speech.service import SpeechTranscriptionService
from app.store import ProductStore
from app.vision.monitor import VisionChangeMonitor
from app.vision.service import VisionSafetyService


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    auto_sync_allowed = settings is None
    configure_logging(resolved.log_level)
    database_path = Path(resolved.database_path).resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    Path(resolved.evidence_root).resolve().mkdir(parents=True, exist_ok=True)
    store = ProductStore(database_path)
    store.initialize()
    ezviz = EzvizClient(resolved)
    llm = LlmService(resolved)
    sleep = SleepService(store, llm, resolved)
    sleep_sync = SleepSyncService(resolved, ezviz, store, llm)
    vision_safety = VisionSafetyService(resolved)
    device_tools = DeviceToolGateway(
        store, resolved, ezviz, vision_safety, sleep_sync
    )
    assistant = AssistantService(store, llm, resolved, device_tools)
    speech_transcription = SpeechTranscriptionService(resolved)
    vision_monitor = VisionChangeMonitor(resolved, ezviz, vision_safety, store)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        monitor_task = asyncio.create_task(vision_monitor.run())
        sleep_sync_task = (
            asyncio.create_task(sleep_sync.run()) if auto_sync_allowed else None
        )
        yield
        monitor_task.cancel()
        if sleep_sync_task is not None:
            sleep_sync_task.cancel()
        with suppress(asyncio.CancelledError):
            await monitor_task
        if sleep_sync_task is not None:
            with suppress(asyncio.CancelledError):
                await sleep_sync_task
        await ezviz.close()
        await llm.close()
        await vision_safety.close()
        await speech_transcription.close()

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
    app.state.assistant = assistant
    app.state.sleep = sleep
    app.state.sleep_sync = sleep_sync
    app.state.vision_safety = vision_safety
    app.state.vision_monitor = vision_monitor
    app.state.speech_transcription = speech_transcription
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
