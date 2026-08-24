from typing import Annotated, cast

from fastapi import Depends, Request

from app.assistant.service import AssistantService
from app.core.config import Settings
from app.devices.ezviz import EzvizClient
from app.llm.service import LlmService
from app.sleep.service import SleepService
from app.sleep.sync import SleepSyncService
from app.store import ProductStore
from app.vision.service import VisionSafetyService


def get_store(request: Request) -> ProductStore:
    return cast(ProductStore, request.app.state.store)


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_ezviz(request: Request) -> EzvizClient:
    return cast(EzvizClient, request.app.state.ezviz)


def get_llm(request: Request) -> LlmService:
    return cast(LlmService, request.app.state.llm)


def get_assistant(request: Request) -> AssistantService:
    return cast(AssistantService, request.app.state.assistant)


def get_sleep(request: Request) -> SleepService:
    return cast(SleepService, request.app.state.sleep)


def get_sleep_sync(request: Request) -> SleepSyncService:
    return cast(SleepSyncService, request.app.state.sleep_sync)


def get_vision_safety(request: Request) -> VisionSafetyService:
    return cast(VisionSafetyService, request.app.state.vision_safety)


StoreDep = Annotated[ProductStore, Depends(get_store)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
EzvizDep = Annotated[EzvizClient, Depends(get_ezviz)]
LlmDep = Annotated[LlmService, Depends(get_llm)]
AssistantDep = Annotated[AssistantService, Depends(get_assistant)]
SleepDep = Annotated[SleepService, Depends(get_sleep)]
SleepSyncDep = Annotated[SleepSyncService, Depends(get_sleep_sync)]
VisionSafetyDep = Annotated[VisionSafetyService, Depends(get_vision_safety)]
