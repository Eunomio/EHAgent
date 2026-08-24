package com.ehagent.resident

import android.Manifest
import android.os.Bundle
import android.os.Build
import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.content.pm.ActivityInfo
import android.content.Intent
import android.net.Uri
import android.app.Application
import android.view.SurfaceView
import android.view.WindowManager
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.compose.setContent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.window.DialogWindowProvider
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.core.content.ContextCompat
import android.content.pm.PackageManager
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive

internal val Brand = Color(0xFF2E7D67)
internal val BrandSoft = Color(0xFFE4F3ED)
internal val Warm = Color(0xFFF4A340)
internal val WarmSoft = Color(0xFFFFF0DC)
internal val Ink = Color(0xFF202622)
internal val Muted = Color(0xFF66706A)
internal val Canvas = Color(0xFFF6F7F3)

class MainActivity : ComponentActivity() {
    private val notificationPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        setContent { EHAgentTheme { ResidentApp() } }
    }
}

@Composable
private fun EHAgentTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(primary = Brand, secondary = Warm, background = Canvas, surface = Color.White, onSurface = Ink),
        typography = Typography(bodyLarge = MaterialTheme.typography.bodyLarge.copy(fontSize = 18.sp), titleLarge = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold)),
        content = content,
    )
}

private enum class Page(val label: String, val icon: ImageVector) {
    HOME("首页", Icons.Rounded.Home), SAFETY("安全", Icons.Rounded.HealthAndSafety),
    SLEEP("睡眠", Icons.Rounded.Bedtime), ME("我的", Icons.Rounded.Person),
    ASSISTANT("问小安", Icons.Rounded.AutoAwesome),
}

@Composable
private fun ResidentApp(viewModel: MainViewModel = androidx.lifecycle.viewmodel.compose.viewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var page by remember { mutableStateOf(Page.HOME) }
    val mainPages = remember { listOf(Page.HOME, Page.SAFETY, Page.SLEEP, Page.ME) }
    LaunchedEffect(viewModel) {
        while (isActive) {
            delay(2_000)
            viewModel.refreshSafetyStatus()
        }
    }
    Scaffold(
        containerColor = Canvas,
        bottomBar = {
            if (page != Page.ASSISTANT) {
                NavigationBar(containerColor = Color.White, tonalElevation = 3.dp) {
                    mainPages.forEach { item ->
                        NavigationBarItem(selected = page == item, onClick = { page = item }, icon = { Icon(item.icon, item.label) }, label = { Text(item.label, fontSize = 14.sp) }, colors = NavigationBarItemDefaults.colors(selectedIconColor = Brand, selectedTextColor = Brand, indicatorColor = BrandSoft))
                    }
                }
            }
        },
        floatingActionButton = {
            if (page != Page.ASSISTANT) {
                DraggableAssistantButton { page = Page.ASSISTANT }
            }
        },
        snackbarHost = { SnackbarHost(remember { SnackbarHostState() }) },
    ) { padding ->
        Box(Modifier.padding(padding).fillMaxSize()) {
            when (page) {
                Page.HOME -> HomePage(state, viewModel, onSafety = { page = Page.SAFETY }, onSleep = { page = Page.SLEEP }, onAssistant = { page = Page.ASSISTANT })
                Page.SAFETY -> SafetyPage(state, viewModel)
                Page.SLEEP -> SleepPage(state, viewModel)
                Page.ME -> MePage(state, viewModel)
                Page.ASSISTANT -> AssistantPage(state, viewModel, onBack = { page = Page.HOME })
            }
            if (state.loading) LinearProgressIndicator(Modifier.fillMaxWidth().align(Alignment.TopCenter), color = Brand)
        }
    }
}

@Composable
private fun PageBody(content: @Composable ColumnScope.() -> Unit) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(
            start = 20.dp,
            top = 22.dp,
            end = 20.dp,
            bottom = 92.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(16.dp),
        content = content,
    )
}

