package com.ehagent.resident

import android.Manifest
import android.os.Bundle
import android.os.Build
import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.content.ActivityNotFoundException
import android.content.pm.ActivityInfo
import android.content.Intent
import android.net.Uri
import android.app.Application
import android.speech.RecognizerIntent
import android.view.SurfaceView
import android.view.WindowManager
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
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
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.zIndex
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

private enum class HomeModule(val storageKey: String, val title: String) {
    CARE("care", "主动关怀"),
    SAFETY("safety", "居家安全"),
    SLEEP("sleep", "昨晚睡眠"),
    CONTACT("contact", "联系家人"),
    DEVICES("devices", "设备状态"),
}

private val defaultHomeModules = HomeModule.entries.toList()

internal val Brand = Color(0xFF2E7D67)
internal val BrandSoft = Color(0xFFE4F3ED)
internal val Warm = Color(0xFFF4A340)
internal val WarmSoft = Color(0xFFFFF0DC)
internal val Ink = Color(0xFF202622)
internal val Muted = Color(0xFF66706A)
internal val Canvas = Color(0xFFF6F7F3)

internal fun safetyRiskLabel(riskLevel: String?): String = when (riskLevel) {
    "clear" -> "未检测到风险"
    "low" -> "低风险"
    "medium" -> "中风险"
    "high" -> "高风险"
    "blocked" -> "通道阻塞"
    "insufficient" -> "画面不清楚"
    else -> "等待检查"
}

internal fun safetyRiskForeground(riskLevel: String?): Color = when (riskLevel) {
    "clear" -> Color(0xFF237A57)
    "low" -> Color(0xFF8A6A00)
    "medium" -> Color(0xFFB85C00)
    "high" -> Color(0xFFC73A31)
    "blocked" -> Color(0xFF326A8F)
    else -> Color(0xFF66706A)
}

internal fun safetyRiskBackground(riskLevel: String?): Color = when (riskLevel) {
    "clear" -> Color(0xFFE4F3ED)
    "low" -> Color(0xFFFFF6CC)
    "medium" -> Color(0xFFFFE8CC)
    "high" -> Color(0xFFFFE6E3)
    "blocked" -> Color(0xFFE4F0F7)
    else -> Color(0xFFF0F2F1)
}

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
    SLEEP("睡眠", Icons.Rounded.Bedtime), PRIVACY("隐私", Icons.Rounded.PrivacyTip),
    ME("我的", Icons.Rounded.Person),
    ASSISTANT("问小安", Icons.Rounded.AutoAwesome),
}

@Composable
private fun ResidentApp(viewModel: MainViewModel = androidx.lifecycle.viewmodel.compose.viewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var page by remember { mutableStateOf(Page.HOME) }
    val mainPages = remember { listOf(Page.HOME, Page.SAFETY, Page.SLEEP, Page.PRIVACY, Page.ME) }
    LaunchedEffect(viewModel) {
        while (isActive) {
            delay(2_000)
            viewModel.refreshSafetyStatus()
        }
    }
    Scaffold(
        containerColor = Canvas,
        bottomBar = {
            NavigationBar(containerColor = Color.White, tonalElevation = 3.dp) {
                mainPages.forEach { item ->
                    NavigationBarItem(
                        selected = page == item || (page == Page.ASSISTANT && item == Page.HOME),
                        onClick = { page = item },
                        icon = { Icon(item.icon, item.label) },
                        label = { Text(item.label, fontSize = 13.sp) },
                        colors = NavigationBarItemDefaults.colors(selectedIconColor = Brand, selectedTextColor = Brand, indicatorColor = BrandSoft),
                    )
                }
            }
        },
        floatingActionButton = {
            if (page != Page.ASSISTANT && page != Page.HOME) {
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
                Page.PRIVACY -> PrivacyPage(state, viewModel)
                Page.ME -> MePage(state, viewModel) {
                    viewModel.startProfileOnboarding()
                    page = Page.ASSISTANT
                }
                Page.ASSISTANT -> AssistantPage(state, viewModel, onBack = { page = Page.HOME })
            }
            if (state.loading) LinearProgressIndicator(Modifier.fillMaxWidth().align(Alignment.TopCenter), color = Brand)
        }
    }
}

@Composable
private fun PageBody(content: @Composable ColumnScope.() -> Unit) {
    val horizontalPadding = if (LocalConfiguration.current.screenWidthDp < 380) 16.dp else 20.dp
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(
            start = horizontalPadding,
            top = 22.dp,
            end = horizontalPadding,
            bottom = 92.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(16.dp),
        content = content,
    )
}

