package com.ehagent.resident

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.os.Build
import android.os.SystemClock
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.time.Duration
import java.time.OffsetDateTime
import java.io.File

data class UiState(
    val loading: Boolean = true,
    val dashboard: Dashboard = Dashboard(),
    val devices: DeviceState = DeviceState(),
    val error: String? = null,
    val notice: String? = null,
    val cameraPaused: Boolean = false,
    val sleepPaused: Boolean = false,
    val proactiveCarePaused: Boolean = false,
    val psychologicalCareEnabled: Boolean = true,
    val assistantDeviceControlConsent: String = "unset",
    val evidenceRetentionDays: Int = 7,
    val profileFacts: List<ProfileFact> = emptyList(),
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
    val voiceRecording: Boolean = false,
    val voiceTranscribing: Boolean = false,
    val voiceError: String? = null,
    val sleepActionLoading: Boolean = false,
    val sleepHistory: List<SleepHistoryNight> = emptyList(),
    val nightAwakeningExpanded: Boolean = false,
    val whiteNoisePlaying: Boolean = false,
    val whiteNoisePaused: Boolean = false,
    val whiteNoiseLoading: Boolean = false,
    val whiteNoiseElapsedSeconds: Int = 0,
    val whiteNoiseRemainingSeconds: Int = 0,
    val whiteNoiseTrackId: String? = null,
    val whiteNoiseTrackName: String? = null,
    val whiteNoiseCanSwitch: Boolean = false,
    val whiteNoiseVolume: Float = 0.35f,
    val whiteNoiseError: String? = null,
)

class MainViewModel(application: Application) : AndroidViewModel(application) {
    companion object {
        private const val BASELINE_MOVE_THRESHOLD_MS = 1_200L
        private const val SAFETY_CHANNEL_ID = "walkway_safety_alerts"
        private const val SAFETY_NOTIFICATION_ID = 4102
        private const val SAFETY_SPEECH_RETRY_MS = 60_000L
        private const val VOICE_RECORDING_LIMIT_MS = 30_000L
    }

    private val preferences = application.getSharedPreferences("connection", 0)
    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()
    private val cameraMoveMutex = Mutex()
    private val safetyRefreshMutex = Mutex()
    private val cameraMoveStartedAt = mutableMapOf<CameraDirection, Long>()
    private var safetyPlayer: MediaPlayer? = null
    private val whiteNoisePlayer = WhiteNoisePlayer()
    private var whiteNoiseTimer: Job? = null
    private var whiteNoisePlaylist: List<WhiteNoiseTrack> = emptyList()
    private var whiteNoiseTrackIndex: Int = -1
    private var safetySpeechInFlightCheckId: String? = null
    private var safetySpeechLastAttemptCheckId: String? = null
    private var safetySpeechLastAttemptAtMs: Long = 0L
    private var voiceRecorder: MediaRecorder? = null
    private var voiceRecordingFile: File? = null
    private var voiceRecordingTimeout: Job? = null
    private var voiceTextConsumer: ((String) -> Unit)? = null
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

