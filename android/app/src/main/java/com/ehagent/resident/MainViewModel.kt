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
)

class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val preferences = application.getSharedPreferences("connection", 0)
    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()
    var backendUrl: String
        get() = preferences.getString("backend_url", "http://10.0.2.2:8000") ?: "http://10.0.2.2:8000"
        private set(value) { preferences.edit().putString("backend_url", value.trimEnd('/')).apply() }

    init { refresh() }

    fun refresh() = viewModelScope.launch {
        _state.value = _state.value.copy(loading = true, error = null, notice = null)
        runCatching {
            val api = ProductApi(backendUrl)
            val dashboard = api.dashboard()
            val devices = api.devices()
            val settings = api.settings()
            _state.value = UiState(false, dashboard, devices, cameraPaused = settings.optBoolean("camera_paused"), sleepPaused = settings.optBoolean("sleep_alerts_paused"))
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
        runCatching { ProductApi(backendUrl).updatePause(camera = paused) }.onSuccess { _state.value = _state.value.copy(cameraPaused = paused); refresh() }
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
}
