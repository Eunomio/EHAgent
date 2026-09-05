from datetime import datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.care.interventions import intervention_list
from app.care.white_noise import random_white_noise, white_noise_path, white_noise_tracks
from app.dependencies import StoreDep

router = APIRouter(prefix="/resident", tags=["proactive care"])


class ProfileFactCreate(BaseModel):
    fact_type: Literal[
        "preferred_name", "living_arrangement", "fall_experience",
        "near_fall_experience", "fall_concern", "activity_avoidance",
        "reminder_preference", "sharing_preference",
        "daily_preference", "interaction_preference", "routine_preference",
    ]
    display_text: str = Field(min_length=2, max_length=80)
    value: dict[str, Any] = Field(default_factory=dict)


class ProfileFactDecision(BaseModel):
    status: Literal["confirmed", "rejected", "expired"]


class EventAction(BaseModel):
    action: Literal["later", "dismiss", "complete"]


class InterventionUpdate(BaseModel):
    status: Literal["completed", "stopped"]
    helpful: bool | None = None
    feedback: str | None = Field(default=None, max_length=300)


@router.get("/profile")
def profile(store: StoreDep) -> dict[str, Any]:
    confirmed = store.profile_facts(("confirmed",))
    inferred = store.profile_facts(("inferred",))
    return {
        "confirmed": confirmed,
        "inferred": inferred,
        "visible": confirmed + inferred,
        "pending_confirmation": store.profile_facts(("candidate",)),
    }


@router.post("/profile/facts")
def create_profile_fact(payload: ProfileFactCreate, store: StoreDep) -> dict[str, Any]:
    return store.create_profile_fact(
        payload.fact_type, payload.value, payload.display_text,
        source="resident_edit", status="confirmed",
    )


@router.put("/profile/facts/{fact_id}")
def decide_profile_fact(
    fact_id: str, payload: ProfileFactDecision, store: StoreDep
) -> dict[str, Any]:
    fact = store.update_profile_fact_status(fact_id, payload.status)
    if fact is None:
        raise HTTPException(404, "没有找到这条个人情况")
    return fact


@router.delete("/profile/facts/{fact_id}")
def delete_profile_fact(fact_id: str, store: StoreDep) -> dict[str, bool]:
    if not store.delete_profile_fact(fact_id):
        raise HTTPException(404, "没有找到这条个人情况")
    return {"deleted": True}


@router.get("/care/events")
def care_events(store: StoreDep) -> dict[str, Any]:
    return {"active": store.latest_proactive_event(), "items": store.proactive_events()}


@router.post("/care/events/{event_id}/actions")
def act_on_event(event_id: str, payload: EventAction, store: StoreDep) -> dict[str, Any]:
    if store.get_proactive_event(event_id) is None:
        raise HTTPException(404, "没有找到这条主动关怀")
    if payload.action == "later":
        remind_at = (datetime.now().astimezone() + timedelta(minutes=30)).isoformat(
            timespec="seconds"
        )
        result = store.update_proactive_event(event_id, "later", remind_at=remind_at)
    elif payload.action == "dismiss":
        result = store.update_proactive_event(event_id, "dismissed")
    else:
        result = store.update_proactive_event(event_id, "completed")
    return result or {}


@router.get("/care/interventions")
def interventions(store: StoreDep) -> dict[str, Any]:
    return {
        "items": intervention_list(),
        "recent_sessions": store.intervention_sessions(),
        "disclaimer": "这些内容用于日常自助支持，不代替医疗或心理治疗。",
    }


@router.get("/care/white-noise/tracks")
def white_noise_library() -> dict[str, Any]:
    return {
        "items": [
            {
                "id": track["id"],
                "name": track["name"],
                "audio_url": f"/api/v1/resident/care/white-noise/audio/{track['id']}",
            }
            for track in white_noise_tracks()
        ]
    }


@router.get("/care/white-noise/random")
def choose_white_noise(
    exclude: str | None = Query(default=None, max_length=32),
) -> dict[str, Any]:
    track = random_white_noise(exclude)
    if track is None:
        raise HTTPException(404, "白噪音素材库中暂时没有可播放的音频")
    return {
        "id": track["id"],
        "name": track["name"],
        "audio_url": f"/api/v1/resident/care/white-noise/audio/{track['id']}",
        "has_alternative": track["has_alternative"],
    }


@router.get("/care/white-noise/audio/{track_id}")
def play_white_noise(track_id: str) -> FileResponse:
    path = white_noise_path(track_id)
    if path is None:
        raise HTTPException(404, "没有找到这条白噪音素材")
    return FileResponse(path)


@router.put("/care/interventions/sessions/{session_id}")
def update_intervention(
    session_id: str, payload: InterventionUpdate, store: StoreDep
) -> dict[str, Any]:
    result = store.update_intervention_session(
        session_id, payload.status, payload.helpful, payload.feedback
    )
    if result is None:
        raise HTTPException(404, "没有找到这次支持记录")
    return result
