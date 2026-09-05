from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.dependencies import AssistantDep, SpeechTranscriptionDep
from app.speech.service import SpeechTranscriptionError

router = APIRouter(prefix="/assistant", tags=["assistant"])


def public_assistant_payload(value: dict[str, Any]) -> dict[str, Any]:
    """Remove internal audit fields from every resident-facing assistant response."""

    def remove_internal_fields(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                key: remove_internal_fields(nested)
                for key, nested in item.items()
                if key != "context_used"
            }
        if isinstance(item, list):
            return [remove_internal_fields(nested) for nested in item]
        return item

    return cast(dict[str, Any], remove_internal_fields(value))


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    conversation_id: str | None = None


@router.post("/chat")
async def chat(payload: ChatRequest, assistant: AssistantDep) -> dict[str, Any]:
    result = await assistant.chat(payload.message.strip(), payload.conversation_id)
    return public_assistant_payload(result)


@router.post("/transcribe")
async def transcribe(
    request: Request, speech: SpeechTranscriptionDep
) -> dict[str, str]:
    content_type = request.headers.get("content-type", "audio/mp4")
    audio = await request.body()
    try:
        text = await speech.transcribe(audio, content_type)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except SpeechTranscriptionError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"text": text}


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: str, assistant: AssistantDep) -> dict[str, Any]:
    result = assistant.conversation(conversation_id)
    if result is None:
        raise HTTPException(404, "没有找到这段对话")
    return public_assistant_payload(result)


@router.post("/events/{event_id}/start")
async def start_event(event_id: str, assistant: AssistantDep) -> dict[str, Any]:
    result = await assistant.start_event(event_id)
    if result is None:
        raise HTTPException(404, "没有找到这条主动关怀")
    return public_assistant_payload(result)


@router.post("/profile-onboarding/start")
def start_profile_onboarding(assistant: AssistantDep) -> dict[str, Any]:
    return public_assistant_payload(assistant.start_profile_onboarding())


@router.post("/actions/{action_id}/confirm")
async def confirm_action(action_id: str, assistant: AssistantDep) -> dict[str, Any]:
    result = await assistant.confirm_action(action_id)
    if result is None:
        raise HTTPException(404, "没有找到这个操作")
    return public_assistant_payload(result)
