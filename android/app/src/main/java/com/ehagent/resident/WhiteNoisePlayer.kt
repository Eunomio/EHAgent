package com.ehagent.resident

import android.media.AudioAttributes
import android.media.MediaPlayer

/** Streams a selected, reviewed white-noise asset from the resident's local Agent. */
internal class WhiteNoisePlayer {
    private var player: MediaPlayer? = null
    private var volume: Float = 0.35f

    @Synchronized
    fun start(url: String, onStarted: () -> Unit, onError: () -> Unit) {
        stop()
        val next = MediaPlayer().apply {
            setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                    .build()
            )
            setDataSource(url)
            isLooping = true
            setVolume(volume, volume)
            setOnPreparedListener {
                it.start()
                onStarted()
            }
            setOnErrorListener { failed, _, _ ->
                runCatching { failed.release() }
                if (player === failed) player = null
                onError()
                true
            }
            prepareAsync()
        }
        player = next
    }

    @Synchronized
    fun pause() {
        player?.takeIf { it.isPlaying }?.pause()
    }

    @Synchronized
    fun resume() {
        player?.takeIf { !it.isPlaying }?.start()
    }

    @Synchronized
    fun setVolume(value: Float) {
        volume = value.coerceIn(0f, 1f)
        player?.setVolume(volume, volume)
    }

    @Synchronized
    fun stop() {
        player?.let { current ->
            current.setOnPreparedListener(null)
            current.setOnErrorListener(null)
            runCatching { current.stop() }
            runCatching { current.release() }
        }
        player = null
    }
}
