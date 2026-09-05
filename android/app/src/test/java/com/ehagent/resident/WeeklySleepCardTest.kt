package com.ehagent.resident

import org.junit.Assert.assertEquals
import org.junit.Test

class WeeklySleepCardTest {
    @Test fun `duration chart includes zero and expands for longer nights`() {
        assertEquals(8, weeklyChartMaximumHours(emptyList()))
        assertEquals(8, weeklyChartMaximumHours(listOf(WeeklySleepNight("2026-08-18", 431))))
        assertEquals(10, weeklyChartMaximumHours(listOf(WeeklySleepNight("2026-08-18", 580))))
    }
    @Test fun `missing vitals are not displayed as zero`() {
        assertEquals("暂无记录", weeklyRate(null))
    }
    @Test fun `rates have clear units and no redundant decimal`() {
        assertEquals("61 次/分", weeklyRate(61.0))
        assertEquals("14.2 次/分", weeklyRate(14.2))
    }
}
