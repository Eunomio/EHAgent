package com.ehagent.resident

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class SafetyCard(val status: String = "ready", val headline: String = "等待下一次检查", val detail: String = "", val taskId: String? = null)
data class SleepCard(val headline: String = "睡眠数据暂未同步", val duration: Int? = null, val respiratoryRate: Double? = null, val heartRate: Double? = null, val bedExitCount: Int? = null, val analysis: String? = null)
data class Dashboard(val greeting: String = "您好", val subtitle: String = "今天也安心生活", val safety: SafetyCard = SafetyCard(), val sleep: SleepCard = SleepCard(), val contactName: String = "家人", val contactPhone: String = "")
data class DeviceState(val cameraConfigured: Boolean = false, val cameraOnline: Boolean? = null, val sleepConfigured: Boolean = false)
data class CameraSdkSession(
    val appKey: String,
    val accessToken: String,
    val deviceSerial: String,
    val channelNo: Int,
    val verifyCode: String,
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
    private suspend fun request(path: String, method: String = "GET", body: JSONObject? = null): JSONObject = withContext(Dispatchers.IO) {
        val connection = URL(baseUrl.trimEnd('/') + path).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.connectTimeout = 5000
        connection.readTimeout = 8000
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
            sleep = SleepCard(sleep.optString("headline"), summary?.optInt("duration_minutes"), summary?.optionalDouble("respiratory_rate"), summary?.optionalDouble("heart_rate"), summary?.takeIf { it.has("bed_exit_count") && !it.isNull("bed_exit_count") }?.optInt("bed_exit_count"), analysis?.optString("summary")?.takeIf { it.isNotBlank() }),
            contactName = root.getJSONObject("help").optString("contact_name", "家人"),
            contactPhone = root.getJSONObject("help").optString("contact_phone", "")
        )
    }

    suspend fun devices(): DeviceState {
        val root = request("/api/v1/devices")
        val camera = root.getJSONObject("c6c")
        val sleep = root.getJSONObject("sleep_assistant")
        return DeviceState(camera.optBoolean("configured"), camera.takeIf { it.has("online") && !it.isNull("online") }?.optBoolean("online"), sleep.optBoolean("configured"))
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
