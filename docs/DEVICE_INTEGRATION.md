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

### 通道画面变化触发

自动通道检查每2秒优先轮询萤石设备告警接口`/api/lapp/alarm/device/list`。新告警必须匹配当前配置的设备序列号和通道号；同一告警编号只处理一次。收到告警后默认等待1秒，让移动过程结束，再抓取当前图片并检查。

萤石告警请求超过2秒、返回错误或暂时不可用时，服务立即使用本地图片差异检测。连续8秒没有告警时也执行一次本地校验，防止设备未上报告警。本地变化以1秒间隔确认两张图片。发送视觉分析前会把超大图片压缩到最长边1280像素，减少上传和图片预处理时间。相关配置：

```dotenv
EH_EZVIZ_ALARM_DETECTION_ENABLED=true
EH_EZVIZ_ALARM_POLL_SECONDS=2
EH_EZVIZ_ALARM_TIMEOUT_SECONDS=2
EH_EZVIZ_ALARM_SETTLE_SECONDS=1
EH_EZVIZ_ALARM_FALLBACK_SECONDS=8
EH_VLM_CHANGE_POLL_SECONDS=1
EH_VLM_CHANGE_CONFIRMATIONS=2
EH_VLM_CHANGE_COOLDOWN_SECONDS=10
EH_VLM_IMAGE_MAX_DIMENSION=1280
EH_VLM_IMAGE_JPEG_QUALITY=85
```

