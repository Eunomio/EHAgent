# 居安 Agent

面向独居和居家养老场景的 Android 产品框架。老人端提供通道安全、睡眠、心率、呼吸频率和联系家人功能；本地 FastAPI 服务负责连接萤石设备、保存数据和接收视觉模型结果。

当前版本为 `0.8.0`，旧版网页界面已经移除。页面不会自动生成健康数据，未连接设备时会明确显示“等待连接”或“暂未同步”。

## 已完成

- 原生 Kotlin + Jetpack Compose 老人端，支持 Android 8.0 及以上系统
- 首页、安全、睡眠、联系家人、设备状态和隐私开关
- 睡眠时长、平均/最低/最高心率、平均/最低/最高呼吸频率、离床次数和时序采样的数据结构
- 萤石 C6c 状态检查和抓图接口
- 居家安全页通过萤石 Android SDK 和 EZPlayer 查看C6c实时画面，支持H.264/H.265设备取流，离开页面后自动关闭
- 无感睡眠助手设备绑定与正式报告接收，支持心率、呼吸频率、睡眠构成、得分和时序采样
- 通道障碍物判断结果、老人处理动作和家人协助请求
- 训练图片与标注上传接口
- LLM生成通道整改建议、睡眠小结和老人反馈摘要，未配置时自动使用模板
- 全局“小安”生活助手，支持家庭信息问答、一般生活问答、语音输入、回答朗读、公开来源和动作确认
- GitHub Actions 自动构建可安装 APK

萤石 AppKey、AppSecret 和设备验证码写在家中电脑的 `.env`。AppSecret始终由后端保管；APK只保存本地服务地址，并在打开画面时取得SDK播放会话，无需 Engineering API key。

LLM API Key同样只写在Windows后端`.env`。启用OpenAI Responses API示例：

```dotenv
EH_LLM_ENABLED=true
EH_LLM_PROVIDER=openai
EH_LLM_API_KEY=你的APIKey
EH_LLM_MODEL=gpt-5.4-nano
EH_LLM_API_BASE=https://api.openai.com/v1
EH_ASSISTANT_WEB_SEARCH_ENABLED=true
EH_ASSISTANT_LOCATION=上海市
```

重启后端后，在`http://127.0.0.1:8000/docs`调用`POST /api/v1/llm/test`。返回`source: llm`表示连接成功；返回`source: template`时，产品仍会使用固定模板完成安全、睡眠和反馈流程。`EH_ASSISTANT_LOCATION`填写老人所在城市，便于回答天气和本地生活问题，无需填写家庭详细地址。

## 快速使用

### 1. 启动家中电脑服务

安装 Python 3.11 后，在仓库根目录运行：

```powershell
Copy-Item .env.example .env
.\scripts\start-backend.ps1
```

启动成功后，在电脑浏览器打开 `http://127.0.0.1:8000/docs` 可查看接口。用 `ipconfig` 找到电脑局域网 IPv4 地址，例如 `192.168.1.10`。

### 2. 安装 APK

在 GitHub 仓库打开 `Actions` → `Android APK` → 最近一次成功任务，在 `Artifacts` 下载 `EHAgent-resident-debug-apk`，解压后把 APK 发到安卓手机安装。

也可用 Android Studio 打开 `android` 目录，运行 `app` 或选择 `Build APK(s)`。

### 3. 连接手机

1. 手机和电脑连接同一个 Wi-Fi。
2. 打开“居安”，选择“我的”。
3. 在“家庭服务连接”填写 `http://电脑IPv4地址:8000`。
4. 点“保存并连接”。首页出现设备状态后即可使用。

Android 模拟器使用 `http://10.0.2.2:8000`。

## 接入设备

- [萤石 C6c 接入与调试](docs/DEVICE_INTEGRATION.md)
- [基础模型、采集数据与上传方法](docs/MODEL_AND_DATA_GUIDE.md)
- [后端接口说明](docs/API.md)
- [比赛期完整PRD](docs/比赛期产品需求文档_PRD_v1.8.md)
- [LLM模块PRD](docs/PRD_LLM_MODULE.md)

## 目录

```text
android/       老人端 Android 应用
app/           本地 FastAPI 服务
scripts/       启动与数据发送脚本
tests/         后端自动化测试
docs/          设备、模型和接口文档
models/        模型交付约定
```
