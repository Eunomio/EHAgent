package com.ehagent.resident

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NightAwakeningTest {
    @Test
    fun `missing object fields remain backward compatible`() {
        val result = JSONObject("{}").toNightAwakening()
        assertEquals("waiting", result.state)
        assertEquals("尚未监测到起夜", result.message)
        assertTrue(result.reasons.isEmpty())
    }

    @Test
    fun `all five card presentations have explicit text`() {
        assertEquals("尚未监测到起夜", NightAwakening().attentionText())
        assertEquals(
            "一般关注",
            NightAwakening(state = "active", attention = "routine_care").attentionText(),
        )
        assertEquals(
            "需要多留意",
            NightAwakening(state = "active", attention = "extra_care").attentionText(),
        )
        assertEquals(
            "数据不足",
            NightAwakening(state = "active", attention = "insufficient").attentionText(),
        )
        assertEquals(
            "最近一次起夜已结束",
            NightAwakening(state = "resolved", attention = "extra_care").attentionText(),
        )
    }

    @Test
    fun `extra care event auto expands only once`() {
        val event = NightAwakening(id = "event-1", state = "active", attention = "extra_care")
        assertTrue(event.shouldAutoExpand(null))
        assertFalse(event.shouldAutoExpand("event-1"))
        assertFalse(NightAwakening(id = "event-2").shouldAutoExpand(null))
    }

    @Test
    fun `empty first install attempts demo import only once`() {
        assertTrue(shouldAutoLoadSleepDemo(sleepDuration = null, alreadyAttempted = false))
        assertFalse(shouldAutoLoadSleepDemo(sleepDuration = null, alreadyAttempted = true))
        assertFalse(shouldAutoLoadSleepDemo(sleepDuration = 440, alreadyAttempted = false))
    }

    @Test
    fun `optional reason fields and long copy are retained`() {
        val longMessage = "这是一段用于验证较长中文提示能够完整解析并交给界面换行展示的文字。"
        val result = JSONObject(
            """{
                "state":"active",
                "attention":"extra_care",
                "message":"$longMessage",
                "reasons":[{
                    "metric":"duration_minutes",
                    "label":"睡眠时长",
                    "current":330,
                    "baseline_median":440,
                    "difference":-110,
                    "direction":"lower",
                    "comparison_status":"changed",
                    "adverse_change":true
                }]
            }""",
        ).toNightAwakening()
        assertEquals(longMessage, result.message)
        assertEquals(-110.0, result.reasons.single().difference!!, 0.0)
        assertTrue(result.reasons.single().adverseChange)
    }
}
