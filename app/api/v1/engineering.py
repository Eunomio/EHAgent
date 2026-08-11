"""Local-only engineering controls for commissioning and deterministic tests."""

from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import (
    get_demo_agent_service,
    get_observation_service,
    get_runtime_service,
    require_engineering_access,
)
from app.domain.events import (
    CaptureMode,
    EventSource,
    ManualObservationRequest,
    ObservationEvent,
    SourceType,
)
from app.domain.runtime import InvalidRuntimeTransition, RuntimeMode
from app.schemas.runtime import RuntimeStateResponse, RuntimeTransitionRequest
from app.schemas.tasks import DemoAnalysisRequest, DemoAnalysisResponse, DemoMaterial
from app.services.demo_agent_service import DemoAgentService
from app.services.observation_service import ObservationService
from app.services.runtime_service import RuntimeService

router = APIRouter(
    prefix="/engineering",
    tags=["engineering"],
    dependencies=[Depends(require_engineering_access)],
)


@router.get("/demo-materials", response_model=list[DemoMaterial])
def list_demo_materials(
    demo_agent: Annotated[DemoAgentService, Depends(get_demo_agent_service)],
) -> list[DemoMaterial]:
    """List deterministic replay materials available to the test console."""

    return demo_agent.materials()


@router.post("/demo-analyses", response_model=DemoAnalysisResponse)
def run_demo_analysis(
    payload: DemoAnalysisRequest,
    runtime_service: Annotated[RuntimeService, Depends(get_runtime_service)],
    demo_agent: Annotated[DemoAgentService, Depends(get_demo_agent_service)],
) -> DemoAnalysisResponse:
    """Run one replay or explicitly manually labelled image through the demo agent."""

    runtime = runtime_service.get()
    if runtime.mode not in {RuntimeMode.COMMISSIONING, RuntimeMode.MAINTENANCE}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Demo analysis requires COMMISSIONING or MAINTENANCE mode",
        )
    return demo_agent.analyze(payload, runtime_mode=runtime.mode)


@router.post("/runtime/transition", response_model=RuntimeStateResponse)
def transition_runtime(
    payload: RuntimeTransitionRequest,
    runtime_service: Annotated[RuntimeService, Depends(get_runtime_service)],
) -> RuntimeStateResponse:
    """Perform one validated and audited runtime-mode transition."""

    try:
        result = runtime_service.transition(
            payload.target,
            reason=payload.reason,
            actor=payload.actor,
        )
    except InvalidRuntimeTransition as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return RuntimeStateResponse.model_validate(result, from_attributes=True)


@router.post(
    "/manual-events",
    response_model=ObservationEvent,
    status_code=status.HTTP_201_CREATED,
)
def create_manual_event(
    payload: ManualObservationRequest,
    request: Request,
    runtime_service: Annotated[RuntimeService, Depends(get_runtime_service)],
    observation_service: Annotated[ObservationService, Depends(get_observation_service)],
) -> ObservationEvent:
    """Append a permanently labeled manual event during non-active modes."""

    runtime = runtime_service.get()
    allowed_modes = {RuntimeMode.COMMISSIONING, RuntimeMode.MAINTENANCE}
    if runtime.mode not in allowed_modes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Manual events are allowed only during COMMISSIONING or MAINTENANCE",
        )

    now = datetime.now(ZoneInfo(request.app.state.settings.app_timezone))
    event = ObservationEvent(
        occurred_at=payload.occurred_at or now,
        received_at=now,
        source=EventSource(
            provider="manual",
            source_type=SourceType.MANUAL,
            device_id="manual-local",
            channel_no=1,
            capture_mode=CaptureMode.EVENT,
        ),
        event_type=payload.event_type,
        runtime_mode=runtime.mode,
        scene_id=payload.scene_id,
        observations=payload.observations,
        quality=payload.quality,
        configuration_version="demo-agent-0.2.0",
    )
    return observation_service.append(event)
