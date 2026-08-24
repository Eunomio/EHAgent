package com.ehagent.resident

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class SafetyCard(val status: String = "ready", val headline: String = "等待下一次检查", val detail: String = "", val taskId: String? = null)
data class BaselineMetric(
    val label: String,
    val current: Double?,
    val baselineMedian: Double?,
    val difference: Double?,
    val status: String,
)
data class NightAwakeningReason(
    val metric: String,
    val label: String,
    val current: Double?,
    val baselineMedian: Double?,
    val difference: Double?,
    val direction: String?,
    val comparisonStatus: String,
    val adverseChange: Boolean,
)
data class NightAwakening(
    val id: String? = null,
    val state: String = "waiting",
    val attention: String? = null,
    val detectedAt: String? = null,
    val eventInterfaceStatus: String? = null,
    val snapshotStatus: String? = null,
    val message: String = "尚未监测到起夜",
    val reasons: List<NightAwakeningReason> = emptyList(),
    val guidance: List<String> = emptyList(),
    val disclaimer: String = "这是根据睡眠变化给出的预防性提示，不代表已经预测到跌倒。",
)
data class SleepCard(
    val headline: String = "睡眠数据暂未同步",
    val duration: Int? = null,
    val respiratoryRate: Double? = null,
    val heartRate: Double? = null,
    val bedExitCount: Int? = null,
    val analysis: String? = null,
    val sleepStart: String? = null,
    val sleepEnd: String? = null,
    val sleepScore: Double? = null,
    val awakeMinutes: Int? = null,
    val lightSleepMinutes: Int? = null,
    val deepSleepMinutes: Int? = null,
    val remSleepMinutes: Int? = null,
    val baselineState: String = "no_data",
    val baselineMessage: String? = null,
    val baselineNights: Int = 0,
    val baselineMetrics: List<BaselineMetric> = emptyList(),
    val dataSource: String? = null,
    val syncStatus: String? = null,
    val syncMessage: String? = null,
    val nightAwakening: NightAwakening = NightAwakening(),
)
data class Dashboard(val greeting: String = "您好", val subtitle: String = "今天也安心生活", val safety: SafetyCard = SafetyCard(), val sleep: SleepCard = SleepCard(), val contactName: String = "家人", val contactPhone: String = "")
data class DeviceState(
    val cameraConfigured: Boolean = false,
    val cameraOnline: Boolean? = null,
    val sleepConfigured: Boolean = false,
    val sleepLastReportAt: String? = null,
    val sleepDemoActive: Boolean = false,
)
data class CameraSdkSession(
    val appKey: String,
    val accessToken: String,
    val deviceSerial: String,
    val channelNo: Int,
    val verifyCode: String,
)
data class SafetyBaselineStatus(
    val ready: Boolean = false,
    val capturedAt: String? = null,
)
data class SafetyAnalysis(
    val riskLevel: String,
    val headline: String,
    val actionText: String,
    val reason: String,
    val checkedAt: String,
)
data class AssistantSource(val title: String, val url: String)
data class AssistantAction(val id: String, val label: String, val status: String)
data class AssistantMessage(
    val id: String,
    val role: String,
    val content: String,
    val sources: List<AssistantSource> = emptyList(),
    val contextUsed: List<String> = emptyList(),
    val actions: List<AssistantAction> = emptyList(),
)
data class AssistantChatResult(
    val conversationId: String,
    val userMessage: AssistantMessage,
    val assistantMessage: AssistantMessage,
)

class ProductApi(private val baseUrl: String) {
    private suspend fun request(
        path: String,
        method: String = "GET",
        body: JSONObject? = null,
        readTimeoutMillis: Int = 15_000,
    ): JSONObject = withContext(Dispatchers.IO) {
        val connection = URL(baseUrl.trimEnd('/') + path).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.connectTimeout = 5000
        connection.readTimeout = readTimeoutMillis
        connection.setRequestProperty("Accept", "application/json")
        if (body != null) {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
        }
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
        connection.disconnect()
        if (code !in 200..299) throw IllegalStateException(JSONObject(text.ifBlank { "{}" }).optString("detail", "连接失败（$code）"))
        JSONObject(text.ifBlank { "{}" })
    }

    suspend fun health(): Boolean = request("/api/v1/health").optString("status") == "ok"

