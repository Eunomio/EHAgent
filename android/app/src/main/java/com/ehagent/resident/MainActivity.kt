package com.ehagent.resident

import android.os.Bundle
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle

private val Brand = Color(0xFF2E7D67)
private val BrandSoft = Color(0xFFE4F3ED)
private val Warm = Color(0xFFF4A340)
private val WarmSoft = Color(0xFFFFF0DC)
private val Ink = Color(0xFF202622)
private val Muted = Color(0xFF66706A)
private val Canvas = Color(0xFFF6F7F3)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
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
    HOME("首页", Icons.Rounded.Home), SAFETY("安全", Icons.Rounded.HealthAndSafety), SLEEP("睡眠", Icons.Rounded.Bedtime), ME("我的", Icons.Rounded.Person)
}

@Composable
private fun ResidentApp(viewModel: MainViewModel = androidx.lifecycle.viewmodel.compose.viewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var page by remember { mutableStateOf(Page.HOME) }
    Scaffold(
        containerColor = Canvas,
        bottomBar = {
            NavigationBar(containerColor = Color.White, tonalElevation = 3.dp) {
                Page.entries.forEach { item ->
                    NavigationBarItem(selected = page == item, onClick = { page = item }, icon = { Icon(item.icon, item.label) }, label = { Text(item.label, fontSize = 14.sp) }, colors = NavigationBarItemDefaults.colors(selectedIconColor = Brand, selectedTextColor = Brand, indicatorColor = BrandSoft))
                }
            }
        },
        snackbarHost = { SnackbarHost(remember { SnackbarHostState() }) }
    ) { padding ->
        Box(Modifier.padding(padding).fillMaxSize()) {
            when (page) {
                Page.HOME -> HomePage(state, viewModel, onSafety = { page = Page.SAFETY }, onSleep = { page = Page.SLEEP })
                Page.SAFETY -> SafetyPage(state, viewModel)
                Page.SLEEP -> SleepPage(state, viewModel)
                Page.ME -> MePage(state, viewModel)
            }
            if (state.loading) LinearProgressIndicator(Modifier.fillMaxWidth().align(Alignment.TopCenter), color = Brand)
        }
    }
}

@Composable
private fun PageBody(content: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 22.dp), verticalArrangement = Arrangement.spacedBy(16.dp), content = content)
}

@Composable
private fun HomePage(state: UiState, vm: MainViewModel, onSafety: () -> Unit, onSleep: () -> Unit) {
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
        SafetyHomeCard(state.dashboard.safety, onSafety)
        SleepHomeCard(state.dashboard.sleep, onSleep)
        ContactCard(state.dashboard.contactName) { dial(context, state.dashboard.contactPhone) }
        Text("设备状态", fontSize = 21.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 4.dp))
        DeviceRow(Icons.Rounded.Videocam, "通道摄像头", deviceText(state.devices.cameraConfigured, state.devices.cameraOnline))
        DeviceRow(Icons.Rounded.Bed, "无感睡眠助手", if (state.devices.sleepConfigured) "已连接" else "等待连接")
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
    PageBody {
        PageTitle("居家安全", "留意每天常走的地方", Icons.Rounded.HealthAndSafety)
        if (state.dashboard.safety.taskId == null) {
            EmptyCard(Icons.Rounded.CheckCircle, "当前没有待处理提醒", "摄像头完成检查后，结果会显示在这里。")
        } else {
            Card(shape = RoundedCornerShape(26.dp), colors = CardDefaults.cardColors(containerColor = WarmSoft)) {
                Column(Modifier.padding(22.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Text("请留意", color = Color(0xFF9A5B12), fontWeight = FontWeight.Bold)
                    Text(state.dashboard.safety.headline, fontSize = 26.sp, fontWeight = FontWeight.Bold)
                    Text(state.dashboard.safety.detail, fontSize = 18.sp, lineHeight = 28.sp)
                    Button(onClick = { vm.taskAction("done") }, modifier = Modifier.fillMaxWidth().height(54.dp), shape = RoundedCornerShape(16.dp)) { Icon(Icons.Rounded.Done, null); Spacer(Modifier.width(8.dp)); Text("我已整理好", fontSize = 18.sp) }
                    OutlinedButton(onClick = { vm.taskAction("need_help"); dial(context, state.dashboard.contactPhone) }, modifier = Modifier.fillMaxWidth().height(54.dp), shape = RoundedCornerShape(16.dp)) { Text("联系家人", fontSize = 18.sp) }
                    TextButton(onClick = { vm.taskAction("later") }, modifier = Modifier.align(Alignment.CenterHorizontally)) { Text("稍后提醒我") }
                }
            }
        }
        SettingsSwitch("暂停通道检查", "需要隐私时可以随时暂停", state.cameraPaused, vm::setCameraPaused)
    }
}

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
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                VitalCard(Modifier.weight(1f), Icons.Rounded.Air, "平均呼吸", sleep.respiratoryRate?.let { formatOne(it) } ?: "—", "次/分")
                VitalCard(Modifier.weight(1f), Icons.Rounded.Favorite, "平均心率", sleep.heartRate?.let { formatOne(it) } ?: "—", "次/分")
            }
            VitalCard(Modifier.fillMaxWidth(), Icons.Rounded.DirectionsWalk, "夜间离床", sleep.bedExitCount?.toString() ?: "—", "次")
            Text("数据来自床边设备的无感测量。身体不舒服时，请及时联系家人或医生。", color = Muted, lineHeight = 24.sp)
        }
        SettingsSwitch("暂停睡眠提醒", "睡眠数据仍会保留", state.sleepPaused, vm::setSleepPaused)
    }
}

@Composable
private fun MePage(state: UiState, vm: MainViewModel) {
    var url by remember(vm.backendUrl) { mutableStateOf(vm.backendUrl) }
    var contactName by remember(state.dashboard.contactName) { mutableStateOf(state.dashboard.contactName) }
    var contactPhone by remember(state.dashboard.contactPhone) { mutableStateOf(state.dashboard.contactPhone) }
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
private fun deviceText(configured: Boolean, online: Boolean?): String = when { !configured -> "等待连接"; online == true -> "在线"; online == false -> "离线"; else -> "已配置" }
private fun formatOne(value: Double): String = if (value % 1.0 == 0.0) value.toInt().toString() else String.format("%.1f", value)
private fun dial(context: android.content.Context, phone: String) {
    if (phone.isNotBlank()) {
        context.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:${Uri.encode(phone)}")))
    } else {
        Toast.makeText(context, "请先在“我的”中填写家人电话", Toast.LENGTH_LONG).show()
    }
}