    private var sleepDemoSeedAttempted: Boolean
        get() = preferences.getBoolean("sleep_return_care_seed_v1", false)
        set(value) { preferences.edit().putBoolean("sleep_return_care_seed_v1", value).apply() }

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
            var dashboard = api.dashboard()
            var devices = api.devices()
            val settings = api.settings()
            val profileFacts = runCatching { api.profileFacts() }.getOrDefault(emptyList())
            val needsCurrentReviewData = BuildConfig.DEMO_MODE &&
                devices.sleepDemoDatasetId != "sleep-return-care-20260904-v1" &&
                !sleepDemoSeedAttempted
            if (
                BuildConfig.DEMO_MODE &&
                (shouldAutoLoadSleepDemo(dashboard.sleep.duration, sleepDemoSeedAttempted) || needsCurrentReviewData)
            ) {
                sleepDemoSeedAttempted = true
                runCatching { api.loadSleepDemo() }.onSuccess {
                    dashboard = api.dashboard()
                    devices = api.devices()
                }
            } else if (!sleepDemoSeedAttempted) {
                sleepDemoSeedAttempted = true
            }
            val sleepHistory = runCatching { api.sleepHistory() }.getOrDefault(emptyList())
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
                proactiveCarePaused = settings.optBoolean("proactive_care_paused"),
                psychologicalCareEnabled = settings.optBoolean("psychological_care_enabled", true),
                assistantDeviceControlConsent = settings.optString(
                    "assistant_device_control_consent", "unset",
                ),
                evidenceRetentionDays = settings.optInt("evidence_retention_days", 7),
                profileFacts = profileFacts,
                safetyBaseline = safetyBaseline,
                baselineError = if (safetyBaseline.ready) null else _state.value.baselineError,
                safetyAnalysis = latestSafetyAnalysis,
                safetyBaselineNeedsRefresh = savedBaselineNeedsRefresh,
                nightAwakeningExpanded = if (autoExpand) true else nightAwakeningExpanded,
                sleepHistory = sleepHistory,
                error = null,
            )
            latestSafetyAnalysis?.let(::handleSafetyAlert)
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
            .onSuccess {
                _state.value = _state.value.copy(
                    notice = if (action == "later") "将在30分钟后再次提醒" else "已记录",
                )
                refresh()
            }
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
                analysis?.let(::handleSafetyAlert)
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

    fun analyzeSafetyFrame(
        image: ByteArray,
        preview: Boolean = false,
        baselineImage: ByteArray? = null,
        onSuccess: (SafetyAnalysis) -> Unit,
        onFailure: (String) -> Unit,
    ) = viewModelScope.launch {
        _state.value = _state.value.copy(
            safetyAnalysisLoading = true,
            safetyAnalysisError = null,
        )
        runCatching { ProductApi(backendUrl).analyzeSafetyFrame(image, preview, baselineImage) }
            .onSuccess { analysis ->
                _state.value = _state.value.copy(
                    safetyAnalysis = analysis,
                    safetyAnalysisLoading = false,
                )
                handleSafetyAlert(analysis)
                onSuccess(analysis)
                refresh()
            }
            .onFailure {
                val message = it.message ?: "本次检查没有完成，请稍后重试"
                _state.value = _state.value.copy(
                    safetyAnalysisLoading = false,
                    safetyAnalysisError = message,
                )
                onFailure(message)
            }
    }

    fun prepareSafetyRecheck(
        taskId: String?,
        onReady: () -> Unit,
        onFailure: (String) -> Unit,
    ) = viewModelScope.launch {
        if (taskId == null) {
            onReady()
            return@launch
        }
        runCatching { ProductApi(backendUrl).taskAction(taskId, "done") }
            .onSuccess {
                onReady()
                refresh()
            }
            .onFailure { onFailure(it.message ?: "暂时无法重新检查，请稍后再试") }
    }

    fun replaySafetySpeech() {
        val analysis = _state.value.safetyAnalysis ?: return
        val speechUrl = analysis.speechUrl ?: return
        viewModelScope.launch { playSafetySpeech(analysis, speechUrl, reportFailure = true) }
    }

    private fun handleSafetyAlert(analysis: SafetyAnalysis) {
        val checkId = analysis.checkId ?: return
        if (
            analysis.riskLevel !in setOf("medium", "high") ||
            (!isRecentSafetyResult(analysis.checkedAt) && _state.value.dashboard.safety.taskId == null)
        ) return

        if (
            analysis.notificationRequired &&
            preferences.getString("last_safety_alert_check", null) != checkId
        ) {
            preferences.edit().putString("last_safety_alert_check", checkId).apply()
            showSafetyNotification(analysis)
        }
        val speechUrl = analysis.speechUrl
        val now = SystemClock.elapsedRealtime()
        val speechRetryReady = safetySpeechLastAttemptCheckId != checkId ||
            now - safetySpeechLastAttemptAtMs >= SAFETY_SPEECH_RETRY_MS
        if (
            analysis.speechAutoPlay &&
            speechUrl != null &&
            preferences.getString("last_safety_speech_check", null) != checkId &&
            safetySpeechInFlightCheckId != checkId &&
            speechRetryReady
        ) {
            safetySpeechInFlightCheckId = checkId
            safetySpeechLastAttemptCheckId = checkId
            safetySpeechLastAttemptAtMs = now
            viewModelScope.launch {
                val played = playSafetySpeech(analysis, speechUrl, reportFailure = false)
                if (played) {
                    preferences.edit().putString("last_safety_speech_check", checkId).apply()
                }
                if (safetySpeechInFlightCheckId == checkId) safetySpeechInFlightCheckId = null
            }
        }
    }

    private fun isRecentSafetyResult(value: String): Boolean = runCatching {
        val age = Duration.between(OffsetDateTime.parse(value), OffsetDateTime.now()).toMinutes()
        age in 0..15
    }.getOrDefault(false)

    private fun showSafetyNotification(analysis: SafetyAnalysis) {
        val application = getApplication<Application>()
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(application, android.Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) return
        val manager = application.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(
                SAFETY_CHANNEL_ID,
                "通道安全提醒",
                NotificationManager.IMPORTANCE_HIGH,
            ).apply { description = "发现通道需要整理时提醒" },
        )
        val intent = Intent(application, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            application,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(application, SAFETY_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setColor(0xFFC73A31.toInt())
            .setContentTitle(analysis.headline)
            .setContentText(analysis.actionText)
            .setStyle(NotificationCompat.BigTextStyle().bigText("${analysis.reason}\n${analysis.actionText}"))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .build()
        manager.notify(SAFETY_NOTIFICATION_ID, notification)
    }

    private suspend fun playSafetySpeech(
        analysis: SafetyAnalysis,
        speechUrl: String,
        reportFailure: Boolean,
    ): Boolean = runCatching {
            val audio = ProductApi(backendUrl).safetySpeech(speechUrl)
            val safeId = analysis.checkId.orEmpty().filter { it.isLetterOrDigit() || it == '-' }
            val file = getApplication<Application>().cacheDir.resolve("safety-$safeId.mp3")
            withContext(Dispatchers.IO) {
                file.writeBytes(audio)
                MediaPlayer().apply {
                    setAudioAttributes(
                        AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_ASSISTANCE_ACCESSIBILITY)
                            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                            .build(),
                    )
                    setDataSource(file.absolutePath)
                    prepare()
                }
            }
        }.fold(onSuccess = { player ->
            safetyPlayer?.release()
            safetyPlayer = player
            player.setOnCompletionListener {
                it.release()
                if (safetyPlayer === it) safetyPlayer = null
            }
            player.setOnErrorListener { mediaPlayer, _, _ ->
                mediaPlayer.release()
                if (safetyPlayer === mediaPlayer) safetyPlayer = null
                true
            }
            player.start()
            if (reportFailure) {
                _state.value = _state.value.copy(notice = "正在播报通道提醒")
            }
            true
        }, onFailure = {
            if (reportFailure) {
                _state.value = _state.value.copy(
                    safetyAnalysisError = "语音提醒暂时无法播放，请查看文字建议",
                )
            }
            false
        })

    override fun onCleared() {
        safetyPlayer?.release()
        safetyPlayer = null
        whiteNoiseTimer?.cancel()
        whiteNoisePlayer.stop()
        voiceRecordingTimeout?.cancel()
        runCatching { voiceRecorder?.stop() }
        voiceRecorder?.release()
        voiceRecorder = null
        voiceRecordingFile?.delete()
        super.onCleared()
    }

    fun toggleVoiceInput(onText: (String) -> Unit) {
        if (_state.value.voiceTranscribing) return
        if (_state.value.voiceRecording) {
            finishVoiceRecording()
        } else {
            startVoiceRecording(onText)
        }
    }

    @Suppress("DEPRECATION")
    private fun startVoiceRecording(onText: (String) -> Unit) {
        val application = getApplication<Application>()
        val output = File(application.cacheDir, "voice-${System.nanoTime()}.m4a")
        val recorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            MediaRecorder(application)
        } else {
            MediaRecorder()
        }
        runCatching {
            recorder.setAudioSource(MediaRecorder.AudioSource.VOICE_RECOGNITION)
            recorder.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            recorder.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            recorder.setAudioChannels(1)
            recorder.setAudioSamplingRate(16_000)
            recorder.setAudioEncodingBitRate(64_000)
            recorder.setOutputFile(output.absolutePath)
            recorder.prepare()
            recorder.start()
        }.onSuccess {
            voiceRecorder = recorder
            voiceRecordingFile = output
            voiceTextConsumer = onText
            _state.value = _state.value.copy(
                voiceRecording = true,
                voiceTranscribing = false,
                voiceError = null,
            )
            voiceRecordingTimeout?.cancel()
            voiceRecordingTimeout = viewModelScope.launch {
                delay(VOICE_RECORDING_LIMIT_MS)
                finishVoiceRecording()
            }
        }.onFailure {
            recorder.release()
            output.delete()
            _state.value = _state.value.copy(
                voiceRecording = false,
                voiceTranscribing = false,
                voiceError = "暂时无法开始录音，请检查麦克风权限",
            )
        }
    }

    private fun finishVoiceRecording() {
        val recorder = voiceRecorder ?: return
        val output = voiceRecordingFile
        voiceRecorder = null
        voiceRecordingFile = null
        voiceRecordingTimeout?.cancel()
        voiceRecordingTimeout = null
        val stopped = runCatching { recorder.stop() }.isSuccess
        recorder.release()
        if (!stopped || output == null || !output.exists()) {
            output?.delete()
            _state.value = _state.value.copy(
                voiceRecording = false,
                voiceTranscribing = false,
                voiceError = "录音时间太短，请重新说一次",
            )
            return
        }

        _state.value = _state.value.copy(
            voiceRecording = false,
            voiceTranscribing = true,
            voiceError = null,
        )
        viewModelScope.launch {
            runCatching {
                ProductApi(backendUrl).transcribeVoice(
                    withContext(Dispatchers.IO) { output.readBytes() },
                )
            }.onSuccess { text ->
                voiceTextConsumer?.invoke(text)
                _state.value = _state.value.copy(
                    voiceTranscribing = false,
                    voiceError = null,
                )
            }.onFailure { error ->
                _state.value = _state.value.copy(
                    voiceTranscribing = false,
                    voiceError = error.message ?: "语音暂时没有识别出来，请稍后再试",
                )
            }
            withContext(Dispatchers.IO) { output.delete() }
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
            _state.value = _state.value.copy(
                safetyAnalysis = _state.value.safetyAnalysis?.copy(hazardRegions = emptyList()),
            )
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

    fun setProactiveCarePaused(paused: Boolean) = viewModelScope.launch {
        runCatching { ProductApi(backendUrl).updatePause(proactive = paused) }
            .onSuccess {
                _state.value = _state.value.copy(
                    proactiveCarePaused = paused,
                    notice = if (paused) "主动关怀已暂停" else "主动关怀已恢复",
                )
                refresh()
            }
            .onFailure { _state.value = _state.value.copy(error = it.message) }
    }

    fun setDeviceControlConsent(consent: String) = viewModelScope.launch {
        runCatching { ProductApi(backendUrl).updatePrivacy(deviceControlConsent = consent) }
            .onSuccess {
                _state.value = _state.value.copy(
                    assistantDeviceControlConsent = consent,
                    notice = if (consent == "allowed") "小安已获得设备控制权限" else "小安不会控制设备",
                    error = null,
                )
            }
            .onFailure { _state.value = _state.value.copy(error = it.message) }
    }

    fun setPsychologicalCareEnabled(enabled: Boolean) = viewModelScope.launch {
        runCatching { ProductApi(backendUrl).updatePrivacy(psychologicalCare = enabled) }
            .onSuccess { _state.value = _state.value.copy(psychologicalCareEnabled = enabled) }
            .onFailure { _state.value = _state.value.copy(error = it.message) }
    }

    fun setEvidenceRetentionDays(days: Int) = viewModelScope.launch {
        runCatching { ProductApi(backendUrl).updatePrivacy(retentionDays = days) }
            .onSuccess {
                _state.value = _state.value.copy(
                    evidenceRetentionDays = days,
                    notice = "风险证据保存时间已改为${days}天",
                    error = null,
                )
            }
            .onFailure { _state.value = _state.value.copy(error = it.message) }
    }

    fun startProactiveEvent(eventId: String) = viewModelScope.launch {
        if (_state.value.assistantLoading) return@launch
        _state.value = _state.value.copy(assistantLoading = true, assistantError = null)
        runCatching { ProductApi(backendUrl).startProactiveEvent(eventId) }
            .onSuccess { result ->
                assistantConversationId = result.conversationId
                _state.value = _state.value.copy(
                    assistantMessages = listOf(result.assistantMessage),
                    assistantLoading = false,
                )
                refreshSafetyStatus()
            }
            .onFailure {
                _state.value = _state.value.copy(
                    assistantLoading = false,
                    assistantError = "这条关怀暂时无法打开，请稍后再试。",
                )
            }
    }

    fun deleteProfileFact(factId: String) = viewModelScope.launch {
        runCatching { ProductApi(backendUrl).deleteProfileFact(factId) }
            .onSuccess {
                _state.value = _state.value.copy(
                    profileFacts = _state.value.profileFacts.filterNot { it.id == factId },
                    notice = "这条个人情况已删除",
                )
            }
            .onFailure { _state.value = _state.value.copy(error = it.message) }
    }

    fun startProfileOnboarding() = viewModelScope.launch {
        if (_state.value.assistantLoading) return@launch
        _state.value = _state.value.copy(assistantLoading = true, assistantError = null)
        runCatching { ProductApi(backendUrl).startProfileOnboarding() }
            .onSuccess { result ->
                assistantConversationId = result.conversationId
                _state.value = _state.value.copy(
                    assistantMessages = listOf(result.assistantMessage),
                    assistantLoading = false,
                )
            }
            .onFailure {
                _state.value = _state.value.copy(
                    assistantLoading = false,
                    assistantError = "画像引导暂时无法打开，请稍后再试。",
                )
            }
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
                sleepDemoSeedAttempted = true
                _state.value = _state.value.copy(
                    sleepActionLoading = false,
                    notice = "健康基线和变化组睡眠数据已导入",
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
                    notice = "近期睡眠记录已清除",
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
                    notice = "起夜关注已开启",
                )
                refresh()
            }
            .onFailure {
                _state.value = _state.value.copy(
                    sleepActionLoading = false,
                    error = it.message ?: "起夜关注开启失败",
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
                    notice = "起夜关注已重置",
                )
                refresh()
            }
            .onFailure {
                _state.value = _state.value.copy(
                    sleepActionLoading = false,
                    error = it.message ?: "起夜关注重置失败",
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
            refreshSafetyStatus()
            refreshPrivacyAndDeviceSettings()
            result.assistantMessage.actions.firstOrNull {
                it.autoStart && it.status == "pending" &&
                    it.kind == "start_intervention" && it.interventionId == "white_noise_30min"
            }?.let { confirmAssistantAction(it.id) }
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

    private val confirmingAssistantActions = mutableSetOf<String>()

    fun confirmAssistantAction(actionId: String) = viewModelScope.launch {
        if (!confirmingAssistantActions.add(actionId)) return@launch
        val selectedAction = _state.value.assistantMessages
            .asSequence()
            .flatMap { it.actions.asSequence() }
            .firstOrNull { it.id == actionId }
        runCatching { ProductApi(backendUrl).confirmAssistantAction(actionId) }
            .onSuccess { updated ->
                val isWhiteNoise = updated.kind == "start_intervention" &&
                    (updated.interventionId ?: selectedAction?.interventionId) == "white_noise_30min"
                val notice = when (updated.kind) {
                    "contact_family" -> "已请家人联系您"
                    "remember_profile_fact" -> "小安已经按您的同意记下"
                    "reject_profile_fact" -> "好的，小安不会记下这件事"
                    "start_intervention" -> if (
                        isWhiteNoise
                    ) "正在为您选择白噪音" else "支持内容已经开始"
                    "defer_event" -> "将在30分钟后再提醒"
                    "pause_proactive_care" -> "主动关怀已暂停"
                    "device_control_allow" -> "已允许小安控制已连接设备"
                    "device_control_deny" -> "小安不会控制设备"
                    "profile_onboarding_choice" -> "已加入我的画像"
                    "profile_onboarding_skip" -> "已跳过这一项"
                    else -> "已记录"
                }
                _state.value = _state.value.copy(
                    assistantMessages = _state.value.assistantMessages.map { message ->
                        message.copy(actions = message.actions.mapNotNull { action ->
                            when {
                                action.id == updated.id -> updated
                                updated.kind in setOf("device_control_allow", "device_control_deny") &&
                                    action.kind in setOf("device_control_allow", "device_control_deny") -> null
                                updated.kind in setOf("profile_onboarding_choice", "profile_onboarding_skip") &&
                                    action.kind in setOf("profile_onboarding_choice", "profile_onboarding_skip") -> null
                                else -> action
                            }
                        })
                    } + listOfNotNull(updated.followUpMessage),
                    notice = notice,
                    assistantError = null,
                    assistantDeviceControlConsent = when (updated.kind) {
                        "device_control_allow" -> "allowed"
                        "device_control_deny" -> "denied"
                        else -> _state.value.assistantDeviceControlConsent
                    },
                )
                if (updated.kind in setOf("remember_profile_fact", "reject_profile_fact")) {
                    viewModelScope.launch {
                        runCatching { ProductApi(backendUrl).profileFacts() }.onSuccess { facts ->
                            _state.value = _state.value.copy(profileFacts = facts)
                        }
                    }
                }
                if (updated.kind == "profile_onboarding_choice") {
                    runCatching { ProductApi(backendUrl).profileFacts() }.onSuccess { facts ->
                        _state.value = _state.value.copy(profileFacts = facts)
                    }
                }
                if (updated.kind in setOf("device_control_allow", "device_control_deny")) {
                    refreshPrivacyAndDeviceSettings()
                }
                if (isWhiteNoise) startWhiteNoise()
            }
            .onFailure {
                _state.value = _state.value.copy(
                    assistantError = "暂时没有发出请求，请稍后再试。"
                )
            }
        confirmingAssistantActions.remove(actionId)
    }

    fun stopWhiteNoise() {
        whiteNoiseTimer?.cancel()
        whiteNoiseTimer = null
        whiteNoisePlayer.stop()
        whiteNoisePlaylist = emptyList()
        whiteNoiseTrackIndex = -1
        _state.value = _state.value.copy(
            whiteNoisePlaying = false,
            whiteNoisePaused = false,
            whiteNoiseLoading = false,
            whiteNoiseElapsedSeconds = 0,
            whiteNoiseRemainingSeconds = 0,
            whiteNoiseTrackId = null,
            whiteNoiseTrackName = null,
            whiteNoiseCanSwitch = false,
            whiteNoiseError = null,
            notice = "白噪音已停止",
        )
    }

    fun toggleWhiteNoisePlayback() {
        when {
            _state.value.whiteNoisePlaying -> {
                whiteNoisePlayer.pause()
                _state.value = _state.value.copy(
                    whiteNoisePlaying = false,
                    whiteNoisePaused = true,
                    notice = "白噪音已暂停",
                )
            }
            _state.value.whiteNoisePaused -> {
                whiteNoisePlayer.resume()
                _state.value = _state.value.copy(
                    whiteNoisePlaying = true,
                    whiteNoisePaused = false,
                    notice = "继续播放白噪音",
                )
            }
        }
    }

    fun previousWhiteNoise() = changeWhiteNoise(-1)

    fun nextWhiteNoise() = changeWhiteNoise(1)

    fun setWhiteNoiseVolume(volume: Float) {
        val safeVolume = volume.coerceIn(0.05f, 0.7f)
        whiteNoisePlayer.setVolume(safeVolume)
        _state.value = _state.value.copy(whiteNoiseVolume = safeVolume)
    }

    fun retryWhiteNoise() = viewModelScope.launch { startWhiteNoise() }

    private fun changeWhiteNoise(offset: Int) = viewModelScope.launch {
        if (whiteNoisePlaylist.size < 2 || _state.value.whiteNoiseLoading) return@launch
        whiteNoiseTrackIndex = Math.floorMod(
            whiteNoiseTrackIndex + offset,
            whiteNoisePlaylist.size,
        )
        playWhiteNoiseTrack(whiteNoisePlaylist[whiteNoiseTrackIndex], resetTimer = false)
    }

    private suspend fun startWhiteNoise() {
        whiteNoiseTimer?.cancel()
        whiteNoisePlayer.stop()
        _state.value = _state.value.copy(
            whiteNoiseLoading = true,
            whiteNoiseError = null,
            assistantError = null,
        )
        runCatching { ProductApi(backendUrl).whiteNoiseTracks() }
            .onSuccess { tracks ->
                if (tracks.isEmpty()) {
                    showWhiteNoiseError("白噪音素材库中暂时没有可播放的音频")
                    return@onSuccess
                }
                whiteNoisePlaylist = tracks.shuffled()
                whiteNoiseTrackIndex = 0
                playWhiteNoiseTrack(whiteNoisePlaylist.first(), resetTimer = true)
            }
            .onFailure {
                showWhiteNoiseError("白噪音素材暂时无法获取，请检查家庭服务连接。")
            }
    }

    private fun playWhiteNoiseTrack(track: WhiteNoiseTrack, resetTimer: Boolean) {
        _state.value = _state.value.copy(
            whiteNoisePlaying = false,
            whiteNoisePaused = false,
            whiteNoiseLoading = true,
            assistantError = null,
        )
        runCatching {
            whiteNoisePlayer.start(
                url = track.audioUrl,
                onStarted = {
                    _state.value = _state.value.copy(
                        whiteNoisePlaying = true,
                        whiteNoisePaused = false,
                        whiteNoiseLoading = false,
                        whiteNoiseTrackId = track.id,
                        whiteNoiseTrackName = track.name,
                        whiteNoiseCanSwitch = whiteNoisePlaylist.size > 1,
                        whiteNoiseError = null,
                        notice = "正在播放：${track.name}",
                    )
                    if (resetTimer) startWhiteNoiseTimer()
                },
                onError = {
                    showWhiteNoiseError("这条音频暂时无法播放，请尝试上一首或下一首。")
                },
            )
        }.onFailure {
            showWhiteNoiseError("这条音频暂时无法播放，请尝试上一首或下一首。")
        }
    }

    private fun startWhiteNoiseTimer() {
        whiteNoiseTimer?.cancel()
        _state.value = _state.value.copy(
            whiteNoiseElapsedSeconds = 0,
            whiteNoiseRemainingSeconds = 30 * 60,
        )
        whiteNoiseTimer = viewModelScope.launch {
            while (_state.value.whiteNoiseRemainingSeconds > 0) {
                delay(1_000L)
                if (_state.value.whiteNoisePlaying) {
                    _state.value = _state.value.copy(
                        whiteNoiseElapsedSeconds = _state.value.whiteNoiseElapsedSeconds + 1,
                        whiteNoiseRemainingSeconds = _state.value.whiteNoiseRemainingSeconds - 1,
                    )
                }
            }
            whiteNoisePlayer.stop()
            whiteNoisePlaylist = emptyList()
            whiteNoiseTrackIndex = -1
            _state.value = _state.value.copy(
                whiteNoisePlaying = false,
                whiteNoisePaused = false,
                whiteNoiseLoading = false,
                whiteNoiseElapsedSeconds = 0,
                whiteNoiseRemainingSeconds = 0,
                whiteNoiseTrackId = null,
                whiteNoiseTrackName = null,
                whiteNoiseCanSwitch = false,
                whiteNoiseError = null,
                notice = "白噪音已播放完毕",
            )
        }
    }

    private fun showWhiteNoiseError(message: String) {
        whiteNoisePlayer.stop()
        whiteNoiseTimer?.cancel()
        whiteNoiseTimer = null
        _state.value = _state.value.copy(
            whiteNoisePlaying = false,
            whiteNoisePaused = false,
            whiteNoiseLoading = false,
            whiteNoiseElapsedSeconds = 0,
            whiteNoiseRemainingSeconds = 0,
            whiteNoiseTrackId = null,
            whiteNoiseTrackName = null,
            whiteNoiseCanSwitch = false,
            whiteNoiseError = message,
            assistantError = null,
        )
    }

    private suspend fun refreshPrivacyAndDeviceSettings() {
        runCatching { ProductApi(backendUrl).settings() }.onSuccess { settings ->
            _state.value = _state.value.copy(
                cameraPaused = settings.optBoolean("camera_paused"),
                sleepPaused = settings.optBoolean("sleep_alerts_paused"),
                proactiveCarePaused = settings.optBoolean("proactive_care_paused"),
                psychologicalCareEnabled = settings.optBoolean("psychological_care_enabled", true),
                assistantDeviceControlConsent = settings.optString(
                    "assistant_device_control_consent", "unset",
                ),
                evidenceRetentionDays = settings.optInt("evidence_retention_days", 7),
            )
        }
    }
}