@Composable
private fun HomePage(state: UiState, vm: MainViewModel, onSafety: () -> Unit, onSleep: () -> Unit, onAssistant: () -> Unit) {
    val context = LocalContext.current
    val compactLayout = LocalConfiguration.current.screenWidthDp < 380
    val horizontalPadding = if (compactLayout) 16.dp else 20.dp
    val preferences = remember(context) { context.getSharedPreferences("home_layout", Context.MODE_PRIVATE) }
    val storedOrder = remember {
        preferences.getString("module_order", null)
            ?.split(',')
            ?.mapNotNull { key -> HomeModule.entries.firstOrNull { it.storageKey == key } }
            ?.distinct()
            .orEmpty()
    }
    val modules = remember {
        mutableStateListOf<HomeModule>().apply {
            addAll(storedOrder + defaultHomeModules.filterNot(storedOrder::contains))
        }
    }
    val visibleModules = modules.filter { it != HomeModule.CARE || state.dashboard.activeCare != null }
    val listState = rememberLazyListState()
    var draggedModule by remember { mutableStateOf<HomeModule?>(null) }
    var draggedDistance by remember { mutableFloatStateOf(0f) }

    fun saveOrder() {
        preferences.edit().putString("module_order", modules.joinToString(",") { it.storageKey }).apply()
    }

    LaunchedEffect(Unit) { vm.loadAssistantConversation() }

    LazyColumn(
        state = listState,
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = horizontalPadding, top = 22.dp, end = horizontalPadding, bottom = 92.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item(key = "home_header") {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(state.dashboard.greeting, fontSize = 30.sp, fontWeight = FontWeight.Bold, color = Ink)
                }
                FilledIconButton(onClick = vm::refresh, colors = IconButtonDefaults.filledIconButtonColors(containerColor = Color.White, contentColor = Brand)) { Icon(Icons.Rounded.Refresh, "刷新") }
            }
        }
        state.error?.let { error -> item(key = "home_error") { ConnectionBanner(error) } }
        state.notice?.let { notice -> item(key = "home_notice") { NoticeBanner(notice) } }
        item(key = "assistant_primary") { HomeAssistantPanel(state, vm, onAssistant) }
        item(key = "module_hint") {
            if (compactLayout) {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("生活模块", fontSize = 21.sp, fontWeight = FontWeight.Bold)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Rounded.DragHandle, null, tint = Muted, modifier = Modifier.size(20.dp))
                        Spacer(Modifier.width(5.dp))
                        Text("长按卡片可调整顺序", color = Muted, fontSize = 14.sp)
                    }
                }
            } else {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text("生活模块", fontSize = 21.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                    Icon(Icons.Rounded.DragHandle, null, tint = Muted)
                    Spacer(Modifier.width(5.dp))
                    Text("长按卡片可调整顺序", color = Muted, fontSize = 14.sp)
                }
            }
        }
        items(visibleModules, key = { "module_${it.storageKey}" }) { module ->
            val isDragging = draggedModule == module
            Box(
                Modifier
                    .fillMaxWidth()
                    .zIndex(if (isDragging) 1f else 0f)
                    .graphicsLayer {
                        translationY = if (isDragging) draggedDistance else 0f
                        shadowElevation = if (isDragging) 18f else 0f
                    }
                    .pointerInput(module, visibleModules) {
                        detectDragGesturesAfterLongPress(
                            onDragStart = {
                                draggedModule = module
                                draggedDistance = 0f
                            },
                            onDragCancel = {
                                draggedModule = null
                                draggedDistance = 0f
                            },
                            onDragEnd = {
                                draggedModule = null
                                draggedDistance = 0f
                                saveOrder()
                            },
                            onDrag = { change, dragAmount ->
                                change.consume()
                                draggedDistance += dragAmount.y
                                val currentInfo = listState.layoutInfo.visibleItemsInfo
                                    .firstOrNull { it.key == "module_${module.storageKey}" }
                                    ?: return@detectDragGesturesAfterLongPress
                                val draggedCenter = currentInfo.offset + currentInfo.size / 2 + draggedDistance
                                val targetInfo = listState.layoutInfo.visibleItemsInfo.firstOrNull { info ->
                                    info.key.toString().startsWith("module_") &&
                                        info.key != currentInfo.key &&
                                        draggedCenter >= info.offset &&
                                        draggedCenter <= info.offset + info.size
                                } ?: return@detectDragGesturesAfterLongPress
                                val target = HomeModule.entries.firstOrNull {
                                    targetInfo.key == "module_${it.storageKey}"
                                } ?: return@detectDragGesturesAfterLongPress
                                val fromIndex = modules.indexOf(module)
                                val toIndex = modules.indexOf(target)
                                if (fromIndex >= 0 && toIndex >= 0 && fromIndex != toIndex) {
                                    modules.removeAt(fromIndex)
                                    modules.add(toIndex, module)
                                    draggedDistance += currentInfo.offset - targetInfo.offset
                                }
                            },
                        )
                    },
            ) {
                when (module) {
                    HomeModule.CARE -> state.dashboard.activeCare?.let { event ->
                        ProactiveCareCard(event) {
                            vm.startProactiveEvent(event.id)
                            onAssistant()
                        }
                    }
                    HomeModule.SAFETY -> SafetyHomeCard(state.dashboard.safety, onSafety)
                    HomeModule.SLEEP -> SleepHomeCard(state.dashboard.sleep, onSleep)
                    HomeModule.CONTACT -> ContactCard(state.dashboard.contactName) {
                        dial(context, state.dashboard.contactPhone)
                    }
                    HomeModule.DEVICES -> HomeDevicesCard(state)
                }
            }
        }
    }
}

