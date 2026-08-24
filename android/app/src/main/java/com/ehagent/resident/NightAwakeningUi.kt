package com.ehagent.resident

internal fun NightAwakening.attentionText(): String = when {
    state == "resolved" -> "最近一次起夜已结束"
    attention == "extra_care" -> "需要多留意"
    attention == "routine_care" -> "一般关注"
    attention == "insufficient" -> "数据不足"
    else -> "尚未监测到起夜"
}

internal fun NightAwakening.shouldAutoExpand(lastExpandedId: String?): Boolean =
    state == "active" &&
        attention == "extra_care" &&
        id != null &&
        id != lastExpandedId

internal fun shouldAutoLoadSleepDemo(
    sleepDuration: Int?,
    alreadyAttempted: Boolean,
): Boolean = sleepDuration == null && !alreadyAttempted
