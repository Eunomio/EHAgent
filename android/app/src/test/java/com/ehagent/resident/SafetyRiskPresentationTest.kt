package com.ehagent.resident

import org.junit.Assert.assertEquals
import org.junit.Test

class SafetyRiskPresentationTest {
    @Test
    fun riskLevelsHaveDistinctUserFacingLabels() {
        assertEquals("未检测到风险", safetyRiskLabel("clear"))
        assertEquals("低风险", safetyRiskLabel("low"))
        assertEquals("中风险", safetyRiskLabel("medium"))
        assertEquals("高风险", safetyRiskLabel("high"))
        assertEquals("通道阻塞", safetyRiskLabel("blocked"))
        assertEquals("画面不清楚", safetyRiskLabel("insufficient"))
    }

    @Test
    fun riskLevelsHaveDistinctCardColors() {
        val colors = listOf("clear", "low", "medium", "high", "blocked", "insufficient")
            .map(::safetyRiskBackground)

        assertEquals(colors.size, colors.distinct().size)
    }
}