@Composable
private fun HomeAssistantPanel(state: UiState, vm: MainViewModel, onAssistant: () -> Unit) {
    val context = LocalContext.current
    var input by remember { mutableStateOf("") }
    val recentMessages = state.assistantMessages.takeLast(2)
    val compactLayout = LocalConfiguration.current.screenWidthDp < 380
    val voiceLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
            ?.firstOrNull()
            ?.let { input = it }
    }
    val audioPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) {
            vm.toggleVoiceInput { input = it }
        } else {
            Toast.makeText(context, "请允许使用麦克风后再试", Toast.LENGTH_LONG).show()
        }
    }
    Card(
        shape = RoundedCornerShape(28.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFF2F6F62)),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(if (compactLayout) 16.dp else 20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                RoundIcon(Icons.Rounded.AutoAwesome, Color.White, Color.White.copy(alpha = .16f))
                Spacer(Modifier.width(if (compactLayout) 8.dp else 12.dp))
                Text(
                    "和小安聊一聊",
                    color = Color.White,
                    fontSize = if (compactLayout) 20.sp else 24.sp,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    softWrap = false,
                    modifier = Modifier.weight(1f),
                )
                Spacer(Modifier.width(6.dp))
                TextButton(
                    onClick = onAssistant,
                    colors = ButtonDefaults.textButtonColors(
                        containerColor = Color.White.copy(alpha = .18f),
                        contentColor = Color.White,
                    ),
                    contentPadding = PaddingValues(horizontal = 10.dp, vertical = 6.dp),
                ) {
                    Text("完整对话", fontSize = if (compactLayout) 14.sp else 15.sp, maxLines = 1)
                }
            }
            Text(
                "可以说说今天的感受，也可以问睡眠和居家安全",
                color = Color.White.copy(.82f),
                fontSize = 15.sp,
                lineHeight = 22.sp,
            )
            if (recentMessages.isEmpty()) {
                Surface(color = Color.White.copy(alpha = .12f), shape = RoundedCornerShape(18.dp)) {
                    Text(
                        "您好，我是小安。今天身体和心情怎么样？",
                        color = Color.White,
                        fontSize = 18.sp,
                        lineHeight = 27.sp,
                        modifier = Modifier.padding(16.dp),
                    )
                }
            } else {
                recentMessages.forEach { message ->
                    Surface(
                        color = if (message.role == "user") Color.White.copy(alpha = .14f) else Color.White,
                        contentColor = if (message.role == "user") Color.White else Ink,
                        shape = RoundedCornerShape(18.dp),
                        modifier = Modifier.fillMaxWidth(if (message.role == "user") .88f else 1f)
                            .align(if (message.role == "user") Alignment.End else Alignment.Start),
                    ) {
                        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
                            Text(elderFacingPlainText(message.content), fontSize = 17.sp, lineHeight = 25.sp)
                            if (message.role != "user") {
                                message.actions.filter { it.status == "pending" }.forEach { action ->
                                    Button(
                                        onClick = { vm.confirmAssistantAction(action.id) },
                                        modifier = Modifier.fillMaxWidth(),
                                        shape = RoundedCornerShape(14.dp),
                                    ) { Text(action.label, fontSize = 16.sp) }
                                }
                            }
                        }
                    }
                }
            }
            if (state.assistantLoading) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.size(20.dp), color = Color.White, strokeWidth = 2.dp)
                    Spacer(Modifier.width(8.dp))
                    Text("小安正在想…", color = Color.White.copy(.85f))
                }
            }
            state.assistantError?.let { Text(it, color = Color(0xFFFFD7D0), fontSize = 14.sp) }
            if (
                state.whiteNoisePlaying || state.whiteNoisePaused || state.whiteNoiseLoading ||
                    state.whiteNoiseError != null
            ) {
                WhiteNoisePlayerCard(state, vm)
            }
            ResponsiveAssistantComposer(
                    value = input,
                    onValueChange = { input = it },
                    onVoice = {
                        if (state.voiceRecording) {
                            vm.toggleVoiceInput { input = it }
                        } else {
                            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                                putExtra(RecognizerIntent.EXTRA_LANGUAGE, "zh-CN")
                                putExtra(RecognizerIntent.EXTRA_PROMPT, "请说出您想和小安聊的内容")
                            }
                            if (intent.resolveActivity(context.packageManager) != null) {
                                voiceLauncher.launch(intent)
                            } else if (
                                ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
                                PackageManager.PERMISSION_GRANTED
                            ) {
                                vm.toggleVoiceInput { input = it }
                            } else {
                                audioPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                            }
                        }
                    },
                    onSend = {
                        vm.sendAssistantMessage(input)
                        input = ""
                    },
                    sendEnabled = input.isNotBlank() && !state.assistantLoading,
                    voiceRecording = state.voiceRecording,
                    voiceTranscribing = state.voiceTranscribing,
                    onDarkBackground = true,
            )
            state.voiceError?.let {
                Text(it, color = Color(0xFFFFD7D0), fontSize = 14.sp, lineHeight = 20.sp)
            }
        }
    }
}

