from fastapi import APIRouter

from app.api.v1 import devices, health, ingest, llm, resident

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(resident.router)
api_router.include_router(devices.router)
api_router.include_router(ingest.router)
api_router.include_router(llm.router)
