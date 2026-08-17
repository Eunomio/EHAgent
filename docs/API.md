# 后端接口

默认地址为 `http://电脑IP:8000`，交互文档位于 `/docs`。

| 用途 | 方法与路径 |
|---|---|
| 服务状态 | `GET /api/v1/health` |
| 老人首页 | `GET /api/v1/resident/dashboard` |
| 通道安全 | `GET /api/v1/resident/safety` |
| 处理安全提醒 | `POST /api/v1/resident/safety/tasks/{id}/actions` |
| 睡眠详情 | `GET /api/v1/resident/sleep` |
| 联系家人 | `POST /api/v1/resident/help` |
| 隐私与联系人设置 | `GET/PUT /api/v1/resident/settings` |
| 设备状态 | `GET /api/v1/devices` |
| C6c 连通测试 | `POST /api/v1/devices/c6c/test` |
| C6c 抓图 | `POST /api/v1/devices/c6c/capture` |
| 获取C6c临时HLS直播地址 | `POST /api/v1/devices/c6c/live` |
| 获取C6c安卓SDK播放会话 | `POST /api/v1/devices/c6c/sdk-session` |
| 接收正式睡眠报告 | `POST /api/v1/ingest/sleep-reports` |
| 兼容旧睡眠摘要地址 | `POST /api/v1/ingest/sleep-summaries` |
| 接收模型判断 | `POST /api/v1/ingest/safety-results` |
| 上传训练图片 | `POST /api/v1/ingest/vision-samples` |
| 提交老人反馈 | `POST /api/v1/resident/feedback` |
| 查看老人反馈摘要 | `GET /api/v1/resident/feedback` |
| 查看LLM配置状态 | `GET /api/v1/llm/status` |
| 测试LLM连接与结构化输出 | `POST /api/v1/llm/test` |
| 向小安提问 | `POST /api/v1/assistant/chat` |
| 恢复一次对话 | `GET /api/v1/assistant/conversations/{id}` |
| 确认小安建议的动作 | `POST /api/v1/assistant/actions/{id}/confirm` |

模型结果示例：

```json
{
  "result": "obstacle",
  "source": "model",
  "location": "卧室外走道",
  "object_name": "纸箱",
  "detail": "纸箱占用了老人常走区域",
  "suggestion": "请将纸箱移到墙边收纳区",
  "evidence_url": "https://example.invalid/evidence.jpg"
}
```

`result` 可为 `clear`、`obstacle` 或 `insufficient`。画面遮挡、过暗或无法判断时发送 `insufficient`，产品只记录检查，不提醒老人整理。

当`result`为`obstacle`时，Windows Agent调用LLM生成`title`、`explanation`和`suggestion`。LLM不能修改`result`。未配置Key、超时或返回格式错误时，返回内容中的`language.source`为`template`。

睡眠数据写入后会生成`analysis.content.summary`；老人反馈同时保留`message`原文和`summary`摘要。

正式睡眠报告使用`device_serial + external_report_id`识别平台中的唯一报告。重复推送会更新原记录。配置`EH_SLEEP_WEBHOOK_TOKEN`后，请求必须携带`X-EH-Sleep-Token`。萤石设备报告缺少`device_serial`返回422，与后端绑定的设备序列号不一致返回409。住户接口不会返回设备序列号和平台报告编号。

安卓端只在老人主动查看时调用`POST /api/v1/devices/c6c/sdk-session`。接口返回EZPlayer初始化所需的AppKey、AccessToken、设备序列号、通道号和播放验证码，AppSecret始终留在后端；暂停通道检查后接口返回409。当前项目用于同一家庭可信局域网联调，正式外网部署时需要在该接口前增加用户登录、HTTPS和设备级授权。

`POST /api/v1/devices/c6c/live`保留给电脑端排查标准HLS直播地址，安卓产品界面不再使用该地址播放。

小安每轮只接收后端整理出的当前生活摘要和最近对话。`POST /api/v1/assistant/chat`返回本人消息、小安回答、使用过的家庭信息名称、公开来源和待确认动作。天气、新闻、政策、交通和近期诈骗信息等时效问题会按需联网查询。联系家人的动作必须再调用确认接口才会生成帮助请求。
