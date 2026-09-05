package com.ehagent.resident

data class DailyConversationUpdate(val reset: Boolean = false, val startEventId: String? = null)

fun dailyConversationUpdate(
    reportId: String?,
    previousReportId: String?,
    eventId: String?,
    eventReportId: String?,
    selectedEventId: String?,
    busy: Boolean,
    paused: Boolean,
): DailyConversationUpdate {
    if (reportId == null || busy) return DailyConversationUpdate()
    val reset = previousReportId != null && previousReportId != reportId
    val start = eventId?.takeIf {
        !paused && eventReportId == reportId && it != selectedEventId
    }
    return DailyConversationUpdate(reset, start)
}
