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
| 接收睡眠摘要 | `POST /api/v1/ingest/sleep-summaries` |
| 接收模型判断 | `POST /api/v1/ingest/safety-results` |
| 上传训练图片 | `POST /api/v1/ingest/vision-samples` |

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