@Composable
private fun HomePage(state: UiState, vm: MainViewModel, onSafety: () -> Unit, onSleep: () -> Unit, onAssistant: () -> Unit) {
    val context = LocalContext.current
    PageBody {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(state.dashboard.greeting, fontSize = 30.sp, fontWeight = FontWeight.Bold, color = Ink)
                Text(state.dashboard.subtitle, color = Muted, fontSize = 17.sp)
            }
            FilledIconButton(onClick = vm::refresh, colors = IconButtonDefaults.filledIconButtonColors(containerColor = Color.White, contentColor = Brand)) { Icon(Icons.Rounded.Refresh, "刷新") }
        }
        state.error?.let { ConnectionBanner(it) }
        state.notice?.let { NoticeBanner(it) }
        Card(
            onClick = onAssistant,
            shape = RoundedCornerShape(26.dp),
            colors = CardDefaults.cardColors(containerColor = Color(0xFF2F6F62)),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Row(Modifier.padding(21.dp), verticalAlignment = Alignment.CenterVertically) {
                RoundIcon(Icons.Rounded.AutoAwesome, Color.White, Color.White.copy(alpha = .16f))
                Spacer(Modifier.width(14.dp))
                Column(Modifier.weight(1f)) {
                    Text("有事问小安", color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                    Text("生活问题、睡眠和家中情况都可以问", color = Color.White.copy(.82f), fontSize = 16.sp)
                }
                Icon(Icons.Rounded.ChevronRight, "打开", tint = Color.White)
            }
        }
        SafetyHomeCard(state.dashboard.safety, onSafety)
        SleepHomeCard(state.dashboard.sleep, onSleep)
        ContactCard(state.dashboard.contactName) { dial(context, state.dashboard.contactPhone) }
        Text("设备状态", fontSize = 21.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 4.dp))
        DeviceRow(Icons.Rounded.Videocam, "通道摄像头", deviceText(state.devices.cameraConfigured, state.devices.cameraOnline))
        DeviceRow(
            Icons.Rounded.Bed,
            "无感睡眠助手",
            when {
                !state.devices.sleepConfigured -> "等待连接"
                state.devices.sleepLastReportAt != null -> "已同步"
                else -> "已连接"
            },
        )
    }
}

@Composable
private fun SafetyHomeCard(card: SafetyCard, onClick: () -> Unit) {
    val attention = card.status == "attention"
    Card(onClick = onClick, shape = RoundedCornerShape(26.dp), colors = CardDefaults.cardColors(containerColor = if (attention) WarmSoft else BrandSoft), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(22.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                RoundIcon(Icons.Rounded.HealthAndSafety, if (attention) Warm else Brand)
                Spacer(Modifier.width(14.dp))
                Column(Modifier.weight(1f)) { Text("通道安全", color = Muted, fontSize = 16.sp); Text(card.headline, fontSize = 24.sp, fontWeight = FontWeight.Bold, maxLines = 2, overflow = TextOverflow.Ellipsis) }
                Icon(Icons.Rounded.ChevronRight, "查看")
            }
            Text(card.detail, fontSize = 17.sp, color = Ink, lineHeight = 25.sp)
        }
    }
}

@Composable
private fun SleepHomeCard(card: SleepCard, onClick: () -> Unit) {
    Card(onClick = onClick, shape = RoundedCornerShape(26.dp), colors = CardDefaults.cardColors(containerColor = Color.White), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(22.dp), verticalArrangement = Arrangement.spacedBy(15.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                RoundIcon(Icons.Rounded.Bedtime, Color(0xFF6876C7), Color(0xFFE9EBFF))
                Spacer(Modifier.width(14.dp)); Column(Modifier.weight(1f)) { Text("昨晚睡眠", color = Muted, fontSize = 16.sp); Text(card.headline, fontSize = 24.sp, fontWeight = FontWeight.Bold) }; Icon(Icons.Rounded.ChevronRight, "查看")
            }
            if (card.duration != null) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                VitalMini("呼吸", card.respiratoryRate?.let { "${formatOne(it)} 次/分" } ?: "暂无")
                VitalMini("心率", card.heartRate?.let { "${formatOne(it)} 次/分" } ?: "暂无")
                VitalMini("离床", card.bedExitCount?.let { "$it 次" } ?: "暂无")
            }
        }
    }
}

@Composable
private fun ContactCard(name: String, onClick: () -> Unit) {
    Card(shape = RoundedCornerShape(26.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Row(Modifier.fillMaxWidth().padding(20.dp), verticalAlignment = Alignment.CenterVertically) {
            RoundIcon(Icons.Rounded.FamilyRestroom, Color(0xFFE56F5B), Color(0xFFFFE9E4)); Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) { Text("需要陪伴或帮忙？", fontSize = 20.sp, fontWeight = FontWeight.Bold); Text("告诉${name}联系您", color = Muted) }
            Button(onClick = onClick, shape = RoundedCornerShape(16.dp)) { Text("联系", fontSize = 17.sp) }
        }
    }
}

