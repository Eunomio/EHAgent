import asyncio
import json

import httpx
import pytest

from app.core.config import Settings
from app.llm.service import LlmService, WhiteNoiseDecision


@pytest.mark.parametrize("decision,expected_count,auto_start", [
    ("offer", 1, False), ("play_now", 1, True), ("defer", 0, False),
    ("decline", 0, False), ("none", 0, False),
])
def test_model_decision_creates_playback_contract(
    client, monkeypatch, decision, expected_count, auto_start,
):
    async def reply(message, context, history):
        return "需要的话，可以听一会儿白噪音。", [], "llm"

    async def plan(message, reply, history):
        return WhiteNoiseDecision(action=decision)

    monkeypatch.setattr(client.app.state.llm, "chat_assistant", reply)
    monkeypatch.setattr(client.app.state.llm, "plan_white_noise", plan)
    result = client.post("/api/v1/assistant/chat", json={"message": "先聊聊吧"}).json()
    actions = result["assistant_message"]["actions"]
    assert len(actions) == expected_count
    assert client.app.state.store.intervention_sessions() == []
    if actions:
        action = actions[0]
        assert action["payload"]["intervention_id"] == "white_noise_30min"
        assert action["payload"]["auto_start"] is auto_start
        assert "播放" in action["label"]
        for _ in range(2):
            assert client.post(f"/api/v1/assistant/actions/{action['id']}/confirm").status_code == 200
        assert len(client.app.state.store.intervention_sessions()) == 1


def test_white_noise_model_receives_history_and_failure_cannot_autoplay():
    async def scenario():
        def handler(request):
            body = json.loads(request.content)
            assert body["text"]["format"]["name"] == "white_noise_action"
            assert "绝不能自动播放" in body["instructions"]
            assert "要现在听吗" in body["input"]
            return httpx.Response(503)

        settings = Settings(llm_enabled=True, llm_api_key="test", llm_provider="openai")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            service = LlmService(settings, http)
            result = await service.plan_white_noise(
                "好", "准备播放", [{"role": "assistant", "content": "要现在听吗"}],
            )
            assert result.action == "none"

    asyncio.run(scenario())