@Composable
private fun HomeDevicesCard(state: UiState) {
    Card(shape = RoundedCornerShape(26.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("设备状态", fontSize = 21.sp, fontWeight = FontWeight.Bold)
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
}

@Composable
private fun ProactiveCareCard(event: ProactiveEvent, onClick: () -> Unit) {
    Card(
        onClick = onClick,
        shape = RoundedCornerShape(26.dp),
        colors = CardDefaults.cardColors(containerColor = WarmSoft),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(21.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                RoundIcon(Icons.Rounded.AutoAwesome, Warm, Color.White)
                Spacer(Modifier.width(13.dp))
                Column(Modifier.weight(1f)) {
                    Text("小安主动关怀", color = Color(0xFF8B5A16), fontSize = 15.sp)
                    Text(event.title, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                }
                Icon(Icons.Rounded.ChevronRight, "回应小安")
            }
            Text(event.message, fontSize = 17.sp, lineHeight = 25.sp, maxLines = 3)
            Text("为什么询问：${event.reason}", color = Muted, fontSize = 13.sp, lineHeight = 19.sp)
        }
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
        val compactLayout = LocalConfiguration.current.screenWidthDp < 380
        if (compactLayout) {
            Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    RoundIcon(Icons.Rounded.FamilyRestroom, Color(0xFFE56F5B), Color(0xFFFFE9E4))
                    Spacer(Modifier.width(14.dp))
                    Column(Modifier.weight(1f)) {
                        Text("需要陪伴或帮忙？", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                        Text("告诉${name}联系您", color = Muted)
                    }
                }
                Button(onClick = onClick, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(16.dp)) {
                    Text("联系${name}", fontSize = 17.sp)
                }
            }
        } else {
            Row(Modifier.fillMaxWidth().padding(20.dp), verticalAlignment = Alignment.CenterVertically) {
                RoundIcon(Icons.Rounded.FamilyRestroom, Color(0xFFE56F5B), Color(0xFFFFE9E4))
                Spacer(Modifier.width(14.dp))
                Column(Modifier.weight(1f)) {
                    Text("需要陪伴或帮忙？", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    Text("告诉${name}联系您", color = Muted)
                }
                Button(onClick = onClick, shape = RoundedCornerShape(16.dp)) { Text("联系", fontSize = 17.sp) }
            }
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
    val resultColor = safetyRiskBackground(result?.riskLevel)
    Card(shape = RoundedCornerShape(26.dp), colors = CardDefaults.cardColors(containerColor = resultColor)) {
        Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(11.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                RoundIcon(
                    Icons.Rounded.Search,
                    safetyRiskForeground(result?.riskLevel),
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
                val statusColor = safetyRiskForeground(it.riskLevel)
                Surface(color = statusColor.copy(alpha = .12f), shape = RoundedCornerShape(50)) {
                    Text(
                        safetyRiskLabel(it.riskLevel),
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
            NightAwakeningCard(
                sleep.nightAwakening,
                state.nightAwakeningExpanded,
                vm::toggleNightAwakeningExpanded,
            )
        } else {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(28.dp),
                colors = CardDefaults.cardColors(containerColor = Color(0xFF303B73)),
            ) {
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
                        Text("萤石参考分 ${formatOne(it)}", color = Color.White, fontSize = 18.sp)
                    }
                }
            }
            RecentSleepTrendCard(state.sleepHistory)
            BoxWithConstraints(Modifier.fillMaxWidth()) {
                if (maxWidth < 350.dp) {
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        VitalCard(Modifier.fillMaxWidth(), Icons.Rounded.Air, "平均呼吸", sleep.respiratoryRate?.let { formatOne(it) } ?: "—", "次/分")
                        VitalCard(Modifier.fillMaxWidth(), Icons.Rounded.Favorite, "平均心率", sleep.heartRate?.let { formatOne(it) } ?: "—", "次/分")
                    }
                } else {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        VitalCard(Modifier.weight(1f), Icons.Rounded.Air, "平均呼吸", sleep.respiratoryRate?.let { formatOne(it) } ?: "—", "次/分")
                        VitalCard(Modifier.weight(1f), Icons.Rounded.Favorite, "平均心率", sleep.heartRate?.let { formatOne(it) } ?: "—", "次/分")
                    }
                }
            }
            VitalCard(Modifier.fillMaxWidth(), Icons.Rounded.DirectionsWalk, "夜间离床", sleep.bedExitCount?.toString() ?: "—", "次")
            sleep.baselineMessage?.let { message ->
                Card(
                    shape = RoundedCornerShape(22.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = if (sleep.baselineState == "changed") Color(0xFFFFF1E5) else BrandSoft,
                    ),
                ) {
                    Column(Modifier.padding(19.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Rounded.Timeline, null, tint = Brand)
                            Spacer(Modifier.width(8.dp))
                            Text("与个人平时相比", fontSize = 19.sp, fontWeight = FontWeight.Bold)
                        }
                        Text(message, fontSize = 17.sp, lineHeight = 26.sp)
                        sleep.baselineMetrics.forEach { metric ->
                            BaselineMetricRow(metric)
                        }
                        if (sleep.baselineState == "baseline_building") {
                            Text("已积累 ${sleep.baselineNights} 晚有效基线记录", color = Muted, fontSize = 15.sp)
                        }
                    }
                }
            }
            NightAwakeningCard(
                sleep.nightAwakening,
                state.nightAwakeningExpanded,
                vm::toggleNightAwakeningExpanded,
            )
            SleepStagesCard(sleep)
            sleep.analysis?.let {
                Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = BrandSoft)) {
                    Column(Modifier.padding(19.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) { Icon(Icons.Rounded.AutoAwesome, null, tint = Brand); Spacer(Modifier.width(8.dp)); Text("昨晚小结", fontSize = 19.sp, fontWeight = FontWeight.Bold) }
                        Text(it, fontSize = 17.sp, lineHeight = 26.sp)
                    }
                }
            }
            OutlinedButton(
                onClick = vm::syncSleep,
                enabled = !state.sleepActionLoading,
                modifier = Modifier.fillMaxWidth().height(50.dp),
                shape = RoundedCornerShape(15.dp),
            ) {
                if (state.sleepActionLoading) {
                    CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(8.dp))
                }
                Text("重新同步昨晚数据", fontSize = 17.sp)
            }
            sleep.syncMessage?.let { Text("同步状态：$it", color = Muted, fontSize = 14.sp) }
            Text("报告用于了解近期睡眠变化，不代替医疗判断。身体不舒服时，请及时联系家人或医生。", color = Muted, lineHeight = 24.sp)
        }
        SettingsSwitch("暂停睡眠提醒", "睡眠数据仍会保留", state.sleepPaused, vm::setSleepPaused)
    }
}

