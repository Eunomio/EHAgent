# 模型交付目录

训练完成后建议按以下结构交付，模型文件不提交到 Git：

```text
models/safety/
  model.onnx
  labels.json
  model-card.md
  metrics.json
```

`model-card.md` 写明训练数据日期、相机视角、适用场景和已知误差；`metrics.json` 至少记录独立测试集召回率、误报率和夜视结果。训练与数据要求见 `docs/MODEL_AND_DATA_GUIDE.md`。