    suspend fun dashboard(): Dashboard {
        val root = request("/api/v1/resident/dashboard")
        val safety = root.getJSONObject("safety")
        val sleep = root.getJSONObject("sleep")
        val summary = sleep.optJSONObject("summary")
        val analysis = sleep.optJSONObject("analysis")?.optJSONObject("content")
        val baseline = sleep.optJSONObject("baseline")
        val metrics = baseline?.optJSONObject("metrics")
        val sync = sleep.optJSONObject("sync")
        val nightAwakening = sleep.optJSONObject("night_awakening")
        return Dashboard(
            greeting = root.optString("greeting", "您好"), subtitle = root.optString("subtitle", "今天也安心生活"),
            safety = SafetyCard(safety.optString("status"), safety.optString("headline"), safety.optString("detail"), safety.optJSONObject("task")?.optString("id")),
            sleep = SleepCard(
                headline = sleep.optString("headline"),
                duration = summary?.optionalInt("duration_minutes"),
                respiratoryRate = summary?.optionalDouble("respiratory_rate"),
                heartRate = summary?.optionalDouble("heart_rate"),
                bedExitCount = summary?.optionalInt("bed_exit_count"),
                analysis = analysis?.optString("summary")?.takeIf { it.isNotBlank() },
                sleepStart = summary?.optionalString("sleep_start"),
                sleepEnd = summary?.optionalString("sleep_end"),
                sleepScore = summary?.optionalDouble("sleep_score"),
                awakeMinutes = summary?.optionalInt("awake_minutes"),
                lightSleepMinutes = summary?.optionalInt("light_sleep_minutes"),
                deepSleepMinutes = summary?.optionalInt("deep_sleep_minutes"),
                remSleepMinutes = summary?.optionalInt("rem_sleep_minutes"),
                baselineState = baseline?.optString("state", "no_data") ?: "no_data",
                baselineMessage = baseline?.optionalString("message"),
                baselineNights = baseline?.optInt("baseline_nights", 0) ?: 0,
                baselineMetrics = listOf("duration_minutes", "heart_rate", "respiratory_rate")
                    .mapNotNull { metrics?.optJSONObject(it)?.toBaselineMetric() },
                dataSource = sleep.optionalString("data_source"),
                syncStatus = sync?.optionalString("status"),
                syncMessage = sync?.optionalString("message"),
                nightAwakening = nightAwakening?.toNightAwakening() ?: NightAwakening(),
            ),
            contactName = root.getJSONObject("help").optString("contact_name", "家人"),
            contactPhone = root.getJSONObject("help").optString("contact_phone", "")
        )
    }

    suspend fun devices(): DeviceState {
        val root = request("/api/v1/devices")
        val camera = root.getJSONObject("c6c")
        val sleep = root.getJSONObject("sleep_assistant")
        return DeviceState(
            cameraConfigured = camera.optBoolean("configured"),
            cameraOnline = camera.takeIf { it.has("online") && !it.isNull("online") }
                ?.optBoolean("online"),
            sleepConfigured = sleep.optBoolean("configured"),
            sleepLastReportAt = sleep.optionalString("last_report_at"),
            sleepDemoActive = sleep.optBoolean("demo_active"),
        )
    }

    suspend fun cameraSdkSession(): CameraSdkSession {
        val root = request("/api/v1/devices/c6c/sdk-session", "POST")
        return CameraSdkSession(
            appKey = root.getString("app_key"),
            accessToken = root.getString("access_token"),
            deviceSerial = root.getString("device_serial"),
            channelNo = root.optInt("channel_no", 1),
            verifyCode = root.optString("verify_code"),
        )
    }

    suspend fun safetyBaseline(): SafetyBaselineStatus {
        val root = request("/api/v1/devices/c6c/safety/baseline")
        return SafetyBaselineStatus(
            ready = root.optBoolean("ready"),
            capturedAt = root.optionalString("captured_at"),
        )
    }

    suspend fun saveSafetyBaseline(): SafetyBaselineStatus {
        val root = request(
            "/api/v1/devices/c6c/safety/baseline",
            method = "POST",
            readTimeoutMillis = 30_000,
        )
        return SafetyBaselineStatus(
            ready = root.optBoolean("ready"),
            capturedAt = root.optionalString("captured_at"),
        )
    }

    suspend fun invalidateSafetyBaseline() {
        request("/api/v1/devices/c6c/safety/baseline/invalidate", method = "POST")
    }

    suspend fun analyzeSafety(): SafetyAnalysis {
        val root = request(
            "/api/v1/devices/c6c/safety/analyze",
            method = "POST",
            readTimeoutMillis = 120_000,
        )
        return root.toSafetyAnalysis()
    }

    suspend fun latestSafetyAnalysis(): SafetyAnalysis? {
        val root = request("/api/v1/devices/c6c/safety/latest")
        val analysis = root.optJSONObject("analysis") ?: return null
        return analysis.toSafetyAnalysis(flat = true)
    }

    private fun JSONObject.toSafetyAnalysis(flat: Boolean = false): SafetyAnalysis {
        val assessment = if (flat) this else getJSONObject("assessment")
        return SafetyAnalysis(
            riskLevel = assessment.getString("risk_level"),
            headline = assessment.getString("headline"),
            actionText = assessment.getString("action_text"),
            reason = getString("reason"),
            checkedAt = getString("checked_at"),
        )
    }

