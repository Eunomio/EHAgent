package com.ehagent.resident

import android.content.Context
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.widget.VideoView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Done
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Videocam
import androidx.compose.material.icons.rounded.VolumeUp
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import java.io.ByteArrayOutputStream
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
internal fun EmbeddedSafetyFlow(vm: MainViewModel) {
    var stage by remember { mutableIntStateOf(0) }
    var playbackRound by remember { mutableIntStateOf(0) }
    var result by remember { mutableStateOf<SafetyAnalysis?>(null) }
    var checking by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var advancing by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val videos = listOf(
        R.raw.safety_many_toys,
        R.raw.safety_cleanup,
        R.raw.safety_one_car,
        R.raw.safety_clear,
    )

    fun analyzeCurrentFrame() {
        if (!checking) return
        scope.launch {
            runCatching { extractWalkwayFrame(context, videos[stage]) }
                .onSuccess { image ->
                    vm.analyzeSafetyFrame(
                        image = image,
                        preview = true,
                        onSuccess = {
                            result = it
                            checking = false
                            error = null
                        },
                        onFailure = {
                            checking = false
                            error = it
                        },
                    )
                }
                .onFailure {
                    checking = false
                    error = "当前画面暂时无法检查，请再试一次"
                }
        }
    }

    fun showNextPicture() {
        result = null
        error = null
        checking = true
        advancing = false
        if (stage < videos.lastIndex) stage += 1 else playbackRound += 1
    }

    val needsCleanup = result?.riskLevel in setOf("medium", "high")
    val resultColor = when (result?.riskLevel) {
        "medium", "high" -> Color(0xFFC73A31)
        "insufficient" -> Color(0xFFC47B22)
        else -> Brand
    }
    val resultBackground = when (result?.riskLevel) {
        "medium", "high" -> Color(0xFFFFE6E3)
        "insufficient" -> Color(0xFFFFF1DA)
        else -> BrandSoft
    }

    Card(shape = RoundedCornerShape(26.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                EmbeddedRoundIcon(Icons.Rounded.Videocam, Brand, BrandSoft)
                Spacer(Modifier.width(13.dp))
                Column(Modifier.weight(1f)) {
                    Text("通道实时画面", fontSize = 21.sp, fontWeight = FontWeight.Bold)
                    Text(
                        if (stage == 0) "画面持续无人，正在自动检查通道" else "通道画面发生变化，正在自动复查",
                        color = Muted,
                    )
                }
            }
            key(stage, playbackRound) {
                AndroidView(
                    factory = {
                        VideoView(it).apply {
                            setOnPreparedListener { player ->
                                player.isLooping = false
                                player.setVolume(0f, 0f)
                                start()
                            }
                            setOnCompletionListener { analyzeCurrentFrame() }
                            setVideoURI(Uri.parse("android.resource://${context.packageName}/${videos[stage]}"))
                        }
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .aspectRatio(16f / 9f)
                        .clip(RoundedCornerShape(18.dp))
                        .background(Color.Black),
                )
            }
        }
    }

    Card(
        shape = RoundedCornerShape(26.dp),
        colors = CardDefaults.cardColors(containerColor = resultBackground),
    ) {
        Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(11.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                EmbeddedRoundIcon(Icons.Rounded.Search, resultColor)
                Spacer(Modifier.width(13.dp))
                Column(Modifier.weight(1f)) {
                    Text("检查当前通道", fontSize = 21.sp, fontWeight = FontWeight.Bold)
                    Text(
                        if (checking) "正在识别通道内的物品" else "自动监测中，画面变化后会再次检查",
                        color = Muted,
                    )
                }
            }
            if (checking) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(9.dp))
                    Text(if (stage == 0) "正在自动检查…" else "正在自动复查…")
                }
            }
            error?.let { message ->
                HorizontalDivider(color = Ink.copy(alpha = .08f))
                Text(message, color = Color(0xFFC73A31), fontSize = 17.sp)
                TextButton(
                    onClick = {
                        error = null
                        checking = true
                        playbackRound += 1
                    },
                ) {
                    Icon(Icons.Rounded.Refresh, null)
                    Spacer(Modifier.width(6.dp))
                    Text("重新检查")
                }
            }
            result?.let { current ->
                HorizontalDivider(color = Ink.copy(alpha = .08f))
                Surface(color = resultColor.copy(alpha = .12f), shape = RoundedCornerShape(50)) {
                    Text(
                        when (current.riskLevel) {
                            "medium", "high" -> "需要整理"
                            "insufficient" -> "画面不清楚"
                            "low" -> "注意观察"
                            else -> "通道安全"
                        },
                        color = resultColor,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 5.dp),
                    )
                }
                Text(current.headline, fontSize = 23.sp, fontWeight = FontWeight.Bold)
                Text(current.reason, fontSize = 17.sp, lineHeight = 25.sp)
                Text(current.actionText, color = resultColor, fontWeight = FontWeight.SemiBold)
                if (needsCleanup && current.speechUrl != null) {
                    TextButton(onClick = vm::replaySafetySpeech) {
                        Icon(Icons.Rounded.VolumeUp, null)
                        Spacer(Modifier.width(6.dp))
                        Text("播放语音提醒")
                    }
                }
            }
        }
    }

    result?.let { current ->
        if (needsCleanup) {
            Card(shape = RoundedCornerShape(26.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFFFFE6E3))) {
                Column(Modifier.padding(22.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Text(if (stage == 0) "请留意" else "复查结果", color = Color(0xFFC73A31), fontWeight = FontWeight.Bold)
                    Text(current.headline, fontSize = 26.sp, fontWeight = FontWeight.Bold)
                    Text(current.actionText, fontSize = 18.sp, lineHeight = 28.sp)
                    Button(
                        onClick = {
                            advancing = true
                            vm.prepareSafetyRecheck(
                                taskId = current.taskId,
                                onReady = ::showNextPicture,
                                onFailure = {
                                    advancing = false
                                    error = it
                                },
                            )
                        },
                        enabled = !advancing,
                        modifier = Modifier.fillMaxWidth().height(54.dp),
                        shape = RoundedCornerShape(16.dp),
                    ) {
                        if (advancing) {
                            CircularProgressIndicator(Modifier.size(22.dp), color = Color.White, strokeWidth = 2.dp)
                        } else {
                            Icon(Icons.Rounded.Done, null)
                            Spacer(Modifier.width(8.dp))
                            Text("我已整理好", fontSize = 18.sp)
                        }
                    }
                }
            }
        } else if (stage == videos.lastIndex) {
            Card(shape = RoundedCornerShape(26.dp), colors = CardDefaults.cardColors(containerColor = BrandSoft)) {
                Row(Modifier.fillMaxWidth().padding(20.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Rounded.CheckCircle, null, tint = Brand, modifier = Modifier.size(30.dp))
                    Spacer(Modifier.width(10.dp))
                    Column {
                        Text("当前没有待处理提醒", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                        Text(current.actionText, color = Muted)
                    }
                }
            }
        } else {
            Button(
                onClick = ::showNextPicture,
                modifier = Modifier.fillMaxWidth().height(54.dp),
                shape = RoundedCornerShape(16.dp),
            ) {
                Icon(Icons.Rounded.Refresh, null)
                Spacer(Modifier.width(8.dp))
                Text("再次检查", fontSize = 18.sp)
            }
        }
    }
}

