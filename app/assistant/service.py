from datetime import datetime, timedelta
from typing import Any

from app.assistant.context import ResidentContextBuilder
from app.assistant.device_tools import DeviceToolGateway
from app.assistant.profile_onboarding import (
    PROFILE_ONBOARDING_FACT_TYPES,
    PROFILE_ONBOARDING_STEPS,
    onboarding_step,
)
from app.care.interventions import intervention
from app.core.config import Settings
from app.llm.service import LlmService
from app.store import ProductStore


class AssistantService:
    """Coordinate persisted chat, resident context, LLM output and confirmed actions."""

    def __init__(
        self,
        store: ProductStore,
        llm: LlmService,
        settings: Settings,
        device_tools: DeviceToolGateway,
    ) -> None:
        self.store = store
        self.llm = llm
        self.context_builder = ResidentContextBuilder(store, settings)
        self.device_tools = device_tools

    async def chat(self, message: str, conversation_id: str | None = None) -> dict[str, Any]:
        conversation = self.store.get_assistant_conversation(conversation_id) if conversation_id else None
        if conversation is None:
            conversation = self.store.create_assistant_conversation(message[:24])

        history = self.store.assistant_messages(conversation["id"], limit=12)
        user_message = self.store.add_assistant_message(
            conversation["id"], "user", message, "resident"
        )
        active_event = self.store.proactive_event_for_conversation(conversation["id"])
        if active_event and active_event["status"] in {"engaged", "pending", "later"}:
            self.store.update_proactive_event(
                active_event["id"], "completed",
                response={"resident_message_id": user_message["id"], "text": message},
                conversation_id=conversation["id"],
            )
        extracted, extraction_source = await self.llm.extract_profile_facts(message)
        candidate_facts: list[dict[str, Any]] = []
        for item in extracted.facts:
            inferred = (
                item.memory_mode == "inferred"
                and item.fact_type in {
                    "daily_preference", "interaction_preference", "routine_preference",
                }
            )
            fact = self.store.create_profile_fact(
                fact_type=item.fact_type,
                value={"evidence_quote": item.evidence_quote},
                display_text=item.display_text,
                source=f"conversation_{extraction_source}",
                source_ref=user_message["id"],
                confidence=item.confidence,
                status="inferred" if inferred else "candidate",
                expires_at=(
                    (datetime.now().astimezone() + timedelta(days=90)).isoformat(
                        timespec="seconds"
                    )
                    if inferred else None
                ),
            )
            if fact["status"] == "candidate":
                candidate_facts.append(fact)
        context, context_used = self.context_builder.build()
        tool_decision, tool_plan_source = await self.llm.plan_device_tool(
            message, self.device_tools.state()
        )
        device_tool = (
            tool_decision.tool_name if tool_decision.tool_name != "none" else None
        )
        device_consent = self.store.settings().get(
            "assistant_device_control_consent", "unset"
        )
        if device_tool:
            context["device_tool_plan"] = {
                "tool_name": device_tool,
                "reason": tool_decision.reason,
                "planner": tool_plan_source,
            }
            context_used.append("本轮设备工具选择")
        if device_tool and device_consent == "allowed":
            context["device_tool_result"] = await self.device_tools.execute(device_tool)
            context_used.append("刚刚调用的设备结果")

        reply, sources, source = await self.llm.chat_assistant(message, context, history)
        if device_tool and device_consent == "unset":
            reply = (
                f"{reply}\n\n要完成这个操作，小安需要控制已连接居家设备的权限。"
                "您只需选择一次，以后可以随时在隐私设置中修改。"
            )
        elif device_tool and device_consent == "denied":
            reply = (
                f"{reply}\n\n您之前选择了不允许小安控制设备，所以这次没有执行。"
                "如需更改，请到隐私设置中重新选择。"
            )
        if candidate_facts:
            descriptions = "、".join(item["display_text"] for item in candidate_facts)
            reply = (
                f"{reply}\n\n我听到您提到“{descriptions}”。"
                "如果您愿意，我可以记住这件事，以后提醒时会更注意您的感受。"
            )
        assistant_message = self.store.add_assistant_message(
            conversation["id"], "assistant", reply, source, sources, context_used
        )
        actions = self._suggest_actions(
            message, assistant_message["id"], conversation["id"], candidate_facts,
            active_event["id"] if active_event else None,
            device_tool,
            device_consent,
        )
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

    def start_profile_onboarding(self) -> dict[str, Any]:
        conversation = self.store.create_assistant_conversation("完善我的情况")
        next_step = self._next_missing_profile_step()
        message = (
            self._add_profile_onboarding_summary(conversation["id"])
            if next_step is None
            else self._add_profile_onboarding_step(conversation["id"], next_step)
        )
        return {
            "conversation_id": conversation["id"],
            "assistant_message": message,
        }

    async def confirm_action(self, action_id: str) -> dict[str, Any] | None:
        action = self.store.get_assistant_action(action_id)
        if action is None:
            return None
        if action["status"] == "completed":
            return action
        follow_up_message: dict[str, Any] | None = None
        if action["kind"] == "contact_family":
            contact_name = self.store.settings().get("contact_name") or "家人"
            self.store.create_help_request("assistant", f"请{contact_name}联系我，我刚才在生活助手中提出了请求。")
            if action["payload"].get("event_id"):
                self.store.update_proactive_event(
                    str(action["payload"]["event_id"]),
                    "completed",
                    response={"choice": "contact_family"},
                )
        elif action["kind"] == "remember_profile_fact":
            self.store.update_profile_fact_status(action["payload"]["fact_id"], "confirmed")
        elif action["kind"] == "reject_profile_fact":
            self.store.update_profile_fact_status(action["payload"]["fact_id"], "rejected")
        elif action["kind"] == "start_intervention":
            resource = intervention(action["payload"]["intervention_id"])
            if resource:
                self.store.start_intervention(
                    resource["id"], resource["title"], action["payload"].get("event_id")
                )
        elif action["kind"] == "defer_event":
            remind_at = (datetime.now().astimezone() + timedelta(minutes=30)).isoformat(
                timespec="seconds"
            )
            self.store.update_proactive_event(
                action["payload"]["event_id"], "later", remind_at=remind_at
            )
        elif action["kind"] == "pause_proactive_care":
            self.store.update_settings({"proactive_care_paused": "true"})
            self.store.update_proactive_event(action["payload"]["event_id"], "dismissed")
        elif action["kind"] == "safety_handle_now":
            self.store.update_proactive_event(
                action["payload"]["event_id"],
                "completed",
                response={"choice": "handle_now"},
            )
            follow_up_message = self.store.add_assistant_message(
                action["conversation_id"],
                "assistant",
                "好的。整理完成后，请到“安全”页面点“我已整理好”，小安会重新检查通道。",
                "proactive_rule",
            )
        elif action["kind"] == "safety_need_help_options":
            follow_up_message = self.store.add_assistant_message(
                action["conversation_id"],
                "assistant",
                "好的。您需要小安请家人联系您吗？",
                "proactive_rule",
            )
            contact_name = self.store.settings().get("contact_name") or "家人"
            follow_up_message["actions"] = [
                self.store.create_assistant_action(
                    action["conversation_id"],
                    follow_up_message["id"],
                    "contact_family",
                    f"确认联系{contact_name}",
                    {
                        "contact_name": contact_name,
                        "event_id": action["payload"]["event_id"],
                    },
                ),
                self.store.create_assistant_action(
                    action["conversation_id"],
                    follow_up_message["id"],
                    "safety_no_contact",
                    "暂时不联系",
                    {"event_id": action["payload"]["event_id"]},
                ),
            ]
        elif action["kind"] == "safety_no_contact":
            self.store.update_proactive_event(
                action["payload"]["event_id"],
                "completed",
                response={"choice": "no_contact"},
            )
        elif action["kind"] == "device_control_allow":
            self.store.update_settings({"assistant_device_control_consent": "allowed"})
            requested_tool = action["payload"].get("requested_tool")
            if requested_tool:
                tool_result = await self.device_tools.execute(str(requested_tool))
                tool_context, tool_context_used = self.context_builder.build()
                tool_context["device_tool_result"] = tool_result
                tool_context_used.append("刚刚调用的设备结果")
                follow_up_text, follow_up_sources, follow_up_source = (
                    await self.llm.chat_assistant(
                        str(action["payload"].get("resident_message") or "请告诉我结果"),
                        tool_context,
                        self.store.assistant_messages(
                            action["conversation_id"], limit=12
                        ),
                    )
                )
                follow_up_message = self.store.add_assistant_message(
                    action["conversation_id"],
                    "assistant",
                    follow_up_text,
                    follow_up_source,
                    sources=follow_up_sources,
                    context_used=tool_context_used,
                )
            self.store.dismiss_other_assistant_actions(action["message_id"], action_id)
        elif action["kind"] == "device_control_deny":
            self.store.update_settings({"assistant_device_control_consent": "denied"})
            self.store.dismiss_other_assistant_actions(action["message_id"], action_id)
        elif action["kind"] == "profile_onboarding_edit":
            follow_up_message = self._add_profile_onboarding_step(
                action["conversation_id"], int(action["payload"]["step_index"])
            )
        elif action["kind"] in {"profile_onboarding_choice", "profile_onboarding_skip"}:
            step_index = int(action["payload"].get("step_index", 0))
            step = onboarding_step(step_index)
            if step is not None:
                fact_type = str(step["fact_type"])
                self.store.expire_profile_facts_by_type(fact_type)
                skipped = action["kind"] == "profile_onboarding_skip"
                self.store.create_profile_fact(
                    fact_type=fact_type,
                    value=(
                        {"skipped": True}
                        if skipped
                        else {"choice": action["payload"]["value"]}
                    ),
                    display_text=(
                        f"{step['field_label']}：暂不填写"
                        if skipped
                        else str(action["payload"]["display_text"])
                    ),
                    source="guided_onboarding",
                    source_ref=action["message_id"],
                    confidence=1.0,
                    status="confirmed",
                )
            self.store.dismiss_other_assistant_actions(
                action["message_id"],
                action_id,
                ("profile_onboarding_choice", "profile_onboarding_skip"),
            )
            next_step = self._next_missing_profile_step()
            follow_up_message = (
                self._add_profile_onboarding_summary(action["conversation_id"])
                if next_step is None
                else self._add_profile_onboarding_step(
                    action["conversation_id"], next_step
                )
            )
        updated = self.store.update_assistant_action(action_id, "completed")
        if updated is not None and follow_up_message is not None:
            updated["follow_up_message"] = follow_up_message
        return updated

    def _add_profile_onboarding_step(
        self, conversation_id: str, step_index: int
    ) -> dict[str, Any]:
        step = onboarding_step(step_index)
        if step is None:
            return self.store.add_assistant_message(
                conversation_id,
                "assistant",
                "基本情况已经填写好了。以后聊天时，您同意记住的偏好也会显示在“我的画像”中，随时可以删除。",
                "guided_onboarding",
            )
        message = self.store.add_assistant_message(
            conversation_id,
            "assistant",
            str(step["question"]),
            "guided_onboarding",
        )
        actions = [
            self.store.create_assistant_action(
                conversation_id,
                message["id"],
                "profile_onboarding_choice",
                str(label),
                {
                    "step_index": step_index,
                    "fact_type": step["fact_type"],
                    "value": value,
                    "display_text": display_text,
                },
            )
            for value, label, display_text in step["choices"]
        ]
        actions.append(self.store.create_assistant_action(
            conversation_id,
            message["id"],
            "profile_onboarding_skip",
            "暂时不填",
            {"step_index": step_index, "fact_type": step["fact_type"]},
        ))
        message["actions"] = actions
        return message

    def _current_onboarding_facts(self) -> dict[str, dict[str, Any]]:
        facts: dict[str, dict[str, Any]] = {}
        for fact in self.store.profile_facts(("confirmed",), limit=100):
            fact_type = str(fact["fact_type"])
            if fact_type in PROFILE_ONBOARDING_FACT_TYPES and fact_type not in facts:
                facts[fact_type] = fact
        return facts

    def _next_missing_profile_step(self) -> int | None:
        current = self._current_onboarding_facts()
        for index, step in enumerate(PROFILE_ONBOARDING_STEPS):
            if str(step["fact_type"]) not in current:
                return index
        return None

    def _add_profile_onboarding_summary(self, conversation_id: str) -> dict[str, Any]:
        current = self._current_onboarding_facts()
        lines = [
            current[str(step["fact_type"])]["display_text"]
            for step in PROFILE_ONBOARDING_STEPS
            if str(step["fact_type"]) in current
        ]
        message = self.store.add_assistant_message(
            conversation_id,
            "assistant",
            "这些内容已经保存：\n" + "\n".join(f"• {line}" for line in lines)
            + "\n\n您可以保持不变，也可以只修改其中一项。",
            "guided_onboarding",
        )
        message["actions"] = [
            self.store.create_assistant_action(
                conversation_id,
                message["id"],
                "profile_onboarding_edit",
                f"修改{step['field_label']}",
                {"step_index": index, "fact_type": step["fact_type"]},
            )
            for index, step in enumerate(PROFILE_ONBOARDING_STEPS)
        ]
        return message

    def start_event(self, event_id: str) -> dict[str, Any] | None:
        event = self.store.get_proactive_event(event_id)
        if event is None:
            return None
        if event.get("conversation_id"):
            conversation = self.conversation(str(event["conversation_id"]))
            if conversation and conversation["messages"]:
                return {
                    "conversation_id": conversation["id"],
                    "assistant_message": conversation["messages"][-1],
                }
        conversation = self.store.create_assistant_conversation(event["title"])
        message = self.store.add_assistant_message(
            conversation["id"], "assistant", event["message"], "proactive_rule",
            context_used=[f"触发原因：{event['reason']}"],
        )
        if event["event_type"] == "environment_risk":
            actions = [
                self.store.create_assistant_action(
                    conversation["id"], message["id"], "safety_handle_now",
                    "我现在处理", {"event_id": event_id},
                ),
                self.store.create_assistant_action(
                    conversation["id"], message["id"], "defer_event",
                    "稍后提醒我", {"event_id": event_id},
                ),
                self.store.create_assistant_action(
                    conversation["id"], message["id"], "safety_need_help_options",
                    "我现在不方便处理", {"event_id": event_id},
                ),
            ]
        else:
            actions = [
                self.store.create_assistant_action(
                    conversation["id"], message["id"], "defer_event", "稍后再说",
                    {"event_id": event_id},
                ),
                self.store.create_assistant_action(
                    conversation["id"], message["id"], "pause_proactive_care", "暂停主动关怀",
                    {"event_id": event_id},
                ),
            ]
        message["actions"] = actions
        self.store.update_proactive_event(
            event_id, "engaged", conversation_id=conversation["id"]
        )
        return {"conversation_id": conversation["id"], "assistant_message": message}

    def _suggest_actions(
        self, message: str, assistant_message_id: str, conversation_id: str,
        candidate_facts: list[dict[str, Any]] | None = None,
        event_id: str | None = None,
        device_tool: str | None = None,
        device_consent: str = "unset",
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        if device_tool and device_consent == "unset":
            actions.append(self.store.create_assistant_action(
                conversation_id, assistant_message_id, "device_control_allow",
                "允许小安控制已连接设备",
                {"requested_tool": device_tool, "resident_message": message},
            ))
            actions.append(self.store.create_assistant_action(
                conversation_id, assistant_message_id, "device_control_deny",
                "暂不允许",
                {},
            ))
        contact_words = ("联系家人", "联系女儿", "联系儿子", "叫家人", "找家人", "通知家人")
        if any(word in message for word in contact_words):
            contact_name = self.store.settings().get("contact_name") or "家人"
            actions.append(self.store.create_assistant_action(
                conversation_id,
                assistant_message_id,
                "contact_family",
                f"确认联系{contact_name}",
                {"contact_name": contact_name},
            ))
        for fact in candidate_facts or []:
            actions.append(self.store.create_assistant_action(
                conversation_id, assistant_message_id, "remember_profile_fact",
                f"记住：{fact['display_text']}", {"fact_id": fact["id"]},
            ))
            actions.append(self.store.create_assistant_action(
                conversation_id, assistant_message_id, "reject_profile_fact",
                "不用记", {"fact_id": fact["id"]},
            ))
        intervention_id = None
        if any(word in message for word in ("睡不着", "不好睡", "想听白噪音")):
            intervention_id = "white_noise_30min"
        elif any(word in message for word in ("紧张", "担心", "后怕", "放松")):
            intervention_id = "relaxation_5min"
        if intervention_id:
            resource = intervention(intervention_id)
            if resource:
                actions.append(self.store.create_assistant_action(
                    conversation_id, assistant_message_id, "start_intervention",
                    resource["title"], {
                        "intervention_id": intervention_id, "event_id": event_id,
                    },
                ))
        return actions
