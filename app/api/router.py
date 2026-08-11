"""Versioned API router composition."""

from fastapi import APIRouter

from app.api.v1 import engineering, health, runtime

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(runtime.router)
api_router.include_router(engineering.router)
