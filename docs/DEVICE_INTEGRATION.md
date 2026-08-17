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

萤石公开产品资料确认设备可采集睡眠状态、心率、呼吸频率和离床信息。睡眠数据接口权限随开放平台应用和项目授权变化，Windows Agent通过独立设备序列号绑定一台无感睡眠助手，并提供正式报告接收口：

```text
POST /api/v1/ingest/sleep-reports
```

接入顺序：

1. 在设备机身标签、包装或萤石账号设备列表中找到睡眠助手的设备序列号。
2. 向萤石项目联系人申请睡眠数据授权，确认回调字段、报告编号、时间单位和推送重试规则。
3. 将开放接口字段映射为本项目的睡眠报告格式；每份报告必须带`device_serial`。
4. `.env`填写：

```dotenv
EH_SLEEP_PROVIDER=ezviz_webhook
EH_SLEEP_DEVICE_NAME=萤石无感睡眠助手
EH_SLEEP_DEVICE_SERIAL=设备机身上的序列号
EH_SLEEP_WEBHOOK_TOKEN=自行生成的随机长字符串
```

5. 推送程序调用接口时增加请求头：

```text
X-EH-Sleep-Token: 与EH_SLEEP_WEBHOOK_TOKEN相同的内容
```

6. 重启服务。`GET /api/v1/devices`中睡眠设备的`configured`应为`true`。

报告包含设备序列号、平台报告编号、报告日期、时区、睡眠起止时间、总睡眠时长、睡眠构成、得分、心率、呼吸频率、离床次数、数据质量、报告状态和生成时间。接口提供时序采样时放入`samples`，提供睡眠阶段区间时放入`stages`。同一设备的同一平台报告编号再次推送时更新原记录。

正式授权前，可以使用设备官方导出的真实记录联调：

```powershell
.\scripts\send-sleep-summary.ps1 -Backend http://127.0.0.1:8000
```

请先把脚本中的示例设备序列号、报告编号和数值替换为设备实际数据。如果配置了接收凭证，运行：

```powershell
.\scripts\send-sleep-summary.ps1 -Backend http://127.0.0.1:8000 -Token "你的接收凭证"
```

当前公开文档没有给出通用睡眠报告REST路径。取得比赛账号的获批接口文档后，在萤石回调或同步程序中完成一次字段映射即可，住户页面、数据库和分析模块无需再调整。公开能力参考：[萤石无感睡眠监测资料](https://icnopen.ezviz.com/cn/s/244)、[萤石睡眠产品介绍](https://www.ezviz.com/cn/news/6412.html?_cc=1)。

## 手机无法连接时

- 电脑和手机连接同一 Wi-Fi，服务启动参数为 `0.0.0.0:8000`。
- Windows 防火墙允许 Python 在专用网络通信。
- 手机里填写电脑 IPv4 地址，不能填写 `127.0.0.1`。
- 先用手机浏览器打开 `http://电脑地址:8000/api/v1/health`；看到 `status: ok` 后再回到应用连接。
