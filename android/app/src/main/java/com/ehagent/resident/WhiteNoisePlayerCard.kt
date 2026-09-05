package com.ehagent.resident

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.GraphicEq
import androidx.compose.material.icons.rounded.Pause
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.SkipNext
import androidx.compose.material.icons.rounded.SkipPrevious
import androidx.compose.material.icons.rounded.StopCircle
import androidx.compose.material.icons.rounded.VolumeDown
import androidx.compose.material.icons.rounded.VolumeUp
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Button
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
internal fun WhiteNoisePlayerCard(state: UiState, vm: MainViewModel) {
    val elapsed = state.whiteNoiseElapsedSeconds.coerceAtLeast(0)
    val remaining = state.whiteNoiseRemainingSeconds.coerceAtLeast(0)
    val progress = (elapsed / (30f * 60f)).coerceIn(0f, 1f)
    Surface(
        color = BrandSoft,
        shape = RoundedCornerShape(22.dp),
        shadowElevation = 2.dp,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            Modifier.padding(horizontal = 17.dp, vertical = 15.dp),
            verticalArrangement = Arrangement.spacedBy(11.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (state.whiteNoiseLoading) {
                    CircularProgressIndicator(Modifier.size(31.dp), color = Brand, strokeWidth = 3.dp)
                } else {
                    Icon(Icons.Rounded.GraphicEq, null, tint = Brand, modifier = Modifier.size(34.dp))
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text("助眠声音", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    Text(
                        when {
                            state.whiteNoiseError != null -> "素材暂时不可用"
                            state.whiteNoiseLoading -> "正在准备音频"
                            state.whiteNoisePaused -> "已暂停 · ${state.whiteNoiseTrackName.orEmpty()}"
                            else -> "正在播放 · ${state.whiteNoiseTrackName.orEmpty()}"
                        },
                        color = Muted,
                        fontSize = 15.sp,
                    )
                }
                TextButton(onClick = vm::stopWhiteNoise) {
                    Icon(Icons.Rounded.StopCircle, null)
                    Spacer(Modifier.width(4.dp))
                    Text("停止")
                }
            }

            state.whiteNoiseError?.let { error ->
                Text(error, color = Muted, fontSize = 16.sp)
                Button(
                    onClick = vm::retryWhiteNoise,
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(15.dp),
                ) {
                    Icon(Icons.Rounded.Refresh, null)
                    Spacer(Modifier.width(7.dp))
                    Text("重新载入素材", fontSize = 17.sp)
                }
                return@Column
            }

            LinearProgressIndicator(
                progress = { progress },
                modifier = Modifier.fillMaxWidth(),
                color = Brand,
            )
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(formatPlayerTime(elapsed), color = Muted, fontSize = 14.sp)
                Text("剩余${formatPlayerTime(remaining)}", color = Muted, fontSize = 14.sp)
            }

            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(
                    onClick = vm::previousWhiteNoise,
                    enabled = state.whiteNoiseCanSwitch && !state.whiteNoiseLoading,
                    modifier = Modifier.size(54.dp),
                ) { Icon(Icons.Rounded.SkipPrevious, "上一首", modifier = Modifier.size(34.dp)) }
                FilledIconButton(
                    onClick = vm::toggleWhiteNoisePlayback,
                    enabled = !state.whiteNoiseLoading,
                    modifier = Modifier.size(62.dp),
                ) {
                    Icon(
                        if (state.whiteNoisePlaying) Icons.Rounded.Pause else Icons.Rounded.PlayArrow,
                        if (state.whiteNoisePlaying) "暂停" else "继续播放",
                        modifier = Modifier.size(38.dp),
                    )
                }
                IconButton(
                    onClick = vm::nextWhiteNoise,
                    enabled = state.whiteNoiseCanSwitch && !state.whiteNoiseLoading,
                    modifier = Modifier.size(54.dp),
                ) { Icon(Icons.Rounded.SkipNext, "下一首", modifier = Modifier.size(34.dp)) }
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Rounded.VolumeDown, "降低音量", tint = Muted)
                Slider(
                    value = state.whiteNoiseVolume,
                    onValueChange = vm::setWhiteNoiseVolume,
                    valueRange = 0.05f..0.7f,
                    modifier = Modifier.weight(1f).padding(horizontal = 8.dp),
                )
                Icon(Icons.Rounded.VolumeUp, "提高音量", tint = Muted)
            }
        }
    }
}

private fun formatPlayerTime(seconds: Int): String =
    "%02d:%02d".format(seconds.coerceAtLeast(0) / 60, seconds.coerceAtLeast(0) % 60)
