# 萤石设备接入与调试

## C6c

1. 在[萤石开放平台](https://open.ys7.com/)创建应用，取得 AppKey 和 AppSecret。
2. 将 C6c 添加到萤石账号，确认设备在线，记录设备序列号和机身验证码。
3. 复制 `.env.example` 为 `.env`，填写：

```dotenv
EH_EZVIZ_APP_KEY=你的AppKey
EH_EZVIZ_APP_SECRET=你的AppSecret
EH_EZVIZ_DEVICE_SERIAL=设备序列号
EH_EZVIZ_CHANNEL_NO=1
EH_EZVIZ_VERIFY_CODE=设备验证码
```

4. 重启后端，依次调用：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/devices/c6c/test
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/devices/c6c/capture
```

抓图接口使用萤石开放平台的设备抓图能力。当前服务会取得真实图片地址并登记一次待分析检查。模型判断完成后，再把结果发到 `safety-results` 接口。

老人端查看实时画面时，APK向Windows Agent取得播放会话，再由萤石Android SDK的`EZPlayer`按设备序列号和通道号直接取流。AppSecret不会发送到APK。SDK播放会话测试接口：

```powershell
$session = Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/devices/c6c/sdk-session
$session | Select-Object success, device_serial, channel_no
```

成功时会显示`success: True`以及已配置的设备和通道。不要在截图或聊天中发送完整AccessToken和设备验证码。画面默认静音，老人关闭画面、离开居家安全页或把应用切到后台后停止播放。

Android工程使用官方Maven依赖`io.github.ezviz-open:ezviz-sdk:5.30.2`。在萤石开放平台的移动应用配置中填写安卓包名`com.ehagent.resident`。真机首次测试步骤：

1. 保持Windows Agent运行，并确认手机可以访问电脑的8000端口。
2. 在APK“我的”页面填写电脑局域网地址，例如`http://192.168.1.20:8000`。
3. 打开“居家安全”，点击“查看实时画面”。
4. 画面加载成功后切到其他页面，再返回确认播放器能够重新连接。
5. C6c使用H.265时优先在ARM64安卓真机验证；x86模拟器可能无法加载或稳定运行SDK的原生解码库。

原有`POST /api/v1/devices/c6c/live`继续保留，方便在电脑上用VLC或ffprobe排查标准HLS地址，APK不再依赖该地址。

开发依据：[萤石 Android SDK下载](https://open.ys7.com/cn/s/download)、[萤石 Android SDK Demo](https://github.com/Ezviz-Open/EzvizSDK-Android)、[EZPlayer接口](https://open.ys7.com/doc/zh/android/com/videogo/openapi/EZPlayer.html)。

## 无感睡眠助手

后端保留统一的夜间摘要接收口：

```text
POST /api/v1/ingest/sleep-summaries
```

同时支持萤石开放平台的最小连通性检查：

```text
POST /api/v1/devices/sleep/test
```

在 `.env` 中配置 `EH_SLEEP_PROVIDER=ezviz`、`EH_EZVIZ_APP_KEY`、`EH_EZVIZ_APP_SECRET`，并提供 `EH_SLEEP_DEVICE_ID` 或 `EH_SLEEP_DEVICE_SERIAL`。启用 `EH_EZVIZ_AUTO_TOKEN=true` 后，后端仅在内存中获取和缓存访问令牌；令牌、完整序列号和设备验证码不得写入 APK、文档、测试夹具或提交记录。

若只配置设备序列号，适配器会通过萤石睡眠组件的设备 ID 查询接口解析内部 `deviceId`；若已知 `EH_SLEEP_DEVICE_ID`，则不发起该解析请求。当前连通性接口只验证凭证和设备 ID 路径，尚未抓取、转换或入库萤石的睡眠统计数据。

后续数据接入顺序：

1. 以官方睡眠体征监测组件的实际返回为准，确认字段口径、日期边界、时区、单位和数据缺失语义。
2. 将已授权的睡眠统计映射为 `sleep-summaries`；每晚写入一次摘要，时序采样写入 `samples`。
3. 每条记录保留 `source`、`measured_at`、质量标记与脱敏调试证据；无记录或字段缺失时标为 `insufficient`，不得补零。
4. 在 Android 客户端展示前，分别验证设备连通、统计读取、入库与页面读取，不能以接口 200 代替非空数据验证。

正式授权前，可以使用设备官方导出的真实记录联调：

```powershell
.\scripts\send-sleep-summary.ps1 -Backend http://127.0.0.1:8000
```

请先把脚本中的示例值替换为设备实际导出值。接口依据：[睡眠体征监测组件](https://open.ys7.com/help/1850)、[睡眠伴侣 EP：离床未归时长](https://open.ys7.com/help/2059)；公开产品背景参考：[萤石无感睡眠监测资料](https://icnopen.ezviz.com/cn/s/244)。

## 手机无法连接时

- 电脑和手机连接同一 Wi-Fi，服务启动参数为 `0.0.0.0:8000`。
- Windows 防火墙允许 Python 在专用网络通信。
- 手机里填写电脑 IPv4 地址，不能填写 `127.0.0.1`。
- 先用手机浏览器打开 `http://电脑地址:8000/api/v1/health`；看到 `status: ok` 后再回到应用连接。