@Composable
private fun SafetyPage(state: UiState, vm: MainViewModel) {
    val context = LocalContext.current
    DisposableEffect(Unit) {
        onDispose { vm.stopCameraStream() }
    }
    PageBody {
        PageTitle("居家安全", "留意每天常走的地方", Icons.Rounded.HealthAndSafety)
        CameraStreamCard(state, vm)
        SafetyCheckCard(state, vm)
        if (state.dashboard.safety.taskId == null) {
            EmptyCard(Icons.Rounded.CheckCircle, "当前没有待处理提醒", "摄像头完成检查后，结果会显示在这里。")
        } else {
            Card(shape = RoundedCornerShape(26.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFFFFE6E3))) {
                Column(Modifier.padding(22.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Text(
                        if (state.dashboard.safety.headline.startsWith("再次检查")) "复查结果" else "请留意",
                        color = Color(0xFFC73A31),
                        fontWeight = FontWeight.Bold,
                    )
                    Text(state.dashboard.safety.headline, fontSize = 26.sp, fontWeight = FontWeight.Bold)
                    Text(state.dashboard.safety.detail, fontSize = 18.sp, lineHeight = 28.sp)
                    Button(
                        onClick = vm::confirmSafetyCleaned,
                        enabled = !state.safetyAnalysisLoading && state.safetyBaseline.ready &&
                            !state.safetyBaselineNeedsRefresh && !state.cameraPaused,
                        modifier = Modifier.fillMaxWidth().height(54.dp),
                        shape = RoundedCornerShape(16.dp),
                    ) {
                        if (state.safetyAnalysisLoading) {
                            CircularProgressIndicator(Modifier.size(22.dp), color = Color.White, strokeWidth = 2.dp)
                            Spacer(Modifier.width(9.dp))
                            Text("正在重新检查…", fontSize = 18.sp)
                        } else {
                            Icon(Icons.Rounded.Done, null)
                            Spacer(Modifier.width(8.dp))
                            Text("我已整理好", fontSize = 18.sp)
                        }
                    }
                    OutlinedButton(
                        onClick = { vm.taskAction("need_help"); dial(context, state.dashboard.contactPhone) },
                        enabled = !state.safetyAnalysisLoading,
                        modifier = Modifier.fillMaxWidth().height(54.dp),
                        shape = RoundedCornerShape(16.dp),
                    ) { Text("联系家人", fontSize = 18.sp) }
                    TextButton(
                        onClick = { vm.taskAction("later") },
                        enabled = !state.safetyAnalysisLoading,
                        modifier = Modifier.align(Alignment.CenterHorizontally),
                    ) { Text("30分钟后提醒") }
                }
            }
        }
        BaselineCard(
            baseline = state.safetyBaseline,
            needsRefresh = state.safetyBaselineNeedsRefresh,
            saving = state.baselineSaving,
            error = state.baselineError,
            canRetry = !state.cameraPaused && state.devices.cameraConfigured,
            onRetry = { vm.saveSafetyBaseline() },
        )
        SettingsSwitch("暂停通道检查", "需要隐私时可以随时暂停", state.cameraPaused, vm::setCameraPaused)
    }
}

@Composable
private fun SafetyCheckCard(state: UiState, vm: MainViewModel) {
    val result = state.safetyAnalysis
    val resultColor = when (result?.riskLevel) {
        "high", "medium" -> Color(0xFFFFE6E3)
        "low" -> Color(0xFFFFF3D6)
        else -> BrandSoft
    }
    Card(shape = RoundedCornerShape(26.dp), colors = CardDefaults.cardColors(containerColor = resultColor)) {
        Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(11.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                RoundIcon(
                    Icons.Rounded.Search,
                    when (result?.riskLevel) {
                        "high", "medium" -> Color(0xFFC73A31)
                        "low" -> Color(0xFFB77900)
                        else -> Brand
                    },
                )
                Spacer(Modifier.width(13.dp))
                Column(Modifier.weight(1f)) {
                    Text("检查当前通道", fontSize = 21.sp, fontWeight = FontWeight.Bold)
                    Text(
                        when {
                            state.safetyBaselineNeedsRefresh -> "摄像头角度变化较大，正在重新识别通道"
                            state.safetyBaseline.ready -> "自动监测中，画面持续变化后会检查"
                            else -> "正在自动识别通道"
                        },
                        color = Muted,
                    )
                }
            }
            result?.let {
                HorizontalDivider(color = Ink.copy(alpha = .08f))
                val statusColor = when (it.riskLevel) {
                    "high", "medium" -> Color(0xFFC73A31)
                    "low" -> Color(0xFF9A6700)
                    else -> Brand
                }
                Surface(color = statusColor.copy(alpha = .12f), shape = RoundedCornerShape(50)) {
                    Text(
                        when (it.riskLevel) {
                            "high", "medium" -> "需要整改"
                            "low" -> "潜在风险"
                            else -> "通道安全"
                        },
                        color = statusColor,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 5.dp),
                    )
                }
                Text(it.headline, fontSize = 23.sp, fontWeight = FontWeight.Bold)
                Text(it.reason, fontSize = 17.sp, lineHeight = 25.sp)
                Text(it.actionText, color = statusColor, fontWeight = FontWeight.SemiBold)
                Text("检查时间 ${shortDateTime(it.checkedAt)}", color = Muted, fontSize = 14.sp)
                if (it.speechUrl != null && it.riskLevel in setOf("medium", "high")) {
                    TextButton(onClick = vm::replaySafetySpeech) {
                        Icon(Icons.Rounded.VolumeUp, null)
                        Spacer(Modifier.width(6.dp))
                        Text("播放语音提醒")
                    }
                }
            }
            state.safetyAnalysisError?.let { Text(it, color = Color(0xFFB44336)) }
            Button(
                onClick = vm::analyzeSafety,
                enabled = state.safetyBaseline.ready && !state.safetyBaselineNeedsRefresh &&
                    !state.safetyAnalysisLoading && !state.cameraPaused,
                modifier = Modifier.fillMaxWidth().height(54.dp),
                shape = RoundedCornerShape(16.dp),
            ) {
                if (state.safetyAnalysisLoading) {
                    CircularProgressIndicator(Modifier.size(22.dp), color = Color.White, strokeWidth = 2.dp)
                    Spacer(Modifier.width(9.dp))
                    Text("正在检查…", fontSize = 18.sp)
                } else {
                    Icon(Icons.Rounded.CameraAlt, null)
                    Spacer(Modifier.width(8.dp))
                    Text("立即检查通道", fontSize = 18.sp)
                }
            }
        }
    }
}

