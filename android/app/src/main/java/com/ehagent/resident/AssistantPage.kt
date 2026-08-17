package com.ehagent.resident

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.speech.RecognizerIntent
import android.speech.tts.TextToSpeech
import android.widget.Toast
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ArrowBack
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.GraphicEq
import androidx.compose.material.icons.rounded.Mic
import androidx.compose.material.icons.rounded.OpenInNew
import androidx.compose.material.icons.rounded.Send
import androidx.compose.material.icons.rounded.VolumeUp
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.Locale

private val quickQuestions = listOf(
    "昨晚睡得怎么样？",
    "今天适合出门吗？",
    "这个电话像诈骗吗？",
    "帮我联系家人",
)

@Composable
internal fun AssistantPage(state: UiState, vm: MainViewModel, onBack: () -> Unit) {
    val context = LocalContext.current
    val listState = rememberLazyListState()
    var input by remember { mutableStateOf("") }
    var speechReady by remember { mutableStateOf(false) }
    val speaker = remember {
        TextToSpeech(context) { status -> speechReady = status == TextToSpeech.SUCCESS }
    }
    LaunchedEffect(speechReady) {
        if (speechReady) speaker.language = Locale.SIMPLIFIED_CHINESE
    }
    DisposableEffect(speaker) { onDispose { speaker.shutdown() } }
    val voiceLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        val words = result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
        words?.firstOrNull()?.let { input = it }
    }

    BackHandler(onBack = onBack)
    LaunchedEffect(Unit) { vm.loadAssistantConversation() }
    LaunchedEffect(state.assistantMessages.size, state.assistantLoading) {
        val count = state.assistantMessages.size + if (state.assistantLoading) 1 else 0
        if (count > 0) listState.animateScrollToItem(count - 1)
    }

    Column(Modifier.fillMaxSize()) {
        Surface(color = Color.White, shadowElevation = 2.dp) {
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(onClick = onBack) { Icon(Icons.Rounded.ArrowBack, "返回") }
                Surface(color = BrandSoft, shape = RoundedCornerShape(16.dp)) {
                    Icon(
                        Icons.Rounded.AutoAwesome,
                        null,
                        tint = Brand,
                        modifier = Modifier.padding(9.dp).size(25.dp),
                    )
                }
                Spacer(Modifier.width(11.dp))
                Column {
                    Text("小安", fontSize = 23.sp, fontWeight = FontWeight.Bold)
                    Text("您的生活助手", color = Muted, fontSize = 14.sp)
                }
            }
        }

        LazyColumn(
            state = listState,
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(13.dp),
        ) {
            if (state.assistantMessages.isEmpty()) {
                item { AssistantWelcome(onQuestion = vm::sendAssistantMessage) }
            }
            items(state.assistantMessages, key = { it.id }) { message ->
                AssistantBubble(
                    message = message,
                    onSpeak = {
                        if (speechReady) {
                            speaker.speak(
                                message.content,
                                TextToSpeech.QUEUE_FLUSH,
                                null,
                                message.id,
                            )
                        }
                    },
                    onConfirm = vm::confirmAssistantAction,
                )
            }
            if (state.assistantLoading) {
                item {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(Modifier.size(22.dp), color = Brand, strokeWidth = 3.dp)
                        Spacer(Modifier.width(10.dp))
                        Text("小安正在想…", color = Muted, fontSize = 16.sp)
                    }
                }
            }
            state.assistantError?.let { error ->
                item {
                    Surface(color = Color(0xFFFFE5E1), shape = RoundedCornerShape(16.dp)) {
                        Text(error, color = Color(0xFF7D2E25), modifier = Modifier.padding(14.dp))
                    }
                }
            }
        }

        Surface(color = Color.White, shadowElevation = 5.dp) {
            Row(
                Modifier.fillMaxWidth().padding(12.dp),
                verticalAlignment = Alignment.Bottom,
            ) {
                IconButton(onClick = {
                    val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                        putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                        putExtra(RecognizerIntent.EXTRA_LANGUAGE, "zh-CN")
                        putExtra(RecognizerIntent.EXTRA_PROMPT, "请说出您想问的问题")
                    }
                    try {
                        voiceLauncher.launch(intent)
                    } catch (_: ActivityNotFoundException) {
                        Toast.makeText(context, "这部手机暂时无法使用语音输入", Toast.LENGTH_LONG).show()
                    }
                }) { Icon(Icons.Rounded.Mic, "语音输入", tint = Brand, modifier = Modifier.size(29.dp)) }
                OutlinedTextField(
                    value = input,
                    onValueChange = { input = it },
                    placeholder = { Text("和小安说点什么") },
                    modifier = Modifier.weight(1f),
                    maxLines = 4,
                    shape = RoundedCornerShape(20.dp),
                )
                Spacer(Modifier.width(8.dp))
                FilledIconButton(
                    onClick = {
                        vm.sendAssistantMessage(input)
                        input = ""
                    },
                    enabled = input.isNotBlank() && !state.assistantLoading,
                    modifier = Modifier.size(52.dp),
                ) { Icon(Icons.Rounded.Send, "发送") }
            }
        }
    }
}