    suspend fun sendHelp(message: String) = request("/api/v1/resident/help", "POST", JSONObject().put("request_type", "contact").put("message", message))
    suspend fun taskAction(taskId: String, action: String) = request("/api/v1/resident/safety/tasks/$taskId/actions", "POST", JSONObject().put("action", action))
    suspend fun updatePause(camera: Boolean? = null, sleep: Boolean? = null) = request("/api/v1/resident/settings", "PUT", JSONObject().apply { camera?.let { put("camera_paused", it) }; sleep?.let { put("sleep_alerts_paused", it) } })
    suspend fun updateContact(name: String, phone: String) = request("/api/v1/resident/settings", "PUT", JSONObject().put("contact_name", name).put("contact_phone", phone))
    suspend fun sendFeedback(topic: String, message: String) = request("/api/v1/resident/feedback", "POST", JSONObject().put("topic", topic).put("message", message))
    suspend fun settings(): JSONObject = request("/api/v1/resident/settings")
    suspend fun syncSleep() = request(
        "/api/v1/devices/sleep/sync",
        method = "POST",
        readTimeoutMillis = 60_000,
    )
    suspend fun loadSleepDemo() = request("/api/v1/devices/sleep/demo", method = "POST")
    suspend fun clearSleepDemo() = request("/api/v1/devices/sleep/demo", method = "DELETE")
    suspend fun activateNightAwakeningDemo() = request(
        "/api/v1/devices/sleep/demo/night-awakening",
        method = "POST",
    )
    suspend fun resetNightAwakeningDemo() = request(
        "/api/v1/devices/sleep/demo/night-awakening",
        method = "DELETE",
    )

    suspend fun sendAssistantMessage(
        conversationId: String?,
        message: String,
    ): AssistantChatResult {
        val body = JSONObject().put("message", message)
        conversationId?.let { body.put("conversation_id", it) }
        val root = request("/api/v1/assistant/chat", "POST", body)
        return AssistantChatResult(
            conversationId = root.getString("conversation_id"),
            userMessage = root.getJSONObject("user_message").toAssistantMessage(),
            assistantMessage = root.getJSONObject("assistant_message").toAssistantMessage(),
        )
    }

    suspend fun assistantConversation(conversationId: String): List<AssistantMessage> {
        return request("/api/v1/assistant/conversations/$conversationId")
            .getJSONArray("messages").mapObjects { it.toAssistantMessage() }
    }

    suspend fun confirmAssistantAction(actionId: String): AssistantAction {
        return request("/api/v1/assistant/actions/$actionId/confirm", "POST")
            .toAssistantAction()
    }
}

private fun JSONObject.optionalDouble(key: String): Double? = if (has(key) && !isNull(key)) optDouble(key) else null
private fun JSONObject.optionalInt(key: String): Int? = if (has(key) && !isNull(key)) optInt(key) else null
private fun JSONObject.optionalString(key: String): String? =
    if (has(key) && !isNull(key)) optString(key).takeIf { it.isNotBlank() } else null

private fun JSONObject.toAssistantMessage() = AssistantMessage(
    id = getString("id"),
    role = getString("role"),
    content = getString("content"),
    sources = optJSONArray("sources")?.mapObjects {
        AssistantSource(it.optString("title", "查看来源"), it.getString("url"))
    }.orEmpty(),
    contextUsed = optJSONArray("context_used")?.mapStrings().orEmpty(),
    actions = optJSONArray("actions")?.mapObjects { it.toAssistantAction() }.orEmpty(),
)

private fun JSONObject.toBaselineMetric() = BaselineMetric(
    label = optString("label"),
    current = optionalDouble("current"),
    baselineMedian = optionalDouble("baseline_median"),
    difference = optionalDouble("difference"),
    status = optString("status", "insufficient"),
)

internal fun JSONObject.toNightAwakening() = NightAwakening(
    id = optionalString("id"),
    state = optString("state", "waiting"),
    attention = optionalString("attention"),
    detectedAt = optJSONObject("event")?.optionalString("detected_at"),
    eventInterfaceStatus = optionalString("event_interface_status"),
    snapshotStatus = optionalString("snapshot_status"),
    message = optString("message", "尚未监测到起夜"),
    reasons = optJSONArray("reasons")?.mapObjects {
        NightAwakeningReason(
            metric = it.optString("metric"),
            label = it.optString("label"),
            current = it.optionalDouble("current"),
            baselineMedian = it.optionalDouble("baseline_median"),
            difference = it.optionalDouble("difference"),
            direction = it.optionalString("direction"),
            comparisonStatus = it.optString("comparison_status", "insufficient"),
            adverseChange = it.optBoolean("adverse_change"),
        )
    }.orEmpty(),
    guidance = optJSONArray("guidance")?.mapStrings().orEmpty(),
    disclaimer = optString(
        "disclaimer",
        "这是根据睡眠变化给出的预防性提示，不代表已经预测到跌倒。",
    ),
)

private fun JSONObject.toAssistantAction() = AssistantAction(
    id = getString("id"),
    label = getString("label"),
    status = getString("status"),
)

private fun <T> JSONArray.mapObjects(transform: (JSONObject) -> T): List<T> =
    (0 until length()).map { transform(getJSONObject(it)) }

private fun JSONArray.mapStrings(): List<String> =
    (0 until length()).map { getString(it) }
