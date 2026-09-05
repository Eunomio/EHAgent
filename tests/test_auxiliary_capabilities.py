import pytest


@pytest.mark.parametrize("message", [
    "我有些紧张，想做放松练习", "带我做呼吸练习", "我想冥想",
    "打开睡前准备清单", "帮我做烦恼梳理", "把担心的事理一理",
])
def test_unavailable_request_is_explained_without_execution(client, message, monkeypatch):
    async def should_not_claim_execution(*args, **kwargs):
        raise AssertionError("Unavailable exercises must not be delegated to generation")

    monkeypatch.setattr(client.app.state.llm, "chat_assistant", should_not_claim_execution)
    result = client.post("/api/v1/assistant/chat", json={"message": message})
    assert result.status_code == 200
    reply = result.json()["assistant_message"]
    assert "小安现在还不能" in reply["content"]
    assert "播放助眠声音" in reply["content"]
    assert "稍后" not in reply["content"]
    assert reply["actions"] == []
    assert client.app.state.store.intervention_sessions() == []


def test_only_playable_resource_is_advertised(client):
    result = client.get("/api/v1/resident/care/interventions").json()
    assert [item["id"] for item in result["items"]] == ["white_noise_30min"]


def test_suggested_alternative_has_a_playback_action(client):
    result = client.post("/api/v1/assistant/chat", json={"message": "播放助眠声音"}).json()
    actions = result["assistant_message"]["actions"]
    assert any(a["payload"].get("intervention_id") == "white_noise_30min" for a in actions)


@pytest.mark.parametrize("resource", ["relaxation_5min", "sleep_preparation", "worry_sorting", "unknown"])
@pytest.mark.parametrize("status", ["pending", "completed"])
def test_legacy_actions_cannot_create_fake_sessions(client, resource, status):
    store = client.app.state.store
    conversation = store.create_assistant_conversation("旧对话")
    message = store.add_assistant_message(conversation["id"], "assistant", "旧按钮", "template")
    action = store.create_assistant_action(
        conversation["id"], message["id"], "start_intervention", "旧练习", {"intervention_id": resource}
    )
    store.update_assistant_action(action["id"], status)
    for _ in range(2):
        result = client.post(f"/api/v1/assistant/actions/{action['id']}/confirm")
        assert result.status_code == 200
        assert result.json()["status"] == "unsupported"
        assert "现在还不能" in result.json()["follow_up_message"]["content"]
    assert store.intervention_sessions() == []


def test_emotion_alone_does_not_offer_unavailable_exercise(client):
    result = client.post("/api/v1/assistant/chat", json={"message": "我有点担心"}).json()
    assert not any(a["payload"].get("intervention_id") == "relaxation_5min"
                   for a in result["assistant_message"]["actions"])
