from typing import Any

PROFILE_ONBOARDING_STEPS: tuple[dict[str, Any], ...] = (
    {
        "question": "为了以后更合适地关心您，我想请您做五个简单选择。您现在通常和谁一起住？",
        "fact_type": "living_arrangement",
        "field_label": "居住情况",
        "choices": (
            ("alone", "我一个人住", "居住情况：一个人住"),
            ("partner_only", "只和老伴一起住", "居住情况：只和老伴一起住"),
            ("family", "和子女或其他家人一起住", "居住情况：和子女或其他家人一起住"),
            ("other", "其他居住安排", "居住情况：其他居住安排"),
        ),
    },
    {
        "question": "您目前是否有经医生确认、需要长期管理的疾病？",
        "fact_type": "health_management_status",
        "field_label": "健康情况",
        "choices": (
            ("none", "没有", "健康情况：没有需要长期管理的疾病"),
            ("managed_no_daily_impact", "有，不影响平时生活", "健康情况：有长期管理的疾病，目前不影响平时生活"),
            ("daily_impact", "有，会影响日常生活", "健康情况：有长期管理的疾病，会影响走路、睡眠或日常生活"),
            ("unsure", "不确定", "健康情况：是否有需要长期管理的疾病尚不确定"),
        ),
    },
    {
        "question": "小安提醒您时，您希望一次说多少内容？",
        "fact_type": "reminder_detail_preference",
        "field_label": "提醒内容",
        "choices": (
            ("brief", "先说重点", "提醒内容：先说重点"),
            ("standard", "说明原因和建议", "提醒内容：说明原因和建议"),
            ("detailed", "再详细一些", "提醒内容：详细说明原因、建议和下一步"),
        ),
    },
    {
        "question": "小安提醒您时，您希望通过哪种方式接收？",
        "fact_type": "interaction_mode_preference",
        "field_label": "提醒方式",
        "choices": (
            ("voice", "主要听语音", "提醒方式：主要使用语音"),
            ("voice_and_screen", "语音和屏幕一起", "提醒方式：语音和屏幕同时呈现"),
            ("screen", "主要看屏幕文字", "提醒方式：主要使用屏幕文字"),
        ),
    },
    {
        "question": "如果小安发现您可能需要家人帮助，应该怎样联系家人？",
        "fact_type": "sharing_preference",
        "field_label": "家人联系规则",
        "choices": (
            (
                "urgent_direct",
                "只有紧急时可直接联系",
                "家人联系规则：仅明确紧急情况可直接联系，其他情况先询问本人",
            ),
            ("ask_every_time", "每次都先问我", "家人联系规则：包括紧急情况在内，每次联系前都先询问本人"),
            ("never_contact", "不要主动联系家人", "家人联系规则：小安不主动联系家人"),
        ),
    },
)


PROFILE_ONBOARDING_FACT_TYPES = tuple(
    str(step["fact_type"]) for step in PROFILE_ONBOARDING_STEPS
)


def onboarding_step(index: int) -> dict[str, Any] | None:
    if index < 0 or index >= len(PROFILE_ONBOARDING_STEPS):
        return None
    return PROFILE_ONBOARDING_STEPS[index]
