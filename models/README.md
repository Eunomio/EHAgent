# 模型目录

当前通道安全功能通过远程视觉大模型完成图片理解，模型名和服务地址由 Windows 后端 `.env` 配置：

```dotenv
EH_VLM_ENABLED=true
EH_VLM_MODEL=ecnu-plus
EH_VLM_API_BASE=https://chat.ecnu.edu.cn/open/api/v1
EH_VLM_API_KEY=你的APIKey
```

当前版本不加载本地 RTMDet、ONNX 或 COCO 权重，仓库也不需要保存传统目标检测模型文件。通道位置、通行影响、绊倒风险和风险框由 VLM 输出，再由 `app/vision` 中的固定规则校正风险等级。

`models/` 目录暂时只保留为以后本地模型试验或模型交付的预留位置。若以后确实引入本地模型，应在独立方案中补充模型卡、适用摄像头、数据来源、评测结果和回退方式，不能直接替换当前线上流程。

当前数据采集与评测方法见 [视觉监测、试验数据与评测](../docs/MODEL_AND_DATA_GUIDE.md)。
