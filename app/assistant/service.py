from typing import Any

from app.assistant.context import ResidentContextBuilder
from app.core.config import Settings
from app.llm.service import LlmService
from app.store import ProductStore


class AssistantService:
    """Coordinate persisted chat, resident context, LLM output and confirmed actions."""

    def __init__(self, store: ProductStore, llm: LlmService, settings: Settings) -> None:
        self.store = store
        self.llm = llm
        self.context_builder = ResidentContextBuilder(store, settings)

    async def chat(self, message: str, conversation_id: str | None = None) -> dict[str, Any]:
        conversation = self.store.get_assistant_conversation(conversation_id) if conversation_id else None
        if conversation is None:
            conversation = self.store.create_assistant_conversation(message[:24])

        history = self.store.assistant_messages(conversation["id"], limit=12)
        user_message = self.store.add_assistant_message(
            conversation["id"], "user", message, "resident"
        )
        context, context_used = self.context_builder.build()
        reply, sources, source = await self.llm.chat_assistant(message, context, history)
        assistant_message = self.store.add_assistant_message(
            conversation["id"], "assistant", reply, source, sources, context_used
        )
        actions = self._suggest_actions(message, assistant_message["id"], conversation["id"])
        assistant_message["actions"] = actions
        return {
            "conversation_id": conversation["id"],
            "user_message": user_message,
            "assistant_message": assistant_message,
        }

    def conversation(self, conversation_id: str) -> dict[str, Any] | None:
        conversation = self.store.get_assistant_conversation(conversation_id)
        if conversation is None:
            return None
        return {
            **conversation,
            "messages": self.store.assistant_messages(conversation_id, limit=50, with_actions=True),
        }

    def confirm_action(self, action_id: str) -> dict[str, Any] | None:
        action = self.store.get_assistant_action(action_id)
        if action is None:
            return None
        if action["status"] == "completed":
            return action
        if action["kind"] == "contact_family":
            contact_name = self.store.settings().get("contact_name") or "家人"
            self.store.create_help_request("assistant", f"请{contact_name}联系我，我刚才在生活助手中提出了请求。")
        return self.store.update_assistant_action(action_id, "completed")

    def _suggest_actions(
        self, message: str, assistant_message_id: str, conversation_id: str
    ) -> list[dict[str, Any]]:
        contact_words = ("联系家人", "联系女儿", "联系儿子", "叫家人", "找家人", "通知家人")
        if any(word in message for word in contact_words):
            contact_name = self.store.settings().get("contact_name") or "家人"
            return [self.store.create_assistant_action(
                conversation_id,
                assistant_message_id,
                "contact_family",
                f"确认联系{contact_name}",
                {"contact_name": contact_name},
            )]
        return []