@Composable
private fun AssistantWelcome(onQuestion: (String) -> Unit) {
    Card(
        shape = RoundedCornerShape(26.dp),
        colors = CardDefaults.cardColors(containerColor = BrandSoft),
    ) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(13.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Rounded.GraphicEq, null, tint = Brand, modifier = Modifier.size(31.dp))
                Spacer(Modifier.width(10.dp))
                Text("您好，我是小安", fontSize = 23.sp, fontWeight = FontWeight.Bold)
            }
            Text("您可以问生活问题，也可以问昨晚睡眠和家中安全情况。", fontSize = 17.sp)
            quickQuestions.forEach { question ->
                AssistChip(onClick = { onQuestion(question) }, label = {
                    Text(question, fontSize = 16.sp)
                })
            }
        }
    }
}

@Composable
private fun AssistantBubble(
    message: AssistantMessage,
    onSpeak: () -> Unit,
    onConfirm: (String) -> Unit,
) {
    val fromResident = message.role == "user"
    Column(
        Modifier.fillMaxWidth(),
        horizontalAlignment = if (fromResident) Alignment.End else Alignment.Start,
    ) {
        Surface(
            color = if (fromResident) Brand else Color.White,
            contentColor = if (fromResident) Color.White else Ink,
            shape = RoundedCornerShape(
                topStart = 22.dp,
                topEnd = 22.dp,
                bottomStart = if (fromResident) 22.dp else 5.dp,
                bottomEnd = if (fromResident) 5.dp else 22.dp,
            ),
            shadowElevation = if (fromResident) 0.dp else 1.dp,
            modifier = Modifier.fillMaxWidth(if (fromResident) .86f else .94f),
        ) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(message.content, fontSize = 18.sp, lineHeight = 28.sp)
                if (!fromResident && message.contextUsed.isNotEmpty()) {
                    Text(
                        "参考了：${message.contextUsed.joinToString("、")}",
                        color = Muted,
                        fontSize = 13.sp,
                    )
                }
                message.sources.forEach { source -> SourceLink(source) }
                message.actions.forEach { action ->
                    Button(
                        onClick = { onConfirm(action.id) },
                        enabled = action.status == "pending",
                        modifier = Modifier.fillMaxWidth().height(50.dp),
                        shape = RoundedCornerShape(15.dp),
                    ) {
                        Icon(
                            if (action.status == "completed") Icons.Rounded.Check else Icons.Rounded.Send,
                            null,
                        )
                        Spacer(Modifier.width(7.dp))
                        Text(if (action.status == "completed") "已通知家人" else action.label)
                    }
                }
            }
        }
        if (!fromResident) {
            IconButton(onClick = onSpeak) {
                Icon(Icons.Rounded.VolumeUp, "朗读回答", tint = Muted)
            }
        }
    }
}

@Composable
private fun SourceLink(source: AssistantSource) {
    val context = LocalContext.current
    Surface(color = Canvas, shape = RoundedCornerShape(13.dp)) {
        Row(
            Modifier.fillMaxWidth().padding(11.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                source.title,
                modifier = Modifier.weight(1f),
                color = Brand,
                fontSize = 14.sp,
                maxLines = 2,
            )
            IconButton(onClick = {
                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(source.url)))
            }) { Icon(Icons.Rounded.OpenInNew, "打开来源", tint = Brand) }
        }
    }
}
