# 后端接口

Windows 本地 Agent 默认监听 `http://电脑IP:8000`，OpenAPI 交互文档位于 `/docs`。安卓真机使用电脑的局域网 IPv4 地址，Android 模拟器使用 `http://10.0.2.2:8000`。

## 住户端接口

| 用途 | 方法与路径 |
|---|---|
| 服务状态 | `GET /api/v1/health` |
| 老人首页 | `GET /api/v1/resident/dashboard` |
| 通道安全任务和检查记录 | `GET /api/v1/resident/safety` |
| 整理完成、稍后提醒或请求家人 | `POST /api/v1/resident/safety/tasks/{id}/actions` |
| 睡眠详情、个人基线和起夜关注 | `GET /api/v1/resident/sleep` |
| 查看或提交家人帮助请求 | `GET/POST /api/v1/resident/help` |
| 更新帮助请求状态 | `PUT /api/v1/resident/help/{id}` |
| 隐私与联系人设置 | `GET/PUT /api/v1/resident/settings` |
| 提交或查看老人反馈 | `POST/GET /api/v1/resident/feedback` |

安全任务动作由请求体中的 `action` 指定。当前支持的动作以 `/docs` 中的 `TaskAction` Schema 为准，APK 已使用“我已整理好”“30 分钟后提醒”和请求家人协助流程。

## C6c 与自动通道检查

| 用途 | 方法与路径 |
|---|---|
| 设备状态 | `GET /api/v1/devices` |
| C6c 连通测试 | `POST /api/v1/devices/c6c/test` |
| C6c 单次抓图 | `POST /api/v1/devices/c6c/capture` |
| 电脑调试用临时 HLS 地址 | `POST /api/v1/devices/c6c/live` |
| 安卓 EZPlayer 播放会话 | `POST /api/v1/devices/c6c/sdk-session` |
| 查看通道参考状态 | `GET /api/v1/devices/c6c/safety/baseline` |
| 立即尝试自动建立通道参考 | `POST /api/v1/devices/c6c/safety/baseline` |
| 将当前参考标记为需要重新识别 | `POST /api/v1/devices/c6c/safety/baseline/invalidate` |
| 获取 APK 使用的最近检查结果 | `GET /api/v1/devices/c6c/safety/latest` |
| 手动发起一次 VLM 安全检查 | `POST /api/v1/devices/c6c/safety/analyze` |
| 获取某次红色风险的语音 | `GET /api/v1/devices/c6c/safety/{check_id}/speech` |

正常产品流程由后台监测服务自动调用抓图和 VLM，不要求用户逐次调用 `analyze`。后台优先读取萤石移动告警，告警暂时不可用或连续 8 秒没有事件时使用本地图片变化检测。

`GET /api/v1/devices/c6c/safety/latest` 示例：

```json
{
  "analysis": {
    "risk_level": "high",
    "headline": "通道通行受阻",
    "action_text": "请尽快把纸箱移到通道外",
    "reason": "纸箱伸入近处落脚区域，经过时需要绕脚。",
    "checked_at": "2026-08-24T16:30:00+08:00",
    "check_id": "check_example",
    "hazard_regions": [
      {
        "hazard_type": "box",
        "label": "纸箱",
        "risk_level": "high",
        "x1": 420,
        "y1": 470,
        "x2": 790,
        "y2": 960
      }
    ],
    "notification_required": true,
    "speech_auto_play": true,
    "speech_url": "/api/v1/devices/c6c/safety/check_example/speech"
  }
}
```

风险框坐标范围为 0–1000，与原始图片分辨率无关。VLM 先直接输出 `event_type`：`clear`、`passage_blocked`、`fall_hazard` 或 `insufficient`。只有 `fall_hazard` 再输出低、中、高跌倒风险；后端只校验和路由该结果，不根据杂物数量或通道占用二次升降级。APK 卡片分别显示绿色“未检测到风险”、黄色“低风险”、橙色“中风险”、红色“高风险”、蓝色“通道阻塞”和灰色“画面不清楚”；颜色与文字共同表达结果，不能只依赖颜色区分。

`notification_required` 和 `speech_auto_play` 已包含同一风险去重逻辑。客户端只按返回值执行提醒，不能根据轮询次数重复播放。