@Composable
private fun NightAwakeningCard(
    awakening: NightAwakening,
    expanded: Boolean,
    onToggle: () -> Unit,
) {
    val attentionColor = when {
        awakening.state == "resolved" -> Brand
        awakening.attention == "extra_care" -> Color(0xFFB45309)
        awakening.attention == "insufficient" -> Muted
        else -> Brand
    }
    val attentionText = awakening.attentionText()
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onToggle),
        shape = RoundedCornerShape(22.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (awakening.attention == "extra_care") WarmSoft else Color.White,
        ),
    ) {
        Column(Modifier.padding(19.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Rounded.Bedtime, null, tint = attentionColor)
                Spacer(Modifier.width(8.dp))
                Column(Modifier.weight(1f)) {
                    Text("起夜关注", fontSize = 19.sp, fontWeight = FontWeight.Bold)
                    Text(attentionText, color = attentionColor, fontWeight = FontWeight.SemiBold)
                }
                Icon(
                    if (expanded) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore,
                    if (expanded) "收起" else "展开",
                    tint = Muted,
                )
            }
            Text(awakening.message, fontSize = 16.sp, lineHeight = 24.sp)
            awakening.detectedAt?.let {
                Text("最近监测：${shortDateTime(it)}", color = Muted, fontSize = 14.sp)
            }
            if (expanded) {
                HorizontalDivider(color = Color(0xFFE4E8E5))
                Text("监测到的情况", fontSize = 17.sp, fontWeight = FontWeight.Bold)
                Text(
                    when {
                        awakening.state == "active" -> "监测到离床，本次关注仍在进行中。"
                        awakening.state == "resolved" -> "本次离床关注已经结束。"
                        awakening.eventInterfaceStatus == "pending_verification" ->
                            "尚未监测到可靠离床事件；萤石离床事件接口仍待真实非空数据验证。"
                        else -> "尚未监测到离床事件。"
                    },
                    color = Muted,
                    lineHeight = 23.sp,
                )
                if (awakening.reasons.isNotEmpty()) {
                    Text("为什么提醒", fontSize = 17.sp, fontWeight = FontWeight.Bold)
                    awakening.reasons.forEach { NightAwakeningReasonRow(it) }
                }
                if (awakening.guidance.isNotEmpty()) {
                    Text("现在可以这样做", fontSize = 17.sp, fontWeight = FontWeight.Bold)
                    awakening.guidance.forEach { item ->
                        Row(Modifier.fillMaxWidth()) {
                            Text("•", color = Brand, fontWeight = FontWeight.Bold)
                            Spacer(Modifier.width(8.dp))
                            Text(item, fontSize = 16.sp, lineHeight = 23.sp)
                        }
                    }
                }
            }
            Text(awakening.disclaimer, color = Muted, fontSize = 13.sp, lineHeight = 19.sp)
        }
    }
}

