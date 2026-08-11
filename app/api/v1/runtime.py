"""Read-only runtime state for all local UI roles."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_runtime_service
from app.schemas.runtime import RuntimeStateResponse
from app.services.runtime_service import RuntimeService

router = APIRouter(tags=["runtime"])


@router.get("/runtime", response_model=RuntimeStateResponse)
def get_runtime(
    runtime_service: Annotated[RuntimeService, Depends(get_runtime_service)],
) -> RuntimeStateResponse:
    """Return the current runtime mode without exposing engineering settings."""

    return RuntimeStateResponse.model_validate(runtime_service.get(), from_attributes=True)