private suspend fun extractWalkwayFrame(context: Context, rawResource: Int): ByteArray =
    withContext(Dispatchers.IO) {
        val retriever = MediaMetadataRetriever()
        try {
            val uri = Uri.parse("android.resource://${context.packageName}/$rawResource")
            retriever.setDataSource(context, uri)
            val durationMs = retriever
                .extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)
                ?.toLongOrNull()
                ?: 1_000L
            val frameTimeUs = (durationMs * 850L).coerceAtLeast(1L)
            val bitmap = retriever.getFrameAtTime(
                frameTimeUs,
                MediaMetadataRetriever.OPTION_CLOSEST,
            ) ?: error("无法读取当前画面")
            try {
                ByteArrayOutputStream().use { output ->
                    check(bitmap.compress(android.graphics.Bitmap.CompressFormat.JPEG, 90, output))
                    output.toByteArray()
                }
            } finally {
                bitmap.recycle()
            }
        } finally {
            retriever.release()
        }
    }

@Composable
private fun EmbeddedRoundIcon(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    color: Color,
    background: Color = color.copy(alpha = .12f),
) {
    Surface(color = background, shape = RoundedCornerShape(16.dp)) {
        Icon(icon, null, tint = color, modifier = Modifier.padding(11.dp).size(27.dp))
    }
}