@Composable
private fun NightAwakeningReasonRow(reason: NightAwakeningReason) {
    val unit = if (reason.metric == "duration_minutes") "分钟" else "次/分"
    val comparison = if (reason.comparisonStatus == "not_comparable") {
        "本次睡眠段尚未结束，时长暂不比较"
    } else if (reason.current == null || reason.baselineMedian == null) {
        "数据不足"
    } else {
        "本次 ${formatOne(reason.current)} · 平时 ${formatOne(reason.baselineMedian)} $unit"
    }
    val difference = reason.difference?.let {
        val prefix = if (it > 0) "+" else ""
        "$prefix${formatOne(it)} $unit"
    }
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(reason.label.ifBlank { reason.metric }, fontWeight = FontWeight.SemiBold)
            Text(comparison, color = Muted, fontSize = 14.sp)
        }
        difference?.let {
            Text(
                it,
                color = if (reason.adverseChange) Color(0xFFB45309) else Brand,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

@Composable
private fun BaselineMetricRow(metric: BaselineMetric) {
    val unit = if (metric.label == "睡眠时长") "分钟" else "次/分"
    val current = metric.current?.let(::formatOne) ?: "—"
    val baseline = metric.baselineMedian?.let(::formatOne) ?: "—"
    val difference = metric.difference?.let {
        val prefix = if (it > 0) "+" else ""
        "$prefix${formatOne(it)} $unit"
    } ?: "数据不足"
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(metric.label, fontWeight = FontWeight.SemiBold)
            Text("昨晚 $current · 平时 $baseline $unit", color = Muted, fontSize = 14.sp)
        }
        Text(
            difference,
            color = if (metric.status == "changed") Color(0xFFB45309) else Brand,
            fontWeight = FontWeight.SemiBold,
        )
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
private fun MePage(state: UiState, vm: MainViewModel, onStartOnboarding: () -> Unit) {
    var url by remember(vm.backendUrl) { mutableStateOf(vm.backendUrl) }
    var contactName by remember(state.dashboard.contactName) { mutableStateOf(state.dashboard.contactName) }
    var contactPhone by remember(state.dashboard.contactPhone) { mutableStateOf(state.dashboard.contactPhone) }
    var feedback by remember { mutableStateOf("") }
    val guidedFactTypes = setOf(
        "living_arrangement",
        "health_management_status",
        "reminder_detail_preference",
        "interaction_mode_preference",
        "sharing_preference",
    )
    val guidedFactCount = state.profileFacts.map { it.factType }.toSet().intersect(guidedFactTypes).size
    val guidedProfileComplete = guidedFactCount == guidedFactTypes.size
    PageBody {
        PageTitle("我的画像", "您可以查看和管理小安了解的内容", Icons.Rounded.Person)
        Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = BrandSoft)) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    RoundIcon(Icons.Rounded.Badge, Brand, Color.White)
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text("让小安更了解您", fontSize = 21.sp, fontWeight = FontWeight.Bold)
                        Text(
                            if (guidedProfileComplete) "基础画像已保存。再次进入可查看记录或只修改一项。"
                            else "通过五个简单选择填写基础情况，任何一项都可以暂不填写。",
                            color = Muted,
                            lineHeight = 23.sp,
                        )
                    }
                }
                Button(
                    onClick = onStartOnboarding,
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                    shape = RoundedCornerShape(16.dp),
                ) {
                    Icon(Icons.Rounded.Chat, null)
                    Spacer(Modifier.width(8.dp))
                    Text(
                        when {
                            guidedProfileComplete -> "查看或修改"
                            guidedFactCount > 0 -> "继续填写"
                            else -> "开始填写"
                        },
                        fontSize = 17.sp,
                    )
                }
            }
        }
        Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("家庭服务连接", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Text("手机和家中电脑需连接同一个网络", color = Muted)
                OutlinedTextField(value = url, onValueChange = { url = it }, label = { Text("服务地址") }, placeholder = { Text("http://192.168.1.10:8000") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Button(onClick = { vm.saveBackend(url) }, modifier = Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(15.dp)) { Text("保存并连接", fontSize = 17.sp) }
            }
        }
        Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("小安记得的情况", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Text("引导填写和日常对话中记住的内容都会显示在这里。", color = Muted)
                if (state.profileFacts.isEmpty()) {
                    Text("暂时没有已确认的内容", color = Muted)
                } else {
                    state.profileFacts.forEach { fact ->
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Rounded.CheckCircle, null, tint = Brand)
                            Spacer(Modifier.width(9.dp))
                            Column(Modifier.weight(1f)) {
                                Text(fact.displayText, fontSize = 17.sp)
                                Text(
                                    when {
                                        fact.source == "guided_onboarding" -> "由您在画像引导中选择"
                                        fact.status == "inferred" -> "小安从日常对话中推测"
                                        fact.source.startsWith("conversation_") -> "由您在日常对话中确认"
                                        else -> "由您填写"
                                    },
                                    color = Muted,
                                    fontSize = 13.sp,
                                )
                            }
                            TextButton(onClick = { vm.deleteProfileFact(fact.id) }) { Text("删除") }
                        }
                    }
                }
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

    }
}

