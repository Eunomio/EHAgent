package com.ehagent.resident

import android.app.Application
import android.os.Handler
import android.os.Looper
import android.view.SurfaceHolder
import com.videogo.errorlayer.ErrorInfo
import com.videogo.openapi.EZConstants.EZRealPlayConstants
import com.videogo.openapi.EZOpenSDK
import com.videogo.openapi.EZPlayer

enum class EzvizPlaybackState {
    CONNECTING,
    PLAYING,
    STOPPED,
    ERROR,
}

object EzvizSdk {
    private var initializedAppKey: String? = null

    @Synchronized
    fun configure(application: Application, session: CameraSdkSession): EZOpenSDK {
        val currentKey = initializedAppKey
        if (currentKey == null) {
            EZOpenSDK.showSDKLog(BuildConfig.DEBUG)
            EZOpenSDK.setDebugStreamEnable(false)
            EZOpenSDK.enableP2P(true)
            EZOpenSDK.initLib(application, session.appKey)
            initializedAppKey = session.appKey
        } else if (currentKey != session.appKey) {
            error("萤石 AppKey 已变化，请重新启动应用")
        }
        return EZOpenSDK.getInstance().also { it.setAccessToken(session.accessToken) }
    }
}

class EzvizPlayerController(
    application: Application,
    private val session: CameraSdkSession,
    private val onStateChanged: (EzvizPlaybackState, String?) -> Unit,
) : SurfaceHolder.Callback {
    private val sdk = EzvizSdk.configure(application, session)
    private val handler = Handler(Looper.getMainLooper()) { message ->
        when (message.what) {
            EZRealPlayConstants.MSG_REALPLAY_PLAY_SUCCESS -> {
                started = true
                onStateChanged(EzvizPlaybackState.PLAYING, null)
            }

            EZRealPlayConstants.MSG_REALPLAY_PLAY_FAIL -> {
                started = false
                val errorCode = (message.obj as? ErrorInfo)?.errorCode
                val detail = errorCode?.let { "画面暂时无法打开（错误码 $it）" }
                    ?: "画面暂时无法打开，请稍后重试"
                onStateChanged(EzvizPlaybackState.ERROR, detail)
            }
        }
        true
    }
    private val player: EZPlayer = sdk.createPlayer(session.deviceSerial, session.channelNo).apply {
        setHandler(handler)
        if (session.verifyCode.isNotBlank()) setPlayVerifyCode(session.verifyCode)
        setHardDecode(true)
        closeSound()
    }
    private var holder: SurfaceHolder? = null
    private var foreground = false
    private var started = false

    fun onStart() {
        foreground = true
        startIfReady()
    }

    fun onStop() {
        foreground = false
        stopPlayback()
    }

    private fun startIfReady() {
        val surfaceHolder = holder ?: return
        if (!foreground || started || !surfaceHolder.surface.isValid) return
        onStateChanged(EzvizPlaybackState.CONNECTING, null)
        player.setSurfaceHold(surfaceHolder)
        started = player.startRealPlay()
        if (!started) {
            onStateChanged(EzvizPlaybackState.ERROR, "画面暂时无法打开，请稍后重试")
        }
    }

    private fun stopPlayback() {
        if (started) player.stopRealPlay()
        started = false
        onStateChanged(EzvizPlaybackState.STOPPED, null)
    }

    override fun surfaceCreated(surfaceHolder: SurfaceHolder) {
        holder = surfaceHolder
        startIfReady()
    }

    override fun surfaceChanged(surfaceHolder: SurfaceHolder, format: Int, width: Int, height: Int) {
        holder = surfaceHolder
    }

    override fun surfaceDestroyed(surfaceHolder: SurfaceHolder) {
        stopPlayback()
        player.setSurfaceHold(null)
        holder = null
    }

    fun release() {
        stopPlayback()
        holder?.removeCallback(this)
        player.setSurfaceHold(null)
        player.release()
        handler.removeCallbacksAndMessages(null)
    }
}
