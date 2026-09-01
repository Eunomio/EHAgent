"""Fixed, reviewable self-help resources used by the proactive assistant."""

from typing import Any

INTERVENTIONS: dict[str, dict[str, Any]] = {
    "relaxation_5min": {
        "id": "relaxation_5min",
        "title": "5分钟放松练习",
        "summary": "跟着小安放慢节奏，做一段不憋气的舒缓练习。",
        "duration_minutes": 5,
        "kind": "guided_relaxation",
        "content": [
            "先找一个坐稳、靠稳的位置。",
            "按平时舒服的节奏呼吸，不需要深吸或憋气。",
            "把注意力依次放到肩膀、双手和双腿，慢慢放松。",
            "如果感到头晕、胸闷或不舒服，请立即停止。",
        ],
        "review_status": "prototype",
    },
    "white_noise_30min": {
        "id": "white_noise_30min",
        "title": "30分钟睡前白噪音",
        "summary": "以较低音量播放，30分钟后自动停止。",
        "duration_minutes": 30,
        "kind": "audio",
        "content": ["请保持音量轻柔，不要遮住警报、门铃或家人的声音。"],
        "review_status": "prototype",
    },
    "sleep_preparation": {
        "id": "sleep_preparation",
        "title": "睡前准备清单",
        "summary": "检查照明、通道、饮水和睡前安排。",
        "duration_minutes": 3,
        "kind": "checklist",
        "content": [
            "把夜间常走的通道整理畅通。",
            "把灯或手电放在伸手可及的位置。",
            "睡前减少让自己持续紧张的信息。",
            "身体不舒服时及时联系家人或医生。",
        ],
        "review_status": "prototype",
    },
    "worry_sorting": {
        "id": "worry_sorting",
        "title": "把担心的事理一理",
        "summary": "分清现在能做的事和需要别人帮助的事。",
        "duration_minutes": 5,
        "kind": "structured_self_help",
        "content": [
            "先说出现在最担心的一件事。",
            "找出今天能够完成的一小步。",
            "需要家人、医生或其他人协助的事情单独记下来。",
        ],
        "review_status": "prototype",
    },
}


def intervention_list() -> list[dict[str, Any]]:
    return [dict(item) for item in INTERVENTIONS.values()]


def intervention(intervention_id: str) -> dict[str, Any] | None:
    item = INTERVENTIONS.get(intervention_id)
    return dict(item) if item else None