@Composable
private fun PrivacyPage(state: UiState, vm: MainViewModel) {
    PageBody {
        PageTitle("隐私设置", "由您决定小安能知道什么、控制什么", Icons.Rounded.PrivacyTip)
        state.notice?.let { NoticeBanner(it) }
        state.error?.let { ConnectionBanner(it) }

        Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = BrandSoft)) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(13.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    RoundIcon(Icons.Rounded.AutoAwesome, Brand, Color.White)
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text("我是小安，我是您的居家小助手", fontSize = 21.sp, fontWeight = FontWeight.Bold)
                    }
                }
                Text("目前可控制：通道检查、睡眠提醒和主动关怀。新增设备接入后也会在这里说明。", fontSize = 15.sp, lineHeight = 23.sp)
            }
        }

        Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(13.dp)) {
                Text("设备控制权限", fontSize = 21.sp, fontWeight = FontWeight.Bold)
                Text("只需选择一次，让小安控制您家里的设备；您可以随时修改或撤回。", color = Muted, lineHeight = 23.sp)
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    ChoiceButton(
                        "允许控制",
                        state.assistantDeviceControlConsent == "allowed",
                        Modifier.weight(1f),
                    ) { vm.setDeviceControlConsent("allowed") }
                    ChoiceButton(
                        "不允许",
                        state.assistantDeviceControlConsent == "denied",
                        Modifier.weight(1f),
                    ) { vm.setDeviceControlConsent("denied") }
                }
                if (state.assistantDeviceControlConsent == "unset") {
                    Text("尚未选择。首次通过对话控制设备时，小安会提供以上两个选项。", color = Color(0xFF8B5A16), fontSize = 14.sp)
                }
            }
        }

        Text("数据与关怀", fontSize = 21.sp, fontWeight = FontWeight.Bold)
        SettingsSwitch(
            "心理健康主动关怀",
            if (state.psychologicalCareEnabled) "结合睡眠和日常对话发现值得关心的变化" else "当前不会生成心理健康主动关怀",
            state.psychologicalCareEnabled,
            vm::setPsychologicalCareEnabled,
        )
        SettingsSwitch(
            "主动发起对话",
            if (state.proactiveCarePaused) "当前已暂停普通主动关怀" else "当前已开启，每天最多主动关怀2次",
            !state.proactiveCarePaused,
        ) { vm.setProactiveCarePaused(!it) }
        SettingsSwitch(
            "通道检查",
            if (state.cameraPaused) "当前已暂停摄像头通道分析" else "当前已开启",
            !state.cameraPaused,
        ) { vm.setCameraPaused(!it) }
        SettingsSwitch(
            "睡眠提醒",
            if (state.sleepPaused) "当前已暂停" else "当前已开启",
            !state.sleepPaused,
        ) { vm.setSleepPaused(!it) }

        /*Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("风险证据保存时间", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Text("用于解释为什么产生安全提醒，到期后按服务清理规则删除。", color = Muted)
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(1, 7, 30).forEach { days ->
                        ChoiceButton(
                            "${days}天",
                            state.evidenceRetentionDays == days,
                            Modifier.weight(1f),
                        ) { vm.setEvidenceRetentionDays(days) }
                    }
                }
            }
        }*/
    }
}

@Composable
private fun ChoiceButton(
    text: String,
    selected: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    if (selected) {
        Button(onClick = onClick, modifier = modifier.height(50.dp), shape = RoundedCornerShape(15.dp)) {
            Icon(Icons.Rounded.Check, null)
            Spacer(Modifier.width(6.dp))
            Text(text)
        }
    } else {
        OutlinedButton(onClick = onClick, modifier = modifier.height(50.dp), shape = RoundedCornerShape(15.dp)) {
            Text(text)
        }
    }
}