@Composable
private fun BaselineCard(
    baseline: SafetyBaselineStatus,
    needsRefresh: Boolean,
    saving: Boolean,
    error: String?,
    canRetry: Boolean,
    onRetry: () -> Unit,
) {
    Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Row(Modifier.fillMaxWidth().padding(20.dp), verticalAlignment = Alignment.CenterVertically) {
            RoundIcon(Icons.Rounded.AddAPhoto, Brand, BrandSoft)
            Spacer(Modifier.width(13.dp))
            Column(Modifier.weight(1f)) {
                Text("通道识别", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Text(
                    when {
                        saving -> "正在识别当前通道…"
                        error != null -> "暂时无法识别，请整理出安全通道后重试"
                        needsRefresh -> "摄像头角度变化较大，正在重新识别"
                        baseline.ready -> "已自动识别${baseline.capturedAt?.let { " · ${shortDateTime(it)}" }.orEmpty()}"
                        else -> "正在自动识别通道"
                    },
                    color = Muted,
                    lineHeight = 22.sp,
                )
                error?.let { Text(it, color = Color(0xFFB44336), fontSize = 14.sp, lineHeight = 20.sp) }
            }
            TextButton(onClick = onRetry, enabled = canRetry && !saving) {
                Text(if (baseline.ready) "重新识别" else "立即识别")
            }
        }
    }
}

