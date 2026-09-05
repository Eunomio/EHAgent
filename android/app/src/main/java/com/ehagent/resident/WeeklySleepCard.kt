package com.ehagent.resident

import androidx.compose.foundation.background
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Air
import androidx.compose.material.icons.rounded.Bedtime
import androidx.compose.material.icons.rounded.Favorite
import androidx.compose.material.icons.rounded.Hotel
import androidx.compose.material.icons.rounded.WbSunny
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.Locale
import kotlin.math.ceil

private val WeekInk = Color(0xFF193F37)

@Composable
fun WeeklySleepCard(week: WeeklySleepOverview) {
    var expanded by rememberSaveable { mutableStateOf(false) }
    Card(
        modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFFF0F6F2)),
    ) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text("上周睡眠概览", modifier = Modifier.weight(1f), fontSize = 22.sp, fontWeight = FontWeight.Bold, color = WeekInk)
                TextButton(onClick = { expanded = !expanded }) {
                    Text(if (expanded) "收起" else "展开", fontSize = 18.sp)
                }
            }
            Text(week.message, fontSize = 19.sp, lineHeight = 29.sp, color = WeekInk)
            if (expanded) {
            WeeklyMetric(
                Icons.Rounded.Hotel, "平均每晚睡眠",
                week.duration?.let { "${it / 60}小时 ${it % 60}分钟" } ?: "暂无记录",
                Color(0xFF32594D), Modifier.fillMaxWidth(),
            )
            WeeklyDurationChart(week.durationSeries)
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        WeeklyMetric(Icons.Rounded.Bedtime, "通常入睡", week.sleepTime ?: "暂无记录", Color(0xFF494B82), Modifier.weight(1f))
                        WeeklyMetric(Icons.Rounded.WbSunny, "通常起床", week.wakeTime ?: "暂无记录", Color(0xFF885513), Modifier.weight(1f))
                    }
            SleepClockBand(week.sleepTime, week.wakeTime)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                WeeklyMetric(Icons.Rounded.Favorite, "平均心率", weeklyRate(week.heartRate).removeSuffix(" 次/分"), Color(0xFF9B3D45), Modifier.weight(1f), "次/分")
                WeeklyMetric(Icons.Rounded.Air, "平均呼吸", weeklyRate(week.respiratoryRate).removeSuffix(" 次/分"), Color(0xFF286278), Modifier.weight(1f), "次/分")
            }
            }
        }
    }
}

internal fun weeklyChartMaximumHours(points: List<WeeklySleepNight>): Int =
    maxOf(8, ceil((points.mapNotNull { it.minutes }.maxOrNull() ?: 0) / 120.0).toInt() * 2)

@Composable
private fun WeeklyDurationChart(points: List<WeeklySleepNight>) {
    if (points.isEmpty()) return
    val top = weeklyChartMaximumHours(points)
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("每晚睡眠时长 · 小时", fontSize = 18.sp, color = WeekInk)
        Row(Modifier.fillMaxWidth().height(150.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Column(Modifier.width(30.dp).fillMaxHeight().padding(bottom = 28.dp), verticalArrangement = Arrangement.SpaceBetween) {
                Text(top.toString(), fontSize = 16.sp, color = WeekInk)
                Text((top / 2).toString(), fontSize = 16.sp, color = WeekInk)
                Text("0", fontSize = 16.sp, color = WeekInk)
            }
            points.forEach { point ->
                Column(
                    Modifier.weight(1f).fillMaxHeight().semantics {
                        contentDescription = point.date + (point.minutes?.let { "，睡眠${it / 60}小时${it % 60}分钟" } ?: "，暂无记录")
                    }, horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.BottomCenter) {
                        if (point.minutes != null) {
                            Box(Modifier.fillMaxWidth(.72f)
                                .fillMaxHeight((point.minutes / (top * 60f)).coerceIn(0.01f, 1f))
                                .background(Color(0xFF327666), RoundedCornerShape(topStart = 6.dp, topEnd = 6.dp)))
                        } else {
                            Text("—", color = Color(0xFF586B65), fontSize = 18.sp)
                        }
                    }
                    HorizontalDivider(color = Color(0xFF758E85))
                    Text(point.date.takeLast(2), fontSize = 16.sp, color = WeekInk, modifier = Modifier.padding(top = 5.dp))
                }
            }
        }
        Text("横轴为日期；空缺表示没有记录", fontSize = 16.sp, color = Color(0xFF486258))
    }
}

@Composable
private fun SleepClockBand(start: String?, end: String?) {
    fun hour(value: String): Float? = runCatching {
        val parts = value.split(":")
        parts[0].toFloat() + parts[1].toFloat() / 60f
    }.getOrNull()
    val from = start?.let(::hour) ?: return
    val to = end?.let(::hour) ?: return
    Canvas(Modifier.fillMaxWidth().height(28.dp).semantics {
        contentDescription = "24小时作息时间轴，通常${start}入睡，${end}起床；包括夜间清醒时间"
    }) {
        val y = size.height / 2
        drawLine(Color(0xFFCCDAD2), Offset(0f, y), Offset(size.width, y), strokeWidth = 12.dp.toPx())
        fun segment(a: Float, b: Float) {
            drawRect(Color(0xFF7177A4), Offset(size.width * a / 24, y - 6.dp.toPx()),
                Size(size.width * (b - a) / 24, 12.dp.toPx()))
        }
        if (to >= from) segment(from, to) else { segment(from, 24f); segment(0f, to) }
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        listOf("0时", "6时", "12时", "18时", "24时").forEach {
            Text(it, fontSize = 16.sp, color = WeekInk)
        }
    }
    Text("作息时段（包含夜间醒来的时间）", fontSize = 16.sp, color = Color(0xFF486258))
}

internal fun weeklyRate(value: Double?): String = value?.let {
    (if (it == it.toInt().toDouble()) it.toInt().toString() else String.format(Locale.CHINA, "%.1f", it)) + " 次/分"
} ?: "暂无记录"

@Composable
private fun WeeklyMetric(icon: ImageVector, label: String, value: String, tint: Color, modifier: Modifier, unit: String? = null) {
    Column(
        modifier.background(Color.White, RoundedCornerShape(18.dp)).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(24.dp))
            Text(label, fontSize = 18.sp, color = WeekInk, lineHeight = 25.sp)
        }
        Text(value, fontSize = 26.sp, lineHeight = 34.sp, fontWeight = FontWeight.SemiBold, color = WeekInk)
        unit?.let { Text(it, fontSize = 16.sp, color = WeekInk) }
    }
}
