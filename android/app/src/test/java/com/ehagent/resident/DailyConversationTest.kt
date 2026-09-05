package com.ehagent.resident

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DailyConversationTest {
    @Test fun `new morning clears old chat and starts matching care`() {
        val result = dailyConversationUpdate("night4", "night3", "care4", "night4", "care3", false, false)
        assertTrue(result.reset)
        assertEquals("care4", result.startEventId)
    }
    @Test fun `same day refresh never repeats an opened care`() {
        val result = dailyConversationUpdate("night4", "night4", "care4", "night4", "care4", false, false)
        assertFalse(result.reset)
        assertNull(result.startEventId)
    }
    @Test fun `sending message defers day change`() {
        val result = dailyConversationUpdate("night4", "night3", "care4", "night4", "care3", true, false)
        assertFalse(result.reset)
        assertNull(result.startEventId)
    }
    @Test fun `stable next morning clears yesterday without manufacturing care`() {
        val result = dailyConversationUpdate("night7", "night6", null, null, "care6", false, false)
        assertTrue(result.reset)
        assertNull(result.startEventId)
    }
    @Test fun `old events and paused care cannot open automatically`() {
        assertNull(dailyConversationUpdate("night4", "night3", "care3", "night3", null, false, false).startEventId)
        assertNull(dailyConversationUpdate("night4", "night3", "care4", "night4", null, false, true).startEventId)
    }
    @Test fun `upgrade switches to unopened current care without erasing unrelated history`() {
        val result = dailyConversationUpdate("night4", null, "care4", "night4", null, false, false)
        assertFalse(result.reset)
        assertEquals("care4", result.startEventId)
    }
}
