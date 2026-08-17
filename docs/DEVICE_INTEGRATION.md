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

老人端查看实时画面时，Windows Agent通过萤石开放平台申请30分钟有效的HLS地址，APK使用Media3播放器打开。测试接口：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/devices/c6c/live
```

成功时返回`url`、`protocol: hls`和`expires_in: 1800`。如果返回直播服务未开通、余额不足或权限不足，需要在萤石开放平台确认该应用和设备具备视频预览或标准直播能力。画面默认静音，老人关闭画面、离开居家安全页或把应用切到后台后停止播放。

开发依据：[萤石 Android SDK 文档](https://open.ys7.com/doc/zh/book/4.x/android-sdk.html)、[设备与视频能力](https://open.ys7.com/cn/s/device)。

## 无感睡眠助手

萤石公开产品资料确认设备可采集睡眠状态、心率、呼吸频率和离床信息。具体数据接口权限随开放平台应用和项目授权变化，因此后端提供统一接收口：

```text
POST /api/v1/ingest/sleep-summaries
```

接入顺序：

1. 向萤石项目联系人申请睡眠数据授权，确认回调或导出的字段、频率与时间单位。
2. 将萤石字段映射为本项目的睡眠摘要格式。
3. 每晚睡眠结束后发送一次摘要；若可取得时序数据，把采样点放入 `samples`。
4. `.env` 设置 `EH_SLEEP_PROVIDER=webhook`，重启服务，手机首页即显示真实记录。

正式授权前，可以使用设备官方导出的真实记录联调：

```powershell
.\scripts\send-sleep-summary.ps1 -Backend http://127.0.0.1:8000
```

请先把脚本中的示例值替换为设备实际导出值。公开能力参考：[萤石无感睡眠监测资料](https://icnopen.ezviz.com/cn/s/244)、[萤石睡眠产品介绍](https://www.ezviz.com/cn/news/6412.html?_cc=1)。

## 手机无法连接时

- 电脑和手机连接同一 Wi-Fi，服务启动参数为 `0.0.0.0:8000`。
- Windows 防火墙允许 Python 在专用网络通信。
- 手机里填写电脑 IPv4 地址，不能填写 `127.0.0.1`。
- 先用手机浏览器打开 `http://电脑地址:8000/api/v1/health`；看到 `status: ok` 后再回到应用连接。
