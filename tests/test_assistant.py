def test_assistant_uses_sleep_context_and_keeps_conversation(client) -> None:
    sleep = {
        "external_report_id": "assistant-sleep-20260817",
        "device_serial": "SLEEP001",
        "sleep_start": "2026-08-16T22:30:00+08:00",
        "sleep_end": "2026-08-17T05:50:00+08:00",
        "duration_minutes": 440,
        "respiratory_rate": 16.2,
        "heart_rate": 62.0,
        "bed_exit_count": 1,
        "quality": "good",
        "source": "ezviz_sleep_assistant",
        "measured_at": "2026-08-17T06:00:00+08:00",
    }
    assert client.post("/api/v1/ingest/sleep-reports", json=sleep).status_code == 200

    response = client.post(
        "/api/v1/assistant/chat", json={"message": "昨晚睡得怎么样？"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert "7小时20分钟" in payload["assistant_message"]["content"]
    assert "最近一次睡眠摘要" in payload["assistant_message"]["context_used"]

    conversation = client.get(
        f"/api/v1/assistant/conversations/{payload['conversation_id']}"
    ).json()
    assert [item["role"] for item in conversation["messages"]] == ["user", "assistant"]


def test_assistant_requires_confirmation_before_contacting_family(client) -> None:
    response = client.post(
        "/api/v1/assistant/chat", json={"message": "帮我联系家人"}
    )
    payload = response.json()
    action = payload["assistant_message"]["actions"][0]
    assert action["status"] == "pending"
    assert client.get("/api/v1/resident/help").json()["requests"] == []

    confirmed = client.post(
        f"/api/v1/assistant/actions/{action['id']}/confirm"
    ).json()
    assert confirmed["status"] == "completed"
    requests = client.get("/api/v1/resident/help").json()["requests"]
    assert len(requests) == 1
    assert requests[0]["request_type"] == "assistant"

    client.post(f"/api/v1/assistant/actions/{action['id']}/confirm")
    assert len(client.get("/api/v1/resident/help").json()["requests"]) == 1


def test_missing_assistant_conversation_returns_404(client) -> None:
    response = client.get("/api/v1/assistant/conversations/missing")
    assert response.status_code == 404


def test_sleep_demo_uses_existing_proactive_conversation(client) -> None:
    loaded = client.post("/api/v1/devices/sleep/demo")
    assert loaded.status_code == 200
    event = client.get("/api/v1/resident/dashboard").json()["care"]["active"]
    assert "昨天半夜醒了" in event["message"]

    started = client.post(f"/api/v1/assistant/events/{event['id']}/start").json()
    conversation_id = started["conversation_id"]
    first = client.post(
        "/api/v1/assistant/chat",
        json={
            "conversation_id": conversation_id,
            "message": "哎呀，我昨晚起来以后再躺下就睡不着了，白天也没有精神。",
        },
    ).json()
    assert "身体不舒服" in first["assistant_message"]["content"]

    second = client.post(
        "/api/v1/assistant/chat",
        json={
            "conversation_id": conversation_id,
            "message": "身体没有不舒服，就是脑子清醒了，后来一直睡不着。",
        },
    ).json()
    assert "轻柔的白噪音" in second["assistant_message"]["content"]


def test_device_control_asks_once_then_executes_without_repeating_consent(client) -> None:
    first = client.post(
        "/api/v1/assistant/chat", json={"message": "请暂停摄像头"}
    ).json()
    actions = first["assistant_message"]["actions"]
    assert [item["kind"] for item in actions] == [
        "device_control_allow", "device_control_deny",
    ]
    assert client.get("/api/v1/resident/settings").json()["camera_paused"] is False

    allowed = client.post(f"/api/v1/assistant/actions/{actions[0]['id']}/confirm").json()
    assert allowed["status"] == "completed"
    assert allowed["follow_up_message"]["content"] == "已暂停通道检查。"
    settings = client.get("/api/v1/resident/settings").json()
    assert settings["assistant_device_control_consent"] == "allowed"
    assert settings["camera_paused"] is True

    conversation = client.get(
        f"/api/v1/assistant/conversations/{first['conversation_id']}"
    ).json()
    permission_actions = conversation["messages"][-2]["actions"]
    assert permission_actions[1]["status"] == "dismissed"

    second = client.post(
        "/api/v1/assistant/chat",
        json={
            "conversation_id": first["conversation_id"],
            "message": "现在恢复摄像头",
        },
    ).json()
    assert not any(
        item["kind"].startswith("device_control_")
        for item in second["assistant_message"]["actions"]
    )
    assert client.get("/api/v1/resident/settings").json()["camera_paused"] is False


def test_denied_device_control_does_not_ask_again(client) -> None:
    first = client.post(
        "/api/v1/assistant/chat", json={"message": "关闭睡眠提醒"}
    ).json()
    deny = next(
        item for item in first["assistant_message"]["actions"]
        if item["kind"] == "device_control_deny"
    )
    client.post(f"/api/v1/assistant/actions/{deny['id']}/confirm")

    second = client.post(
        "/api/v1/assistant/chat", json={"message": "关闭睡眠提醒"}
    ).json()
    assert second["assistant_message"]["actions"] == []
    settings = client.get("/api/v1/resident/settings").json()
    assert settings["assistant_device_control_consent"] == "denied"
    assert settings["sleep_alerts_paused"] is False


def test_semantic_home_request_invokes_camera_and_vlm_tool(client) -> None:
    client.put(
        "/api/v1/resident/settings",
        json={"assistant_device_control_consent": "allowed"},
    )
    client.app.state.settings.ezviz_device_serial = "TEST-CAMERA"
    client.app.state.ezviz._token = "test-token"
    called = False

    async def analyze(_ezviz) -> dict:
        nonlocal called
        called = True
        return {
            "checked_at": "2026-08-31T14:00:00+08:00",
            "reason": "当前通道与安全基准一致，未见新增障碍物。",
            "evidence_path": "semantic-camera-check.jpg",
            "assessment": {
                "risk_level": "clear",
                "headline": "通道畅通",
                "action_text": "保持通道整洁",
            },
        }

    client.app.state.vision_safety.analyze = analyze
    response = client.post(
        "/api/v1/assistant/chat", json={"message": "帮我看看我家现在怎么样"}
    )
    assert response.status_code == 200
    assert called is True
    content = response.json()["assistant_message"]["content"]
    assert "刚刚通过摄像头检查" in content
    assert "通道畅通" in content
    assert client.app.state.store.recent_checks(1)[0]["source"] == "assistant_device_tool"


def test_guided_profile_onboarding_saves_visible_choice_and_continues(client) -> None:
    started = client.post("/api/v1/assistant/profile-onboarding/start")
    assert started.status_code == 200
    first = started.json()["assistant_message"]
    assert "和谁一起住" in first["content"]
    assert [item["label"] for item in first["actions"]] == [
        "我一个人住", "只和老伴一起住", "和子女或其他家人一起住", "其他居住安排", "暂时不填",
    ]

    selected = client.post(
        f"/api/v1/assistant/actions/{first['actions'][0]['id']}/confirm"
    ).json()
    assert "需要长期管理的疾病" in selected["follow_up_message"]["content"]
    visible = client.get("/api/v1/resident/profile").json()["visible"]
    assert visible[0]["display_text"] == "居住情况：一个人住"
    assert visible[0]["source"] == "guided_onboarding"
    assert visible[0]["status"] == "confirmed"


def test_completed_profile_onboarding_reopens_saved_summary(client) -> None:
    started = client.post("/api/v1/assistant/profile-onboarding/start").json()
    message = started["assistant_message"]
    for _ in range(5):
        selected = client.post(
            f"/api/v1/assistant/actions/{message['actions'][0]['id']}/confirm"
        ).json()
        message = selected["follow_up_message"]

    assert "这些内容已经保存" in message["content"]
    assert all(item["kind"] == "profile_onboarding_edit" for item in message["actions"])
    reopened = client.post("/api/v1/assistant/profile-onboarding/start").json()[
        "assistant_message"
    ]
    assert "这些内容已经保存" in reopened["content"]
    assert [item["label"] for item in reopened["actions"]] == [
        "修改居住情况",
        "修改健康情况",
        "修改提醒内容",
        "修改提醒方式",
        "修改家人联系规则",
    ]


def test_profile_onboarding_skip_is_saved_and_visible(client) -> None:
    first = client.post("/api/v1/assistant/profile-onboarding/start").json()[
        "assistant_message"
    ]
    skipped = client.post(
        f"/api/v1/assistant/actions/{first['actions'][-1]['id']}/confirm"
    ).json()
    assert "需要长期管理的疾病" in skipped["follow_up_message"]["content"]
    visible = client.get("/api/v1/resident/profile").json()["visible"]
    assert visible[0]["display_text"] == "居住情况：暂不填写"


def test_explicit_health_condition_requires_confirmation(client) -> None:
    response = client.post(
        "/api/v1/assistant/chat", json={"message": "医生说我有高血压。"}
    ).json()
    actions = response["assistant_message"]["actions"]
    remember = next(item for item in actions if item["kind"] == "remember_profile_fact")
    assert "高血压" in remember["label"]
    assert client.get("/api/v1/resident/profile").json()["confirmed"] == []


def test_low_sensitivity_preference_is_visible_ambient_memory(client) -> None:
    response = client.post(
        "/api/v1/assistant/chat", json={"message": "我喜欢早上听戏"}
    ).json()
    assert not any(
        item["kind"] == "remember_profile_fact"
        for item in response["assistant_message"]["actions"]
    )
    profile = client.get("/api/v1/resident/profile").json()
    assert profile["inferred"][0]["display_text"] == "喜欢早上听戏"
    assert profile["inferred"][0]["status"] == "inferred"
    assert profile["visible"][0]["id"] == profile["inferred"][0]["id"]


def test_night_awakening_offers_white_noise_and_starts_only_after_consent(client) -> None:
    response = client.post(
        "/api/v1/assistant/chat",
        json={"message": "我起夜以后很难再次入睡"},
    )
    assert response.status_code == 200
    message = response.json()["assistant_message"]
    assert "白噪音" in message["content"]
    action = next(
        item for item in message["actions"]
        if item["kind"] == "start_intervention"
    )
    assert action["payload"]["intervention_id"] == "white_noise_30min"
    assert client.app.state.store.intervention_sessions(limit=10) == []

    confirmed = client.post(
        f"/api/v1/assistant/actions/{action['id']}/confirm"
    ).json()
    assert confirmed["status"] == "completed"
    assert "正在为您选择" in confirmed["follow_up_message"]["content"]
    assert "上一首和下一首" in confirmed["follow_up_message"]["content"]
    sessions = client.app.state.store.intervention_sessions(limit=10)
    assert sessions[0]["intervention_id"] == "white_noise_30min"
