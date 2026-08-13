from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings
from app.devices.ezviz import EzvizClient
from app.store import ProductStore


def get_store(request: Request) -> ProductStore:
    return request.app.state.store


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_ezviz(request: Request) -> EzvizClient:
    return request.app.state.ezviz


StoreDep = Annotated[ProductStore, Depends(get_store)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
EzvizDep = Annotated[EzvizClient, Depends(get_ezviz)]