使用前需要在萤石云视频中开启C6c的移动侦测或布防。若当前账号没有告警列表权限，日志会记录萤石告警不可用，通道检查继续使用本地检测。

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
POST /api/v1/ingest/sleep-reports
```

同时支持萤石开放平台的最小连通性检查：

```text
POST /api/v1/devices/sleep/test
```

在 `.env` 中配置 `EH_SLEEP_PROVIDER=ezviz`、`EH_EZVIZ_APP_KEY`、`EH_EZVIZ_APP_SECRET`，并提供 `EH_SLEEP_DEVICE_ID` 或 `EH_SLEEP_DEVICE_SERIAL`。启用 `EH_EZVIZ_AUTO_TOKEN=true` 后，后端仅在内存中获取和缓存访问令牌；令牌、完整序列号和设备验证码不得写入 APK、文档、测试夹具或提交记录。

若只配置设备序列号，适配器会通过萤石睡眠组件的设备 ID 查询接口解析内部 `deviceId`；若已知 `EH_SLEEP_DEVICE_ID`，则不发起该解析请求。

使用下列接口同步指定日期的统计数据；未传 `target_date` 时默认同步前一天：

```text
POST /api/v1/devices/sleep/sync?target_date=YYYY-MM-DD
```

同步接口调用萤石的每日睡眠、每日心率和每日呼吸率统计，并写入既有 `sleep-summaries` 契约：

| 项目契约字段 | 萤石来源 | 处理方式 |
| --- | --- | --- |
| `sleep_start`、`sleep_end`、`duration_minutes` | 呼吸统计的睡眠起止时间 | 使用 `EH_SLEEP_TIMESTAMP_UTC_OFFSET_HOURS` 解析，计算时长；无有效时间则同步失败。 |
| `heart_rate`、`heart_rate_min`、`heart_rate_max` | 心率统计的均值、最小值、最大值 | 只接受 20–240 次/分。 |
| `respiratory_rate`、`respiratory_min`、`respiratory_max` | 呼吸统计的十分钟均值、最小值、最大值 | 日均值由有效十分钟均值计算；只接受 1–80 次/分。 |
| `samples[].at`、`samples[].heart_rate`、`samples[].respiratory_rate` | 心率分钟曲线、呼吸十分钟曲线 | 以时间戳合并，保留可用的单项或双项采样点。 |
| `measured_at`、`source`、`quality` | 睡眠结束时间、固定来源、有效字段情况 | 结束时间为测量时间；来源为 `ezviz_sleep_assistant`；无有效心率和呼吸率时标记 `insufficient`。 |
| `bed_exit_count`、`bed_exit_status` | 睡眠伴侣 EP 的事件级入床/离床消息 | 只统计睡眠时间窗内的离床事件并去重；完整查询成功才允许写入 0，否则保持为空并标记 `unavailable`。 |

每日睡眠评分可入库，并在 Android 端明确显示为“萤石参考分”；不将它与个人基线合成新的健康分数。分期字段只在接口返回且口径确认后展示。萤石统计时间字符串可能不带时区，继续使用 `EH_SLEEP_TIMESTAMP_UTC_OFFSET_HOURS` 显式解析，实际偏移仍须和设备端记录核对。不得用清醒分期推导离床次数、HRV 或医疗结论。

后端默认在北京时间 10:00 同步前一晚，并在启动时补拉最近三天。可用 `EH_SLEEP_AUTO_SYNC_ENABLED`、`EH_SLEEP_SYNC_HOUR`、`EH_SLEEP_SYNC_MINUTE`、`EH_SLEEP_SYNC_LOOKBACK_DAYS` 和 `EH_SLEEP_SYNC_UTC_OFFSET_HOURS` 调整。页面读取本地数据库；外部接口失败不会阻塞既有报告。

本地开发环境提供 `POST /api/v1/devices/sleep/demo` 和 `DELETE /api/v1/devices/sleep/demo`。前者导入随源码提交的 `app/sleep/demo_sleep_healthy_baseline.json` 与 `app/sleep/demo_sleep_return_delay.json`：第一组为7晚健康基线，第二组为7晚变化数据，其中第1、2晚正常，第3、4晚起夜后长时间清醒，第5晚缓解，第6、7晚回归稳态。导入前只替换旧的 `demo_generated` 数据，不影响真实设备记录；后者只删除当前 `demo_dataset_id`。两组记录共享一个演示数据集，使变化组能够与前7晚个人基线比较。生产环境拒绝这两个操作。Android Demo 包按新的数据集版本自动导入一次，用户手动清除后不会因页面刷新恢复，仍可在“我的”页面主动重新导入。

个人基线使用当前夜之前最多 14 晚有效记录，至少 7 晚后启用。睡眠时长、平均心率和平均呼吸率分别计算中位数与 MAD，仅描述是否与近期个人水平有变化。当前产品不输出跌倒风险、行动能力、认知状态或心理健康预测。

睡眠页包含可展开的“起夜关注”子模块。它只在收到可靠离床事件后，把本次睡眠快照与个人基线作确定性比较：睡眠时长减少、平均心率升高、平均呼吸率升高属于关注方向，至少两项达到既有基线变化阈值时显示“需要多留意”。该结果是预防性提示，不是跌倒概率或医疗判断；离床次数只作事实展示，不参与关注度计算。睡眠段未结束时，累计睡眠时长不得和整夜基线比较。

本地开发环境可在导入14晚演示数据后调用：

```text
POST /api/v1/devices/sleep/demo/night-awakening
DELETE /api/v1/devices/sleep/demo/night-awakening
```

前者幂等生成一次带阶段性快照的演示离床关注，后者只重置同一 `demo_dataset_id` 的起夜演示。`GET /api/v1/resident/sleep` 和首页睡眠对象通过可选字段 `night_awakening` 返回事件、逐项基线差异、建议、算法版本和边界说明。活动事件在收到 `in_bed` 后解除；当前持久化层也会在缺少返回事件时于 30 分钟后自动标为 `resolved`。Android 只在同一个新事件首次出现且关注度为 `extra_care` 时自动展开一次，用户的折叠选择保存在本机。

萤石事件级入床/离床接口目前只有适配器与离线测试，尚无真实非空事件证据。真实接口验证前，产品只能显示“接口待验证”，不能宣称已稳定监测起夜。以后若要建立跌倒风险模型，还需接入起夜后的步态、支撑稳定性、环境障碍、既往跌倒和人工结果标注；睡眠偏离不能单独升级为跌倒预测。

后续数据接入顺序：

1. 以官方睡眠体征监测组件的实际返回为准，确认字段口径、日期边界、时区、单位和数据缺失语义。
2. 每条记录保留 `source`、`measured_at`、质量标记与脱敏调试证据；无记录或字段缺失时标为 `insufficient`，不得补零。
3. 在 Android 客户端展示前，分别验证设备连通、统计读取、入库与页面读取，不能以接口 200 代替非空数据验证。

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
