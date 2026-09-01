from datetime import datetime, timedelta, timezone

from app.care.rules import create_sleep_change_event
from app.core.config import Settings
from app.vision.workflow import record_safety_result


def test_conversation_fact_requires_explicit_confirmation(client) -> None:
    response = client.post(
        "/api/v1/assistant/chat",
        json={"message": "我前些天差点摔倒，现在起夜时有点担心。"},
    )
    assert response.status_code == 200
    message = response.json()["assistant_message"]
    kinds = [item["kind"] for item in message["actions"]]
    assert "remember_profile_fact" in kinds
    assert "reject_profile_fact" in kinds

    profile = client.get("/api/v1/resident/profile").json()
    assert profile["confirmed"] == []
    assert profile["pending_confirmation"]

    remember = next(
        item for item in message["actions"] if item["kind"] == "remember_profile_fact"
    )
    confirmed = client.post(f"/api/v1/assistant/actions/{remember['id']}/confirm")
    assert confirmed.status_code == 200
    profile = client.get("/api/v1/resident/profile").json()
    assert len(profile["confirmed"]) == 1
    assert profile["confirmed"][0]["status"] == "confirmed"


def test_profile_fact_can_be_deleted(client) -> None:
    created = client.post(
        "/api/v1/resident/profile/facts",
        json={
            "fact_type": "reminder_preference",
            "display_text": "希望小安说慢一点",
            "value": {"speech_style": "slow"},
        },
    ).json()
    assert client.delete(f"/api/v1/resident/profile/facts/{created['id']}").status_code == 200
    assert client.get("/api/v1/resident/profile").json()["confirmed"] == []


def test_vlm_result_creates_one_proactive_event(client) -> None:
    store = client.app.state.store
    settings = Settings(database_path=store.path, evidence_root=store.path.parent / "evidence")
    result = {
        "checked_at": "2026-08-30T10:00:00+08:00",
        "reason": "纸箱位于通道中部，需要绕开。",
        "evidence_path": "risk.jpg",
        "assessment": {
            "risk_level": "medium",
            "headline": "通道需要整理",
            "action_text": "请把纸箱移到通道外",
        },
    }
    record_safety_result(store, settings, result, "camera_safety_auto")
    events = client.get("/api/v1/resident/care/events").json()
    created = events["items"][0]
    assert created["event_type"] == "environment_risk"
    assert "VLM" in created["reason"]
    assert "需要家人帮忙" not in created["message"]
    assert "您现在方便处理吗" in created["message"]

    started = client.post(f"/api/v1/assistant/events/{created['id']}/start")
    assert started.status_code == 200
    started_message = started.json()["assistant_message"]
    assert "为什么询问" not in started_message["content"]
    assert started_message["context_used"][0].startswith("触发原因")
    assert [item["label"] for item in started_message["actions"]] == [
        "我现在处理", "稍后提醒我", "我现在不方便处理",
    ]

    need_help = client.post(
        f"/api/v1/assistant/actions/{started_message['actions'][2]['id']}/confirm"
    ).json()["follow_up_message"]
    assert "需要小安请家人联系" in need_help["content"]
    assert [item["label"] for item in need_help["actions"]] == [
        "确认联系家人", "暂时不联系",
    ]


def test_sleep_event_requires_two_consecutive_changed_nights(client) -> None:
    store = client.app.state.store
    base = datetime(2026, 8, 1, 6, 30, tzinfo=timezone(timedelta(hours=8)))

    def add_night(index: int, duration: int) -> dict:
        end = base + timedelta(days=index)
        start = end - timedelta(minutes=duration)
        return store.add_sleep({
            "external_report_id": f"night-{index}",
            "device_serial": "SLEEP001",
            "report_date": end.date().isoformat(),
            "timezone": "Asia/Shanghai",
            "sleep_start": start.isoformat(),
            "sleep_end": end.isoformat(),
            "duration_minutes": duration,
            "respiratory_rate": 14.0,
            "heart_rate": 62.0,
            "bed_exit_count": 1,
            "quality": "usable",
            "data_status": "final",
            "source": "ezviz_sleep_assistant",
            "measured_at": end.isoformat(),
            "samples": [],
            "stages": [],
        })

    for index in range(7):
        add_night(index, 440)
    first_changed = add_night(7, 300)
    assert create_sleep_change_event(store, first_changed) is None
    second_changed = add_night(8, 290)
    event = create_sleep_change_event(store, second_changed)
    assert event is not None
    assert event["event_type"] == "sleep_change"
    assert "连续两晚" in event["reason"]


def test_proactive_pause_blocks_new_normal_events(client) -> None:
    client.put("/api/v1/resident/settings", json={"proactive_care_paused": True})
    created = client.app.state.store.create_proactive_event(
        "sleep_change", "想问问您", "今天感觉怎么样？", "测试规则",
        "test", "event-1",
    )
    assert created is None