@Composable
internal fun ResponsiveAssistantComposer(
    value: String,
    onValueChange: (String) -> Unit,
    onVoice: () -> Unit,
    onSend: () -> Unit,
    sendEnabled: Boolean,
    voiceRecording: Boolean = false,
    voiceTranscribing: Boolean = false,
    onDarkBackground: Boolean = false,
    modifier: Modifier = Modifier,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        placeholder = {
            Text(
                when {
                    voiceRecording -> "正在录音，再点一次完成"
                    voiceTranscribing -> "正在识别您说的话…"
                    else -> "和小安说点什么"
                },
                maxLines = 1,
            )
        },
        modifier = modifier.fillMaxWidth(),
        minLines = 1,
        maxLines = 3,
        shape = RoundedCornerShape(20.dp),
        leadingIcon = {
            IconButton(
                onClick = onVoice,
                enabled = !voiceTranscribing,
                modifier = Modifier.size(48.dp),
            ) {
                if (voiceTranscribing) {
                    CircularProgressIndicator(Modifier.size(23.dp), color = Brand, strokeWidth = 2.dp)
                } else {
                    Icon(
                        if (voiceRecording) Icons.Rounded.Stop else Icons.Rounded.Mic,
                        if (voiceRecording) "结束录音" else "语音输入",
                        tint = if (voiceRecording) Color(0xFFC73A31) else Brand,
                        modifier = Modifier.size(27.dp),
                    )
                }
            }
        },
        trailingIcon = {
            FilledIconButton(
                onClick = onSend,
                enabled = sendEnabled,
                modifier = Modifier.size(44.dp),
                colors = IconButtonDefaults.filledIconButtonColors(
                    containerColor = if (onDarkBackground) Warm else Brand,
                    contentColor = Color.White,
                ),
            ) { Icon(Icons.Rounded.Send, "发送") }
        },
        colors = if (onDarkBackground) {
            OutlinedTextFieldDefaults.colors(
                focusedContainerColor = Color.White,
                unfocusedContainerColor = Color.White,
                focusedBorderColor = Color.White,
                unfocusedBorderColor = Color.White,
            )
        } else {
            OutlinedTextFieldDefaults.colors()
        },
    )
}

@Composable private fun PageTitle(title: String, subtitle: String, icon: ImageVector) { Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) { RoundIcon(icon, Brand); Spacer(Modifier.width(14.dp)); Column(Modifier.weight(1f)) { Text(title, fontSize = 29.sp, fontWeight = FontWeight.Bold); Text(subtitle, color = Muted, fontSize = 16.sp, lineHeight = 22.sp) } } }
@Composable private fun RoundIcon(icon: ImageVector, color: Color, background: Color = Color.White) { Box(Modifier.size(52.dp).clip(CircleShape).background(background), contentAlignment = Alignment.Center) { Icon(icon, null, tint = color, modifier = Modifier.size(28.dp)) } }
@Composable private fun VitalMini(label: String, value: String) { Column { Text(label, color = Muted, fontSize = 14.sp); Text(value, fontWeight = FontWeight.SemiBold, fontSize = 16.sp) } }
@Composable private fun VitalCard(modifier: Modifier, icon: ImageVector, label: String, value: String, unit: String) { Card(modifier, shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) { Column(Modifier.padding(19.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) { Icon(icon, null, tint = Brand); Text(label, color = Muted); Row(verticalAlignment = Alignment.Bottom) { Text(value, fontSize = 29.sp, fontWeight = FontWeight.Bold); Spacer(Modifier.width(4.dp)); Text(unit, color = Muted, modifier = Modifier.padding(bottom = 4.dp)) } } } }
@Composable private fun EmptyCard(icon: ImageVector, title: String, detail: String) { Card(shape = RoundedCornerShape(26.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) { Column(Modifier.fillMaxWidth().padding(26.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) { RoundIcon(icon, Brand, BrandSoft); Text(title, fontSize = 22.sp, fontWeight = FontWeight.Bold); Text(detail, color = Muted, lineHeight = 25.sp) } } }
@Composable private fun DeviceRow(icon: ImageVector, title: String, status: String) { Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) { Row(Modifier.fillMaxWidth().padding(17.dp), verticalAlignment = Alignment.CenterVertically) { Icon(icon, null, tint = Brand, modifier = Modifier.size(28.dp)); Spacer(Modifier.width(14.dp)); Text(title, Modifier.weight(1f), fontSize = 18.sp, fontWeight = FontWeight.SemiBold); Text(status, color = Muted) } } }
@Composable private fun SettingsSwitch(title: String, detail: String, checked: Boolean, onChecked: (Boolean) -> Unit) { Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) { Row(Modifier.fillMaxWidth().padding(18.dp), verticalAlignment = Alignment.CenterVertically) { Column(Modifier.weight(1f)) { Text(title, fontSize = 18.sp, fontWeight = FontWeight.SemiBold); Text(detail, color = Muted) }; Switch(checked, onChecked, colors = SwitchDefaults.colors(checkedTrackColor = Brand)) } } }
@Composable private fun ConnectionBanner(text: String) { val message = if (text.contains(Regex("https?://|(?:\\d{1,3}\\.){3}\\d{1,3}"))) "家庭服务暂时未连接，请稍后重试" else text; Surface(color = Color(0xFFFFE5E1), shape = RoundedCornerShape(16.dp)) { Row(Modifier.fillMaxWidth().padding(15.dp), verticalAlignment = Alignment.CenterVertically) { Icon(Icons.Rounded.WifiOff, null, tint = Color(0xFFB44336)); Spacer(Modifier.width(10.dp)); Text(message, color = Color(0xFF7D2E25), modifier = Modifier.weight(1f), lineHeight = 23.sp) } } }
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
