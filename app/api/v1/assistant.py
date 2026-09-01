from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import AssistantDep

router = APIRouter(prefix="/assistant", tags=["assistant"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    conversation_id: str | None = None


@router.post("/chat")
async def chat(payload: ChatRequest, assistant: AssistantDep) -> dict[str, Any]:
    return await assistant.chat(payload.message.strip(), payload.conversation_id)


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: str, assistant: AssistantDep) -> dict[str, Any]:
    result = assistant.conversation(conversation_id)
    if result is None:
        raise HTTPException(404, "没有找到这段对话")
    return result


@router.post("/events/{event_id}/start")
def start_event(event_id: str, assistant: AssistantDep) -> dict[str, Any]:
    result = assistant.start_event(event_id)
    if result is None:
        raise HTTPException(404, "没有找到这条主动关怀")
    return result


@router.post("/profile-onboarding/start")
def start_profile_onboarding(assistant: AssistantDep) -> dict[str, Any]:
    return assistant.start_profile_onboarding()


@router.post("/actions/{action_id}/confirm")
async def confirm_action(action_id: str, assistant: AssistantDep) -> dict[str, Any]:
    result = await assistant.confirm_action(action_id)
    if result is None:
        raise HTTPException(404, "没有找到这个操作")
    return result
