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