@Composable
private fun CameraStreamCard(state: UiState, vm: MainViewModel) {
    Card(
        shape = RoundedCornerShape(26.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White),
    ) {
        Column(
            Modifier.fillMaxWidth().padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                RoundIcon(Icons.Rounded.Videocam, Brand, BrandSoft)
                Spacer(Modifier.width(13.dp))
                Column(Modifier.weight(1f)) {
                    Text("通道实时画面", fontSize = 21.sp, fontWeight = FontWeight.Bold)
                    Text("只有您主动打开时才播放", color = Muted)
                }
                if (state.cameraSession != null) {
                    TextButton(onClick = vm::stopCameraStream) { Text("关闭画面") }
                }
            }
            when {
                state.cameraPaused -> CameraMessage("通道检查已暂停", "恢复通道检查后可以查看画面")
                !state.devices.cameraConfigured -> CameraMessage("摄像头等待连接", "连接萤石C6c后可以查看画面")
                state.devices.cameraOnline == false -> CameraMessage("摄像头当前离线", "请检查摄像头电源和网络")
                state.cameraStreamLoading -> Row(
                    Modifier.fillMaxWidth().padding(vertical = 22.dp),
                    horizontalArrangement = Arrangement.Center,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    CircularProgressIndicator(Modifier.size(28.dp), color = Brand)
                    Spacer(Modifier.width(12.dp))
                    Text("正在打开画面…", fontSize = 17.sp)
                }
                state.cameraSession != null -> CameraPlayer(
                    state.cameraSession,
                    vm,
                    state.cameraMoveError,
                    state.safetyAnalysis,
                    state.safetyBaselineNeedsRefresh,
                )
                else -> {
                    state.cameraStreamError?.let {
                        Text(it, color = Color(0xFFB44336), lineHeight = 24.sp)
                    }
                    Button(
                        onClick = vm::startCameraStream,
                        modifier = Modifier.fillMaxWidth().height(54.dp),
                        shape = RoundedCornerShape(16.dp),
                    ) {
                        Icon(Icons.Rounded.PlayArrow, null)
                        Spacer(Modifier.width(8.dp))
                        Text(
                            if (state.cameraStreamError == null) "查看实时画面" else "重新打开",
                            fontSize = 18.sp,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun CameraMessage(title: String, detail: String) {
    Surface(color = Canvas, shape = RoundedCornerShape(18.dp)) {
        Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text(title, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
            Text(detail, color = Muted)
        }
    }
}

@Composable
private fun CameraPlayer(
    session: CameraSdkSession,
    vm: MainViewModel,
    moveError: String?,
    analysis: SafetyAnalysis?,
    baselineNeedsRefresh: Boolean,
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    var playbackState by remember(session) { mutableStateOf(EzvizPlaybackState.CONNECTING) }
    var playbackError by remember(session) { mutableStateOf<String?>(null) }
    var fullscreen by remember(session) { mutableStateOf(false) }
    val regions = analysis?.hazardRegions.orEmpty().takeUnless { baselineNeedsRefresh }.orEmpty()
    val controller = remember(session) {
        EzvizPlayerController(
            application = context.applicationContext as Application,
            session = session,
        ) { state, detail ->
            playbackState = state
            playbackError = detail
        }
    }
    DisposableEffect(controller, lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_START -> controller.onStart()
                Lifecycle.Event.ON_STOP -> controller.onStop()
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        if (lifecycleOwner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) {
            controller.onStart()
        }
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            controller.release()
        }
    }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        if (!fullscreen) {
            CameraViewport(
                controller,
                playbackState,
                Modifier.fillMaxWidth().aspectRatio(16f / 9f),
                regions = regions,
                onFullscreen = { fullscreen = true },
            )
        }
        CameraMoveHandle(onMove = vm::setCameraMoving)
        Text("实时画面默认静音，离开本页后自动关闭", color = Muted, fontSize = 14.sp)
        playbackError?.let { Text(it, color = Color(0xFFB44336)) }
        moveError?.let { Text(it, color = Color(0xFFB44336)) }
    }
    if (fullscreen) {
        FullscreenCamera(
            controller = controller,
            playbackState = playbackState,
            moveError = moveError,
            onMove = vm::setCameraMoving,
            regions = regions,
            onClose = { fullscreen = false },
        )
    }
}

@Composable
private fun CameraViewport(
    controller: EzvizPlayerController,
    playbackState: EzvizPlaybackState,
    modifier: Modifier,
    regions: List<HazardRegion> = emptyList(),
    onFullscreen: (() -> Unit)? = null,
    fullscreen: Boolean = false,
) {
    Box(
        modifier.clip(if (fullscreen) RectangleShape else RoundedCornerShape(18.dp)).background(Color.Black),
        contentAlignment = Alignment.Center,
    ) {
        AndroidView(
            factory = { viewContext ->
                SurfaceView(viewContext).apply {
                    keepScreenOn = true
                    holder.addCallback(controller)
                }
            },
            modifier = Modifier.fillMaxSize(),
        )
        RiskRegionOverlay(regions, Modifier.fillMaxSize())
        if (playbackState == EzvizPlaybackState.CONNECTING) CircularProgressIndicator(color = Color.White)
        onFullscreen?.let {
            FilledIconButton(
                onClick = it,
                modifier = Modifier.align(Alignment.TopEnd).padding(8.dp),
                colors = IconButtonDefaults.filledIconButtonColors(containerColor = Color.Black.copy(alpha = .58f), contentColor = Color.White),
            ) { Icon(Icons.Rounded.Fullscreen, "全屏查看") }
        }
    }
}

@Composable
private fun RiskRegionOverlay(regions: List<HazardRegion>, modifier: Modifier = Modifier) {
    if (regions.isEmpty()) return
    Box(modifier) {
        Canvas(Modifier.fillMaxSize()) {
            regions.forEach { region ->
                val color = if (region.riskLevel == "low") Color(0xFFFFB300) else Color(0xFFE53935)
                val left = size.width * region.x1 / 1000f
                val top = size.height * region.y1 / 1000f
                val width = size.width * (region.x2 - region.x1) / 1000f
                val height = size.height * (region.y2 - region.y1) / 1000f
                val topLeft = androidx.compose.ui.geometry.Offset(left, top)
                val boxSize = androidx.compose.ui.geometry.Size(width, height)
                drawRect(color.copy(alpha = .14f), topLeft = topLeft, size = boxSize)
                drawRect(
                    color,
                    topLeft = topLeft,
                    size = boxSize,
                    style = Stroke(width = 3.dp.toPx()),
                )
            }
        }
        Surface(
            modifier = Modifier.align(Alignment.TopStart).padding(8.dp),
            color = Color.Black.copy(alpha = .68f),
            shape = RoundedCornerShape(6.dp),
        ) {
            Text(
                "最近检查位置",
                color = Color.White,
                fontSize = 12.sp,
                modifier = Modifier.padding(horizontal = 7.dp, vertical = 4.dp),
            )
        }
        Column(
            Modifier.align(Alignment.BottomStart).padding(8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            regions.distinctBy { it.label to it.riskLevel }.take(3).forEach { region ->
                val color = if (region.riskLevel == "low") Color(0xFFFFB300) else Color(0xFFE53935)
                Surface(color = Color.Black.copy(alpha = .68f), shape = RoundedCornerShape(6.dp)) {
                    Text(
                        "${if (region.riskLevel == "low") "留意" else "需整改"} · ${region.label}",
                        color = color,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(horizontal = 7.dp, vertical = 4.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun CameraMoveHandle(
    onMove: (CameraDirection, Boolean) -> Unit,
    dark: Boolean = false,
    modifier: Modifier = Modifier.fillMaxWidth(),
) {
    val labelColor = if (dark) Color.White.copy(alpha = .78f) else Muted
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        Spacer(Modifier.height(7.dp))
        DirectionButton(Icons.Rounded.KeyboardArrowUp, "向上移动", CameraDirection.UP, onMove, dark)
        Row(verticalAlignment = Alignment.CenterVertically) {
            DirectionButton(Icons.Rounded.KeyboardArrowLeft, "向左移动", CameraDirection.LEFT, onMove, dark)
            Surface(Modifier.size(48.dp).padding(13.dp), shape = CircleShape, color = if (dark) Color.White.copy(alpha = .28f) else Brand.copy(alpha = .22f)) {}
            DirectionButton(Icons.Rounded.KeyboardArrowRight, "向右移动", CameraDirection.RIGHT, onMove, dark)
        }
        DirectionButton(Icons.Rounded.KeyboardArrowDown, "向下移动", CameraDirection.DOWN, onMove, dark)
    }
}

@Composable
private fun DirectionButton(
    icon: ImageVector,
    description: String,
    direction: CameraDirection,
    onMove: (CameraDirection, Boolean) -> Unit,
    dark: Boolean,
) {
    Surface(
        modifier = Modifier.size(48.dp).pointerInput(direction) {
            detectTapGestures(onPress = {
                onMove(direction, true)
                try {
                    tryAwaitRelease()
                } finally {
                    onMove(direction, false)
                }
            })
        },
        shape = CircleShape,
        color = if (dark) Color.White.copy(alpha = .2f) else BrandSoft,
    ) {
        Box(contentAlignment = Alignment.Center) {
            Icon(icon, description, tint = if (dark) Color.White else Brand, modifier = Modifier.size(30.dp))
        }
    }
}

@Composable
private fun FullscreenCamera(
    controller: EzvizPlayerController,
    playbackState: EzvizPlaybackState,
    moveError: String?,
    onMove: (CameraDirection, Boolean) -> Unit,
    regions: List<HazardRegion>,
    onClose: () -> Unit,
) {
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        val context = LocalContext.current
        val view = LocalView.current
        val activity = remember(context) { context.findActivity() }
        DisposableEffect(activity) {
            val previousOrientation = activity?.requestedOrientation
            activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
            onDispose {
                if (previousOrientation != null) activity.requestedOrientation = previousOrientation
            }
        }
        DisposableEffect(view) {
            val window = (view.parent as DialogWindowProvider).window
            window.setLayout(WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.MATCH_PARENT)
            WindowCompat.setDecorFitsSystemWindows(window, false)
            WindowInsetsControllerCompat(window, view).hide(WindowInsetsCompat.Type.systemBars())
            onDispose { WindowInsetsControllerCompat(window, view).show(WindowInsetsCompat.Type.systemBars()) }
        }
        Box(Modifier.fillMaxSize().background(Color.Black)) {
            CameraViewport(
                controller,
                playbackState,
                Modifier.fillMaxSize(),
                regions = regions,
                fullscreen = true,
            )
            FilledIconButton(
                onClick = onClose,
                modifier = Modifier.align(Alignment.TopEnd).padding(18.dp),
                colors = IconButtonDefaults.filledIconButtonColors(containerColor = Color.Black.copy(alpha = .58f), contentColor = Color.White),
            ) { Icon(Icons.Rounded.FullscreenExit, "退出全屏") }
            Column(
                Modifier.align(Alignment.BottomEnd).padding(end = 28.dp, bottom = 22.dp),
                horizontalAlignment = Alignment.End,
            ) {
                CameraMoveHandle(onMove, dark = true, modifier = Modifier.width(152.dp))
                moveError?.let {
                    Text(
                        it,
                        color = Color(0xFFFFB4AB),
                        modifier = Modifier.widthIn(max = 230.dp).padding(top = 6.dp),
                    )
                }
            }
        }
    }
}

private tailrec fun Context.findActivity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.findActivity()
    else -> null
}

private fun shortDateTime(value: String): String = value.replace('T', ' ').take(16)

@Composable
private fun SleepPage(state: UiState, vm: MainViewModel) {
    val sleep = state.dashboard.sleep
    PageBody {
        PageTitle("睡眠", "看看昨晚休息得怎么样", Icons.Rounded.Bedtime)
        if (sleep.duration == null) {
            EmptyCard(Icons.Rounded.Bed, "还没有睡眠记录", "连接无感睡眠助手后，这里会显示真实睡眠数据。")
        } else {
            Card(shape = RoundedCornerShape(28.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFF303B73))) {
                Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("昨晚共睡眠", color = Color.White.copy(.75f), fontSize = 17.sp)
                    Text("${sleep.duration / 60} 小时 ${sleep.duration % 60} 分钟", color = Color.White, fontSize = 32.sp, fontWeight = FontWeight.Bold)
                    if (sleep.sleepStart != null && sleep.sleepEnd != null) {
                        Text(
                            "${clockText(sleep.sleepStart)} 入睡 · ${clockText(sleep.sleepEnd)} 起床",
                            color = Color.White.copy(.82f),
                            fontSize = 16.sp,
                        )
                    }
                    sleep.sleepScore?.let {
                        Text("睡眠得分 ${formatOne(it)}", color = Color.White, fontSize = 18.sp)
                    }
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                VitalCard(Modifier.weight(1f), Icons.Rounded.Air, "平均呼吸", sleep.respiratoryRate?.let { formatOne(it) } ?: "—", "次/分")
                VitalCard(Modifier.weight(1f), Icons.Rounded.Favorite, "平均心率", sleep.heartRate?.let { formatOne(it) } ?: "—", "次/分")
            }
            VitalCard(Modifier.fillMaxWidth(), Icons.Rounded.DirectionsWalk, "夜间离床", sleep.bedExitCount?.toString() ?: "—", "次")
            SleepStagesCard(sleep)
            sleep.analysis?.let {
                Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = BrandSoft)) {
                    Column(Modifier.padding(19.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) { Icon(Icons.Rounded.AutoAwesome, null, tint = Brand); Spacer(Modifier.width(8.dp)); Text("昨晚小结", fontSize = 19.sp, fontWeight = FontWeight.Bold) }
                        Text(it, fontSize = 17.sp, lineHeight = 26.sp)
                    }
                }
            }
            Text("数据来自床边设备的无感测量。身体不舒服时，请及时联系家人或医生。", color = Muted, lineHeight = 24.sp)
        }
        SettingsSwitch("暂停睡眠提醒", "睡眠数据仍会保留", state.sleepPaused, vm::setSleepPaused)
    }
}

@Composable
private fun SleepStagesCard(sleep: SleepCard) {
    val stages = listOfNotNull(
        sleep.awakeMinutes?.let { "清醒" to it },
        sleep.lightSleepMinutes?.let { "浅睡" to it },
        sleep.deepSleepMinutes?.let { "深睡" to it },
        sleep.remSleepMinutes?.let { "快速眼动" to it },
    )
    if (stages.isEmpty()) return
    Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(19.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("睡眠构成", fontSize = 19.sp, fontWeight = FontWeight.Bold)
            stages.forEach { (label, minutes) ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(label, color = Muted, fontSize = 16.sp)
                    Text(formatMinutes(minutes), fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

@Composable
private fun MePage(state: UiState, vm: MainViewModel) {
    var url by remember(vm.backendUrl) { mutableStateOf(vm.backendUrl) }
    var contactName by remember(state.dashboard.contactName) { mutableStateOf(state.dashboard.contactName) }
    var contactPhone by remember(state.dashboard.contactPhone) { mutableStateOf(state.dashboard.contactPhone) }
    var feedback by remember { mutableStateOf("") }
    PageBody {
        PageTitle("我的", "管理家中设备和联系设置", Icons.Rounded.Person)
        Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("家庭服务连接", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Text("手机和家中电脑需连接同一个网络", color = Muted)
                OutlinedTextField(value = url, onValueChange = { url = it }, label = { Text("服务地址") }, placeholder = { Text("http://192.168.1.10:8000") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Button(onClick = { vm.saveBackend(url) }, modifier = Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(15.dp)) { Text("保存并连接", fontSize = 17.sp) }
            }
        }
        state.notice?.let { NoticeBanner(it) }
        state.error?.let { ConnectionBanner(it) }
        Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("紧急联系人", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                OutlinedTextField(value = contactName, onValueChange = { contactName = it }, label = { Text("家人称呼") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = contactPhone, onValueChange = { contactPhone = it }, label = { Text("电话号码") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedButton(onClick = { vm.saveContact(contactName, contactPhone) }, modifier = Modifier.fillMaxWidth().height(50.dp), shape = RoundedCornerShape(15.dp)) { Text("保存联系方式", fontSize = 17.sp) }
            }
        }
        Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("说说您的感受", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Text("可以告诉我们哪里好用、哪里需要改进", color = Muted)
                OutlinedTextField(value = feedback, onValueChange = { feedback = it }, placeholder = { Text("例如：睡眠小结看得很清楚") }, minLines = 3, maxLines = 5, modifier = Modifier.fillMaxWidth())
                Button(onClick = { vm.sendFeedback(feedback) { feedback = "" } }, modifier = Modifier.fillMaxWidth().height(50.dp), shape = RoundedCornerShape(15.dp)) { Text("提交", fontSize = 17.sp) }
            }
        }
        Text("我的设备", fontSize = 21.sp, fontWeight = FontWeight.Bold)
        DeviceRow(Icons.Rounded.Videocam, "萤石 C6c", deviceText(state.devices.cameraConfigured, state.devices.cameraOnline))
        DeviceRow(Icons.Rounded.Bed, "无感睡眠助手", if (state.devices.sleepConfigured) "已连接" else "等待连接")
        Text("隐私开关", fontSize = 21.sp, fontWeight = FontWeight.Bold)
        SettingsSwitch("通道检查", if (state.cameraPaused) "当前已暂停" else "当前已开启", !state.cameraPaused) { vm.setCameraPaused(!it) }
        SettingsSwitch("睡眠提醒", if (state.sleepPaused) "当前已暂停" else "当前已开启", !state.sleepPaused) { vm.setSleepPaused(!it) }
    }
}

@Composable private fun PageTitle(title: String, subtitle: String, icon: ImageVector) { Row(verticalAlignment = Alignment.CenterVertically) { RoundIcon(icon, Brand); Spacer(Modifier.width(14.dp)); Column { Text(title, fontSize = 29.sp, fontWeight = FontWeight.Bold); Text(subtitle, color = Muted, fontSize = 16.sp) } } }
@Composable private fun RoundIcon(icon: ImageVector, color: Color, background: Color = Color.White) { Box(Modifier.size(52.dp).clip(CircleShape).background(background), contentAlignment = Alignment.Center) { Icon(icon, null, tint = color, modifier = Modifier.size(28.dp)) } }
@Composable private fun VitalMini(label: String, value: String) { Column { Text(label, color = Muted, fontSize = 14.sp); Text(value, fontWeight = FontWeight.SemiBold, fontSize = 16.sp) } }
@Composable private fun VitalCard(modifier: Modifier, icon: ImageVector, label: String, value: String, unit: String) { Card(modifier, shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) { Column(Modifier.padding(19.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) { Icon(icon, null, tint = Brand); Text(label, color = Muted); Row(verticalAlignment = Alignment.Bottom) { Text(value, fontSize = 29.sp, fontWeight = FontWeight.Bold); Spacer(Modifier.width(4.dp)); Text(unit, color = Muted, modifier = Modifier.padding(bottom = 4.dp)) } } } }
@Composable private fun EmptyCard(icon: ImageVector, title: String, detail: String) { Card(shape = RoundedCornerShape(26.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) { Column(Modifier.fillMaxWidth().padding(26.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) { RoundIcon(icon, Brand, BrandSoft); Text(title, fontSize = 22.sp, fontWeight = FontWeight.Bold); Text(detail, color = Muted, lineHeight = 25.sp) } } }
@Composable private fun DeviceRow(icon: ImageVector, title: String, status: String) { Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) { Row(Modifier.fillMaxWidth().padding(17.dp), verticalAlignment = Alignment.CenterVertically) { Icon(icon, null, tint = Brand, modifier = Modifier.size(28.dp)); Spacer(Modifier.width(14.dp)); Text(title, Modifier.weight(1f), fontSize = 18.sp, fontWeight = FontWeight.SemiBold); Text(status, color = Muted) } } }
@Composable private fun SettingsSwitch(title: String, detail: String, checked: Boolean, onChecked: (Boolean) -> Unit) { Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) { Row(Modifier.fillMaxWidth().padding(18.dp), verticalAlignment = Alignment.CenterVertically) { Column(Modifier.weight(1f)) { Text(title, fontSize = 18.sp, fontWeight = FontWeight.SemiBold); Text(detail, color = Muted) }; Switch(checked, onChecked, colors = SwitchDefaults.colors(checkedTrackColor = Brand)) } } }
@Composable private fun ConnectionBanner(text: String) { Surface(color = Color(0xFFFFE5E1), shape = RoundedCornerShape(16.dp)) { Row(Modifier.fillMaxWidth().padding(15.dp), verticalAlignment = Alignment.CenterVertically) { Icon(Icons.Rounded.WifiOff, null, tint = Color(0xFFB44336)); Spacer(Modifier.width(10.dp)); Text(text, color = Color(0xFF7D2E25)) } } }
@Composable private fun NoticeBanner(text: String) { Surface(color = BrandSoft, shape = RoundedCornerShape(16.dp)) { Row(Modifier.fillMaxWidth().padding(15.dp), verticalAlignment = Alignment.CenterVertically) { Icon(Icons.Rounded.CheckCircle, null, tint = Brand); Spacer(Modifier.width(10.dp)); Text(text, color = Color(0xFF205B4B)) } } }
private fun deviceText(configured: Boolean, online: Boolean?): String = when { !configured -> "等待连接"; online == true -> "已连接"; online == false -> "离线"; else -> "已配置" }
private fun formatOne(value: Double): String = if (value % 1.0 == 0.0) value.toInt().toString() else String.format("%.1f", value)
private fun formatMinutes(minutes: Int): String =
    if (minutes >= 60) "${minutes / 60}小时${minutes % 60}分钟" else "${minutes}分钟"
private fun clockText(timestamp: String): String =
    timestamp.substringAfter('T', timestamp).take(5)
private fun dial(context: android.content.Context, phone: String) {
    if (phone.isNotBlank()) {
        context.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:${Uri.encode(phone)}")))
    } else {
        Toast.makeText(context, "请先在“我的”中填写家人电话", Toast.LENGTH_LONG).show()
    }
}
