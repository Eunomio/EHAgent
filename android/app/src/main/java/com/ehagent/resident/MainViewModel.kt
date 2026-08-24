package com.ehagent.resident

import android.app.Application
import android.os.SystemClock
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

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
    val safetyBaseline: SafetyBaselineStatus = SafetyBaselineStatus(),
    val safetyBaselineNeedsRefresh: Boolean = false,
    val baselineSaving: Boolean = false,
    val baselineError: String? = null,
    val safetyAnalysis: SafetyAnalysis? = null,
    val safetyAnalysisLoading: Boolean = false,
    val safetyAnalysisError: String? = null,
    val cameraMoveError: String? = null,
    val assistantMessages: List<AssistantMessage> = emptyList(),
    val assistantLoading: Boolean = false,
    val assistantError: String? = null,
    val sleepActionLoading: Boolean = false,
    val nightAwakeningExpanded: Boolean = false,
)

class MainViewModel(application: Application) : AndroidViewModel(application) {
    companion object {
        private const val BASELINE_MOVE_THRESHOLD_MS = 1_200L
    }

    private val preferences = application.getSharedPreferences("connection", 0)
    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()
    private val cameraMoveMutex = Mutex()
    private val safetyRefreshMutex = Mutex()
    private val cameraMoveStartedAt = mutableMapOf<CameraDirection, Long>()
    var backendUrl: String
        get() = preferences.getString("backend_url", "http://10.0.2.2:8000") ?: "http://10.0.2.2:8000"
        private set(value) { preferences.edit().putString("backend_url", value.trimEnd('/')).apply() }
    private var assistantConversationId: String?
        get() = preferences.getString("assistant_conversation_id", null)
        set(value) { preferences.edit().putString("assistant_conversation_id", value).apply() }

    private var nightAwakeningExpanded: Boolean
        get() = preferences.getBoolean("night_awakening_expanded", false)
        set(value) { preferences.edit().putBoolean("night_awakening_expanded", value).apply() }

    private var lastAutoExpandedAwakeningId: String?
        get() = preferences.getString("night_awakening_auto_expanded_id", null)
        set(value) { preferences.edit().putString("night_awakening_auto_expanded_id", value).apply() }

    private var savedBaselineNeedsRefresh: Boolean
        get() = preferences.getBoolean("safety_baseline_needs_refresh", false)
        set(value) { preferences.edit().putBoolean("safety_baseline_needs_refresh", value).apply() }

    private var cameraHorizontalOffsetMs: Long
        get() = preferences.getLong("camera_horizontal_offset_ms", 0L)
        set(value) { preferences.edit().putLong("camera_horizontal_offset_ms", value).apply() }

    private var cameraVerticalOffsetMs: Long
        get() = preferences.getLong("camera_vertical_offset_ms", 0L)
        set(value) { preferences.edit().putLong("camera_vertical_offset_ms", value).apply() }

    init { refresh() }