## 睡眠设备与数据

| 用途 | 方法与路径 |
|---|---|
| 睡眠伴侣连通测试 | `POST /api/v1/devices/sleep/test` |
| 同步萤石单日睡眠摘要 | `POST /api/v1/devices/sleep/sync?target_date=YYYY-MM-DD` |
| 接收正式睡眠报告 | `POST /api/v1/ingest/sleep-reports` |
| 兼容旧睡眠摘要入口 | `POST /api/v1/ingest/sleep-summaries` |
| 导入本地睡眠演示数据 | `POST /api/v1/devices/sleep/demo` |
| 清除本地睡眠演示数据 | `DELETE /api/v1/devices/sleep/demo` |
| 激活演示起夜关注 | `POST /api/v1/devices/sleep/demo/night-awakening` |
| 重置演示起夜关注 | `DELETE /api/v1/devices/sleep/demo/night-awakening` |

演示数据接口只在非生产环境可用。正式睡眠报告使用 `device_serial + external_report_id` 识别唯一记录，重复推送会更新原记录。配置 `EH_SLEEP_WEBHOOK_TOKEN` 后，请求需要携带 `X-EH-Sleep-Token`。

`GET /api/v1/resident/sleep` 返回最新睡眠、同来源历史、个人基线、离床数据状态、最近同步状态和可选的 `night_awakening`。个人基线状态可为 `no_data`、`baseline_building`、`close_to_baseline`、`changed` 或 `insufficient`。演示数据与真实设备数据不会混合计算。

`night_awakening.state` 可为 `waiting`、`active` 或 `resolved`；`attention` 可为 `routine_care`、`extra_care` 或 `insufficient`。该结果用于提示近期睡眠偏离和生活照护，不表示跌倒概率。

离床事件接口没有完整返回时，`bed_exit.count` 为 `null`、`bed_exit.status` 为 `unavailable`，客户端不能显示为 0。

## LLM 与生活助手

| 用途 | 方法与路径 |
|---|---|
| 查看 LLM 配置状态 | `GET /api/v1/llm/status` |
| 测试 LLM 连接与结构化输出 | `POST /api/v1/llm/test` |
| 向小安提问 | `POST /api/v1/assistant/chat` |
| 恢复一次对话 | `GET /api/v1/assistant/conversations/{id}` |
| 确认小安建议的动作 | `POST /api/v1/assistant/actions/{id}/confirm` |

小安每轮只接收后端整理出的当前生活摘要和最近对话。联系家人的动作需要再次调用确认接口，确认后才会生成帮助请求。

## 早期兼容接口

以下接口仍保留给旧脚本或独立联调，当前 APK 自动监测流程不依赖它们：

| 用途 | 方法与路径 |
|---|---|
| 外部程序回传旧版 `clear/obstacle/insufficient` 结果 | `POST /api/v1/ingest/safety-results` |
| 保存离线试验图片与任意 JSON 标注 | `POST /api/v1/ingest/vision-samples` |

当前方案不要求训练传统目标检测模型，也不要求先上传训练图片。离线采图和 VLM 评测流程见 [视觉监测、试验数据与评测](MODEL_AND_DATA_GUIDE.md)。

## 安全配置

萤石 AppSecret、VLM/LLM API Key 和设备验证码只保存在 Windows 后端。`sdk-session` 会向同一家庭可信局域网中的 APK 返回 EZPlayer 播放所需的短期信息，AppSecret 不会发送到 APK。正式外网部署时需要增加登录、HTTPS 和设备级授权。
# 白噪音聊天动作（2026-09-05）

`POST /api/v1/assistant/chat` 返回的 `assistant_message.actions` 可包含 `kind=start_intervention`、`payload.intervention_id=white_noise_30min`。新增可选布尔字段 `payload.auto_start`：默认 false，表示用户点击播放；true 表示本轮明确要求现在播放，Android 自动调用 `POST /api/v1/assistant/actions/{id}/confirm` 后打开播放器。旧客户端忽略此字段时仍可点击播放。读取历史消息不触发自动播放；模型判断失败不授权自动播放。接口确认幂等，重复确认不会新增干预会话。
