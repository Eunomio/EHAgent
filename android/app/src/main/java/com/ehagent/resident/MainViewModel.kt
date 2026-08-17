package com.ehagent.resident

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class UiState(
    val loading: Boolean = true,
    val dashboard: Dashboard = Dashboard(),
    val devices: DeviceState = DeviceState(),
    val error: String? = null,
    val notice: String? = null,
    val cameraPaused: Boolean = false,
    val sleepPaused: Boolean = false,
    val cameraStreamLoading: Boolean = false,
    val cameraSession: CameraSdkSession? = null,
    val cameraStreamError: String? = null,
    val assistantMessages: List<AssistantMessage> = emptyList(),
    val assistantLoading: Boolean = false,
    val assistantError: String? = null,
)

class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val preferences = application.getSharedPreferences("connection", 0)
    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()
    var backendUrl: String
        get() = preferences.getString("backend_url", "http://10.0.2.2:8000") ?: "http://10.0.2.2:8000"
        private set(value) { preferences.edit().putString("backend_url", value.trimEnd('/')).apply() }
    private var assistantConversationId: String?
        get() = preferences.getString("assistant_conversation_id", null)
        set(value) { preferences.edit().putString("assistant_conversation_id", value).apply() }

    init { refresh() }

    fun refresh() = viewModelScope.launch {
        _state.value = _state.value.copy(loading = true, error = null, notice = null)
        runCatching {
            val api = ProductApi(backendUrl)
            val dashboard = api.dashboard()
            val devices = api.devices()
            val settings = api.settings()
            _state.value = _state.value.copy(
                loading = false,
                dashboard = dashboard,
                devices = devices,
                cameraPaused = settings.optBoolean("camera_paused"),
                sleepPaused = settings.optBoolean("sleep_alerts_paused"),
                error = null,
            )
        }.onFailure { _state.value = _state.value.copy(loading = false, error = it.message ?: "暂时无法连接") }
    }

    fun saveBackend(url: String) = viewModelScope.launch {
        val clean = url.trim().trimEnd('/')
        if (!clean.startsWith("http://") && !clean.startsWith("https://")) {
            _state.value = _state.value.copy(error = "请填写以 http:// 或 https:// 开头的地址")
            return@launch
        }
        runCatching { ProductApi(clean).health() }.onSuccess {
            backendUrl = clean
            _state.value = _state.value.copy(notice = "连接成功", error = null)
            refresh()
        }.onFailure { _state.value = _state.value.copy(error = "连接失败，请检查电脑地址和网络") }
    }

    fun taskAction(action: String) = viewModelScope.launch {
        val id = _state.value.dashboard.safety.taskId ?: return@launch
        runCatching { ProductApi(backendUrl).taskAction(id, action) }
            .onSuccess { _state.value = _state.value.copy(notice = "已记录"); refresh() }
            .onFailure { _state.value = _state.value.copy(error = it.message) }
    }

    fun setCameraPaused(paused: Boolean) = viewModelScope.launch {
        runCatching { ProductApi(backendUrl).updatePause(camera = paused) }.onSuccess {
            _state.value = _state.value.copy(
                cameraPaused = paused,
                cameraStreamLoading = false,
                cameraSession = null,
                cameraStreamError = null,
            )
            refresh()
        }
    }

    fun startCameraStream() = viewModelScope.launch {
        if (_state.value.cameraPaused) {
            _state.value = _state.value.copy(cameraStreamError = "请先恢复通道检查")
            return@launch
        }
        _state.value = _state.value.copy(
            cameraStreamLoading = true,
            cameraSession = null,
            cameraStreamError = null,
        )
        runCatching { ProductApi(backendUrl).cameraSdkSession() }
            .onSuccess { session ->
                _state.value = _state.value.copy(
                    cameraStreamLoading = false,
                    cameraSession = session,
                )
            }
            .onFailure {
                _state.value = _state.value.copy(
                    cameraStreamLoading = false,
                    cameraStreamError = it.message ?: "暂时无法打开画面",
                )
            }
    }

    fun stopCameraStream() {
        _state.value = _state.value.copy(
            cameraStreamLoading = false,
            cameraSession = null,
            cameraStreamError = null,
        )
    }

    fun setSleepPaused(paused: Boolean) = viewModelScope.launch {
        runCatching { ProductApi(backendUrl).updatePause(sleep = paused) }.onSuccess { _state.value = _state.value.copy(sleepPaused = paused) }
    }

    fun saveContact(name: String, phone: String) = viewModelScope.launch {
        if (name.isBlank() || phone.isBlank()) {
            _state.value = _state.value.copy(error = "请填写家人称呼和电话号码")
            return@launch
        }
        runCatching { ProductApi(backendUrl).updateContact(name.trim(), phone.trim()) }
            .onSuccess { _state.value = _state.value.copy(notice = "家人联系方式已保存", error = null); refresh() }
            .onFailure { _state.value = _state.value.copy(error = it.message) }
    }

    fun sendFeedback(message: String, onSent: () -> Unit) = viewModelScope.launch {
        if (message.trim().length < 2) {
            _state.value = _state.value.copy(error = "请写下您的感受")
            return@launch
        }
        runCatching { ProductApi(backendUrl).sendFeedback("product", message.trim()) }
            .onSuccess {
                _state.value = _state.value.copy(notice = "谢谢，您的感受已保存", error = null)
                onSent()
            }
            .onFailure { _state.value = _state.value.copy(error = it.message) }
    }

    fun loadAssistantConversation() = viewModelScope.launch {
        val conversationId = assistantConversationId ?: return@launch
        if (_state.value.assistantMessages.isNotEmpty()) return@launch
        runCatching { ProductApi(backendUrl).assistantConversation(conversationId) }
            .onSuccess { messages ->
                _state.value = _state.value.copy(assistantMessages = messages, assistantError = null)
            }
            .onFailure {
                assistantConversationId = null
                _state.value = _state.value.copy(assistantMessages = emptyList())
            }
    }

    fun sendAssistantMessage(message: String) = viewModelScope.launch {
        val clean = message.trim()
        if (clean.isBlank() || _state.value.assistantLoading) return@launch
        val localMessage = AssistantMessage("local-${System.nanoTime()}", "user", clean)
        _state.value = _state.value.copy(
            assistantMessages = _state.value.assistantMessages + localMessage,
            assistantLoading = true,
            assistantError = null,
        )
        runCatching {
            ProductApi(backendUrl).sendAssistantMessage(assistantConversationId, clean)
        }.onSuccess { result ->
            assistantConversationId = result.conversationId
            _state.value = _state.value.copy(
                assistantMessages = _state.value.assistantMessages
                    .filterNot { it.id == localMessage.id } +
                    listOf(result.userMessage, result.assistantMessage),
                assistantLoading = false,
            )
        }.onFailure {
            _state.value = _state.value.copy(
                assistantMessages = _state.value.assistantMessages.filterNot {
                    messageItem -> messageItem.id == localMessage.id
                },
                assistantLoading = false,
                assistantError = "小安暂时没有回应，请检查家庭服务连接后再试。",
            )
        }
    }

    fun confirmAssistantAction(actionId: String) = viewModelScope.launch {
        runCatching { ProductApi(backendUrl).confirmAssistantAction(actionId) }
            .onSuccess { updated ->
                _state.value = _state.value.copy(
                    assistantMessages = _state.value.assistantMessages.map { message ->
                        message.copy(actions = message.actions.map { action ->
                            if (action.id == updated.id) updated else action
                        })
                    },
                    notice = "已请家人联系您",
                    assistantError = null,
                )
            }
            .onFailure {
                _state.value = _state.value.copy(
                    assistantError = "暂时没有发出请求，请稍后再试。"
                )
            }
    }
}
