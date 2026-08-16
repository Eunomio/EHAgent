package com.ehagent.resident

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class SafetyCard(val status: String = "ready", val headline: String = "等待下一次检查", val detail: String = "", val taskId: String? = null)
data class SleepCard(val headline: String = "睡眠数据暂未同步", val duration: Int? = null, val respiratoryRate: Double? = null, val heartRate: Double? = null, val bedExitCount: Int? = null, val analysis: String? = null)
data class Dashboard(val greeting: String = "您好", val subtitle: String = "今天也安心生活", val safety: SafetyCard = SafetyCard(), val sleep: SleepCard = SleepCard(), val contactName: String = "家人", val contactPhone: String = "")
data class DeviceState(val cameraConfigured: Boolean = false, val cameraOnline: Boolean? = null, val sleepConfigured: Boolean = false)

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

    suspend fun sendHelp(message: String) = request("/api/v1/resident/help", "POST", JSONObject().put("request_type", "contact").put("message", message))
    suspend fun taskAction(taskId: String, action: String) = request("/api/v1/resident/safety/tasks/$taskId/actions", "POST", JSONObject().put("action", action))
    suspend fun updatePause(camera: Boolean? = null, sleep: Boolean? = null) = request("/api/v1/resident/settings", "PUT", JSONObject().apply { camera?.let { put("camera_paused", it) }; sleep?.let { put("sleep_alerts_paused", it) } })
    suspend fun updateContact(name: String, phone: String) = request("/api/v1/resident/settings", "PUT", JSONObject().put("contact_name", name).put("contact_phone", phone))
    suspend fun sendFeedback(topic: String, message: String) = request("/api/v1/resident/feedback", "POST", JSONObject().put("topic", topic).put("message", message))
    suspend fun settings(): JSONObject = request("/api/v1/resident/settings")
}

private fun JSONObject.optionalDouble(key: String): Double? = if (has(key) && !isNull(key)) optDouble(key) else null
