package com.ehagent.resident

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class SafetyCard(val status: String = "ready", val headline: String = "等待下一次检查", val detail: String = "", val taskId: String? = null)
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
)
data class Dashboard(val greeting: String = "您好", val subtitle: String = "今天也安心生活", val safety: SafetyCard = SafetyCard(), val sleep: SleepCard = SleepCard(), val contactName: String = "家人", val contactPhone: String = "")
data class DeviceState(
    val cameraConfigured: Boolean = false,
    val cameraOnline: Boolean? = null,
    val sleepConfigured: Boolean = false,
    val sleepLastReportAt: String? = null,
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
    val checkId: String? = null,
    val hazardRegions: List<HazardRegion> = emptyList(),
    val notificationRequired: Boolean = false,
    val speechAutoPlay: Boolean = false,
    val speechUrl: String? = null,
)
data class HazardRegion(
    val label: String,
    val riskLevel: String,
    val x1: Float,
    val y1: Float,
    val x2: Float,
    val y2: Float,
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
        val regions = optJSONArray("hazard_regions")?.mapObjects { region ->
            HazardRegion(
                label = region.optString("label", "风险位置"),
                riskLevel = region.optString("risk_level", assessment.optString("risk_level")),
                x1 = region.optDouble("x1", 0.0).toFloat().coerceIn(0f, 1000f),
                y1 = region.optDouble("y1", 0.0).toFloat().coerceIn(0f, 1000f),
                x2 = region.optDouble("x2", 0.0).toFloat().coerceIn(0f, 1000f),
                y2 = region.optDouble("y2", 0.0).toFloat().coerceIn(0f, 1000f),
            )
        }?.filter { it.x2 - it.x1 >= 10f && it.y2 - it.y1 >= 10f }.orEmpty()
        return SafetyAnalysis(
            riskLevel = assessment.getString("risk_level"),
            headline = assessment.getString("headline"),
            actionText = assessment.getString("action_text"),
            reason = getString("reason"),
            checkedAt = getString("checked_at"),
            checkId = optionalString("check_id"),
            hazardRegions = regions,
            notificationRequired = optBoolean("notification_required"),
            speechAutoPlay = optBoolean("speech_auto_play"),
            speechUrl = optionalString("speech_url"),
        )
    }

    suspend fun safetySpeech(path: String): ByteArray = withContext(Dispatchers.IO) {
        val url = if (path.startsWith("http://") || path.startsWith("https://")) {
            path
        } else {
            baseUrl.trimEnd('/') + "/" + path.trimStart('/')
        }
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.requestMethod = "GET"
        connection.connectTimeout = 5_000
        connection.readTimeout = 60_000
        connection.setRequestProperty("Accept", "audio/mpeg")
        val code = connection.responseCode
        if (code !in 200..299) {
            connection.disconnect()
            throw IllegalStateException("语音提醒暂时不可用")
        }
        val audio = connection.inputStream.use { it.readBytes() }
        connection.disconnect()
        if (audio.size < 128) throw IllegalStateException("语音提醒内容无效")
        audio
    }

    suspend fun sendHelp(message: String) = request("/api/v1/resident/help", "POST", JSONObject().put("request_type", "contact").put("message", message))
    suspend fun taskAction(taskId: String, action: String) = request("/api/v1/resident/safety/tasks/$taskId/actions", "POST", JSONObject().put("action", action))
    suspend fun updatePause(camera: Boolean? = null, sleep: Boolean? = null) = request("/api/v1/resident/settings", "PUT", JSONObject().apply { camera?.let { put("camera_paused", it) }; sleep?.let { put("sleep_alerts_paused", it) } })
    suspend fun updateContact(name: String, phone: String) = request("/api/v1/resident/settings", "PUT", JSONObject().put("contact_name", name).put("contact_phone", phone))
    suspend fun sendFeedback(topic: String, message: String) = request("/api/v1/resident/feedback", "POST", JSONObject().put("topic", topic).put("message", message))
    suspend fun settings(): JSONObject = request("/api/v1/resident/settings")

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

private fun JSONObject.toAssistantAction() = AssistantAction(
    id = getString("id"),
    label = getString("label"),
    status = getString("status"),
)

private fun <T> JSONArray.mapObjects(transform: (JSONObject) -> T): List<T> =
    (0 until length()).map { transform(getJSONObject(it)) }

private fun JSONArray.mapStrings(): List<String> =
    (0 until length()).map { getString(it) }