    fun refresh() = viewModelScope.launch {
        _state.value = _state.value.copy(loading = true, error = null, notice = null)
        runCatching {
            val api = ProductApi(backendUrl)
            val dashboard = api.dashboard()
            val devices = api.devices()
            val settings = api.settings()
            val safetyBaseline = runCatching { api.safetyBaseline() }
                .getOrDefault(_state.value.safetyBaseline)
            val latestSafetyAnalysis = runCatching { api.latestSafetyAnalysis() }
                .getOrDefault(_state.value.safetyAnalysis)
            if (safetyBaseline.ready && savedBaselineNeedsRefresh) {
                savedBaselineNeedsRefresh = false
                resetCameraMovementOffset()
            }
            val awakening = dashboard.sleep.nightAwakening
            val autoExpand = awakening.shouldAutoExpand(lastAutoExpandedAwakeningId)
            if (autoExpand) {
                lastAutoExpandedAwakeningId = awakening.id
                nightAwakeningExpanded = true
            }
            _state.value = _state.value.copy(
                loading = false,
                dashboard = dashboard,
                devices = devices,
                cameraPaused = settings.optBoolean("camera_paused"),
                sleepPaused = settings.optBoolean("sleep_alerts_paused"),
                safetyBaseline = safetyBaseline,
                baselineError = if (safetyBaseline.ready) null else _state.value.baselineError,
                safetyAnalysis = latestSafetyAnalysis,
                safetyBaselineNeedsRefresh = savedBaselineNeedsRefresh,
                nightAwakeningExpanded = if (autoExpand) true else nightAwakeningExpanded,
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

    fun refreshSafetyStatus() = viewModelScope.launch {
        if (_state.value.safetyAnalysisLoading || _state.value.baselineSaving) return@launch
        if (!safetyRefreshMutex.tryLock()) return@launch
        try {
            val api = ProductApi(backendUrl)
            // The latest result is the time-sensitive part. Refresh it independently so a
            // temporary failure in dashboard or baseline never hides an automatic check.
            runCatching { api.latestSafetyAnalysis() }.onSuccess { analysis ->
                _state.value = _state.value.copy(safetyAnalysis = analysis)
            }
            runCatching { api.dashboard() }.onSuccess { dashboard ->
                _state.value = _state.value.copy(dashboard = dashboard)
            }
            runCatching { api.safetyBaseline() }.onSuccess { baseline ->
                if (baseline.ready && savedBaselineNeedsRefresh) {
                    savedBaselineNeedsRefresh = false
                    resetCameraMovementOffset()
                }
                _state.value = _state.value.copy(
                    safetyBaseline = baseline,
                    safetyBaselineNeedsRefresh = savedBaselineNeedsRefresh,
                    baselineError = if (baseline.ready) null else _state.value.baselineError,
                )
            }
        } finally {
            safetyRefreshMutex.unlock()
        }
    }

    fun confirmSafetyCleaned() = viewModelScope.launch {
        val current = _state.value
        val id = current.dashboard.safety.taskId ?: return@launch
        when {
            current.cameraPaused -> {
                _state.value = current.copy(safetyAnalysisError = "请先恢复通道检查")
                return@launch
            }
            !current.safetyBaseline.ready -> {
                _state.value = current.copy(safetyAnalysisError = "正在识别通道，请稍后再试")
                return@launch
            }
            current.safetyBaselineNeedsRefresh -> {
                _state.value = current.copy(safetyAnalysisError = "摄像头角度变化较大，正在重新识别通道")
                return@launch
            }
        }
        _state.value = current.copy(
            safetyAnalysisLoading = true,
            safetyAnalysisError = null,
        )
        runCatching {
            val api = ProductApi(backendUrl)
            api.taskAction(id, "done")
            api.analyzeSafety()
        }.onSuccess { analysis ->
            _state.value = _state.value.copy(
                safetyAnalysis = analysis,
                safetyAnalysisLoading = false,
                notice = "通道复查已完成",
            )
            refresh()
        }.onFailure {
            _state.value = _state.value.copy(
                safetyAnalysisLoading = false,
                safetyAnalysisError = it.message ?: "复查没有完成，请稍后重试",
            )
        }
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

    fun saveSafetyBaseline(onSaved: () -> Unit = {}) = viewModelScope.launch {
        _state.value = _state.value.copy(baselineSaving = true, baselineError = null)
        runCatching { ProductApi(backendUrl).saveSafetyBaseline() }
            .onSuccess { baseline ->
                savedBaselineNeedsRefresh = false
                resetCameraMovementOffset()
                _state.value = _state.value.copy(
                    safetyBaseline = baseline,
                    safetyBaselineNeedsRefresh = false,
                    baselineSaving = false,
                    safetyAnalysis = null,
                    notice = "通道已重新识别",
                )
                onSaved()
            }
            .onFailure {
                _state.value = _state.value.copy(
                    baselineSaving = false,
                    baselineError = it.message ?: "暂时无法保存，请稍后重试",
                )
            }
    }

    fun analyzeSafety() = viewModelScope.launch {
        _state.value = _state.value.copy(
            safetyAnalysisLoading = true,
            safetyAnalysisError = null,
        )
        runCatching { ProductApi(backendUrl).analyzeSafety() }
            .onSuccess { analysis ->
                _state.value = _state.value.copy(
                    safetyAnalysis = analysis,
                    safetyAnalysisLoading = false,
                )
                refresh()
            }
            .onFailure {
                _state.value = _state.value.copy(
                    safetyAnalysisLoading = false,
                    safetyAnalysisError = it.message ?: "本次检查没有完成，请稍后重试",
                )
            }
    }

    fun setCameraMoving(direction: CameraDirection, moving: Boolean) = viewModelScope.launch {
        val session = _state.value.cameraSession ?: return@launch
        cameraMoveMutex.withLock {
            runCatching {
                withContext(Dispatchers.IO) {
                    EzvizSdk.controlPtz(getApplication(), session, direction, moving)
                }
            }.onSuccess {
                _state.value = _state.value.copy(cameraMoveError = null)
                recordCameraMovement(direction, moving)
            }.onFailure {
                _state.value = _state.value.copy(
                    cameraMoveError = "摄像头暂时无法移动，请稍后重试",
                )
            }
        }
    }

    private fun recordCameraMovement(direction: CameraDirection, moving: Boolean) {
        if (moving) {
            cameraMoveStartedAt[direction] = SystemClock.elapsedRealtime()
            return
        }
        val startedAt = cameraMoveStartedAt.remove(direction) ?: return
        val duration = (SystemClock.elapsedRealtime() - startedAt).coerceAtLeast(0L)
        when (direction) {
            CameraDirection.LEFT -> cameraHorizontalOffsetMs -= duration
            CameraDirection.RIGHT -> cameraHorizontalOffsetMs += duration
            CameraDirection.UP -> cameraVerticalOffsetMs -= duration
            CameraDirection.DOWN -> cameraVerticalOffsetMs += duration
        }
        val movementSquared =
            cameraHorizontalOffsetMs * cameraHorizontalOffsetMs +
                cameraVerticalOffsetMs * cameraVerticalOffsetMs
        val thresholdSquared = BASELINE_MOVE_THRESHOLD_MS * BASELINE_MOVE_THRESHOLD_MS
        if (
            movementSquared >= thresholdSquared &&
            _state.value.safetyBaseline.ready &&
            !_state.value.safetyBaselineNeedsRefresh
        ) {
            savedBaselineNeedsRefresh = true
            _state.value = _state.value.copy(safetyBaselineNeedsRefresh = true)
            viewModelScope.launch {
                runCatching { ProductApi(backendUrl).invalidateSafetyBaseline() }
            }
        }
    }

    private fun resetCameraMovementOffset() {
        cameraMoveStartedAt.clear()
        cameraHorizontalOffsetMs = 0L
        cameraVerticalOffsetMs = 0L
    }

    fun setSleepPaused(paused: Boolean) = viewModelScope.launch {
        runCatching { ProductApi(backendUrl).updatePause(sleep = paused) }.onSuccess { _state.value = _state.value.copy(sleepPaused = paused) }
    }

    fun syncSleep() = viewModelScope.launch {
        if (_state.value.sleepActionLoading) return@launch
        _state.value = _state.value.copy(sleepActionLoading = true, error = null)
        runCatching { ProductApi(backendUrl).syncSleep() }
            .onSuccess {
                _state.value = _state.value.copy(
                    sleepActionLoading = false,
                    notice = "昨晚睡眠数据已同步",
                )
                refresh()
            }
            .onFailure {
                _state.value = _state.value.copy(
                    sleepActionLoading = false,
                    error = it.message ?: "睡眠同步失败",
                )
            }
    }

    fun loadSleepDemo() = viewModelScope.launch {
        if (_state.value.sleepActionLoading) return@launch
        _state.value = _state.value.copy(sleepActionLoading = true, error = null)
        runCatching { ProductApi(backendUrl).loadSleepDemo() }
            .onSuccess {
                _state.value = _state.value.copy(
                    sleepActionLoading = false,
                    notice = "8晚演示睡眠数据已导入",
                )
                refresh()
            }
            .onFailure {
                _state.value = _state.value.copy(sleepActionLoading = false, error = it.message)
            }
    }

    fun clearSleepDemo() = viewModelScope.launch {
        if (_state.value.sleepActionLoading) return@launch
        _state.value = _state.value.copy(sleepActionLoading = true, error = null)
        runCatching { ProductApi(backendUrl).clearSleepDemo() }
            .onSuccess {
                nightAwakeningExpanded = false
                _state.value = _state.value.copy(
                    sleepActionLoading = false,
                    nightAwakeningExpanded = false,
                    notice = "演示睡眠数据已清除",
                )
                refresh()
            }
            .onFailure {
                _state.value = _state.value.copy(sleepActionLoading = false, error = it.message)
            }
    }

    fun toggleNightAwakeningExpanded() {
        val expanded = !_state.value.nightAwakeningExpanded
        nightAwakeningExpanded = expanded
        _state.value = _state.value.copy(nightAwakeningExpanded = expanded)
    }

    fun activateNightAwakeningDemo() = viewModelScope.launch {
        if (_state.value.sleepActionLoading) return@launch
        _state.value = _state.value.copy(sleepActionLoading = true, error = null)
        runCatching { ProductApi(backendUrl).activateNightAwakeningDemo() }
            .onSuccess {
                _state.value = _state.value.copy(
                    sleepActionLoading = false,
                    notice = "演示起夜关注已激活",
                )
                refresh()
            }
            .onFailure {
                _state.value = _state.value.copy(
                    sleepActionLoading = false,
                    error = it.message ?: "演示起夜关注激活失败",
                )
            }
    }

    fun resetNightAwakeningDemo() = viewModelScope.launch {
        if (_state.value.sleepActionLoading) return@launch
        _state.value = _state.value.copy(sleepActionLoading = true, error = null)
        runCatching { ProductApi(backendUrl).resetNightAwakeningDemo() }
            .onSuccess {
                nightAwakeningExpanded = false
                _state.value = _state.value.copy(
                    sleepActionLoading = false,
                    nightAwakeningExpanded = false,
                    notice = "演示起夜关注已重置",
                )
                refresh()
            }
            .onFailure {
                _state.value = _state.value.copy(
                    sleepActionLoading = false,
                    error = it.message ?: "演示起夜关注重置失败",
                )
            }
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
