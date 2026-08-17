package com.ehagent.resident

import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material3.Icon
import androidx.compose.material3.SmallFloatingActionButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import kotlin.math.roundToInt

@Composable
internal fun DraggableAssistantButton(onClick: () -> Unit) {
    val configuration = LocalConfiguration.current
    val density = LocalDensity.current
    val horizontalTravel = with(density) {
        (configuration.screenWidthDp.dp - 84.dp).toPx().coerceAtLeast(0f)
    }
    val verticalTravel = with(density) {
        (configuration.screenHeightDp.dp - 180.dp).toPx().coerceAtLeast(0f)
    }
    var offsetX by rememberSaveable { mutableFloatStateOf(0f) }
    var offsetY by rememberSaveable { mutableFloatStateOf(0f) }

    LaunchedEffect(horizontalTravel, verticalTravel) {
        offsetX = offsetX.coerceIn(-horizontalTravel, 0f)
        offsetY = offsetY.coerceIn(-verticalTravel, 0f)
    }

    SmallFloatingActionButton(
        onClick = onClick,
        modifier = Modifier
            .offset { IntOffset(offsetX.roundToInt(), offsetY.roundToInt()) }
            .size(52.dp)
            .pointerInput(horizontalTravel, verticalTravel) {
                detectDragGestures { change, dragAmount ->
                    change.consume()
                    offsetX = (offsetX + dragAmount.x).coerceIn(-horizontalTravel, 0f)
                    offsetY = (offsetY + dragAmount.y).coerceIn(-verticalTravel, 0f)
                }
            },
        containerColor = Brand,
        contentColor = Color.White,
    ) {
        Icon(Icons.Rounded.AutoAwesome, contentDescription = "问小安")
    }
}
