package com.ehagent.resident

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
internal fun RecentSleepTrendCard(historyNewestFirst: List<SleepHistoryNight>) {
    val nights = historyNewestFirst.take(7).reversed()
    if (nights.size < 7) return
    var selected by remember(nights) { mutableIntStateOf(nights.lastIndex) }
    val night = nights[selected]
    Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(19.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("最近7晚", fontSize = 20.sp, fontWeight = FontWeight.Bold)
            Text("起夜后再次入睡用时", color = Muted, fontSize = 15.sp)
            Row(
                Modifier.fillMaxWidth().height(155.dp),
                horizontalArrangement = Arrangement.spacedBy(7.dp),
                verticalAlignment = Alignment.Bottom,
            ) {
                nights.forEachIndexed { index, item ->
                    val minutes = item.awakeAfterReturnMinutes
                    val needsAttention = (minutes ?: 0) >= 55
                    Column(
                        Modifier.weight(1f).clickable { selected = index },
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Text(minutes?.toString() ?: "—", fontSize = 12.sp, color = if (needsAttention) Color(0xFFB45309) else Brand)
                        if (minutes != null) Box(
                            Modifier.fillMaxWidth().height((minutes.coerceAtLeast(5) * 1.45f).dp)
                                .clip(RoundedCornerShape(topStart = 7.dp, topEnd = 7.dp))
                                .background(if (needsAttention) Warm else if (selected == index) Brand else Brand.copy(alpha = .42f)),
                        )
                        Text("${index + 1}", color = Muted, fontSize = 13.sp)
                    }
                }
            }
            Text("分钟 · 点击柱形查看当晚数据", color = Muted, fontSize = 13.sp)
            HorizontalDivider()
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("第${selected + 1}晚 · ${shortDate(night.reportDate)}", fontWeight = FontWeight.Bold)
                night.sleepScore?.let { Text("睡眠参考分 ${it.toInt()}", color = Brand) }
            }
            Text("${clock(night.sleepStart)} 入睡 · ${clock(night.sleepEnd)} 起床 · 共睡 ${duration(night.durationMinutes)}")
            TrendRow("夜间离床", "${night.bedExitCount ?: "—"}次", "回床后清醒 ${night.awakeAfterReturnMinutes ?: "—"}分钟")
            TrendRow("睡眠构成", "清醒${night.awakeMinutes ?: "—"}分", "浅睡${night.lightSleepMinutes ?: "—"} · 深睡${night.deepSleepMinutes ?: "—"} · 快速眼动${night.remSleepMinutes ?: "—"}分")
            TrendRow("平均体征", "心率${night.heartRate?.toInt() ?: "—"}次/分", "呼吸${night.respiratoryRate ?: "—"}次/分")
            if ((nights[3].awakeAfterReturnMinutes ?: 0) >= 55 &&
                (nights[4].awakeAfterReturnMinutes ?: 0) >= 55 &&
                nights.takeLast(2).all {
                    val minutes = it.awakeAfterReturnMinutes
                    minutes != null && minutes < minOf(
                        nights[3].awakeAfterReturnMinutes ?: 0,
                        nights[4].awakeAfterReturnMinutes ?: 0,
                    )
                }
            ) {
                Text("第4、5晚起夜后较久才再次入睡，最近两晚已有好转。", color = Color(0xFF9A6700), fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun TrendRow(label: String, value: String, detail: String) {
    Row(Modifier.fillMaxWidth()) {
        Text(label, color = Muted, modifier = Modifier.width(82.dp))
        Column { Text(value, fontWeight = FontWeight.SemiBold); Text(detail, color = Muted, fontSize = 14.sp) }
    }
}

private fun shortDate(value: String) = value.split('-').takeLast(2).joinToString("月", postfix = "日")
private fun clock(value: String) = value.substringAfter('T').take(5)
private fun duration(value: Int) = "${value / 60}小时${value % 60}分"
