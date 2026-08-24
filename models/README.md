# 模型交付目录

## RTMDet-tiny 预训练模型

官方 COCO 预训练权重保存在：

```text
models/pretrained/rtmdet_tiny_8xb32-300e_coco.pth
```

训练环境单独安装在 `.venv-rtmdet`，与后端 `.venv` 隔离。验证 GPU 和 OpenMMLab 环境：

```powershell
.\.venv-rtmdet\Scripts\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
.\.venv-rtmdet\Scripts\python.exe -c "import mmcv, mmengine, mmdet; print(mmcv.__version__, mmengine.__version__, mmdet.__version__)"
```

该权重仍输出 COCO 的 80 类，只用于初始化训练。完成六类别微调后，再把最终 ONNX 和标签文件交付到 `models/safety/`。

训练完成后建议按以下结构交付，模型文件不提交到 Git：

```text
models/safety/
  model.onnx
  labels.json
  model-card.md
  metrics.json
```

`model-card.md` 写明训练数据日期、相机视角、适用场景和已知误差；`metrics.json` 至少记录独立测试集召回率、误报率和夜视结果。训练与数据要求见 `docs/MODEL_AND_DATA_GUIDE.md`。
