# 居安 Agent

面向独居和居家养老场景的 Android 应用。住户可以查看通道安全、睡眠与身体趋势、联系家人，并通过萤石 C6c 查看家中通道。Windows 本地服务负责连接设备、自动检查画面、保存任务状态以及调用视觉和语音服务。

当前 Android 版本为 `0.10.3`，支持 Android 8.0 及以上系统。

## 当前功能

### 通道安全

- 通过萤石 Android SDK 和 EZPlayer 播放 C6c 实时画面，支持 H.264/H.265 设备取流
- 实时画面支持横向全屏，摄像头操控杆位于全屏右下角
- 后台自动识别可正常通行的参考画面，住户无需手动设置基准图
- 每 2 秒查询萤石移动告警，发现画面活动后自动抓图并检查
- 萤石告警接口超时或暂时不可用时，自动使用本地图片变化检测
- 视觉大模型分别判断剩余通行空间和绊倒风险，通道边缘且不影响行走的日常物品保持安全状态
- 使用实际通道开口与物品风险框的重叠比例，纠正“纸箱位于边缘”等与画面位置冲突的结论
- 绿色表示通道安全，黄色表示潜在风险，红色表示需要整改
- 在普通画面和横向全屏画面中显示黄色或红色风险框
- 红色风险生成具体整改建议，并发送系统通知和自动播放中文语音
- 同一风险只提醒一次；风险升级后再次提醒
- 支持“我已整理好”立即复查、“30 分钟后提醒”和请求家人协助
- 摄像头角度明显变化后隐藏旧风险框，并自动重新识别通道

### 睡眠与生活协助

- 接收无感睡眠伴侣的睡眠报告、心率、呼吸频率、睡眠构成、得分和时序采样
- 展示睡眠时长、平均/最低/最高心率、平均/最低/最高呼吸频率等数据
- 使用至少 8 晚同来源记录建立个人睡眠基线，并展示与个人平时相比的变化
- 支持带可靠来源的起夜关注状态；真实事件接口没有可用数据时明确显示暂未取得，不用 0 补齐
- 全局“小安”生活助手支持家庭信息问答、一般生活问答、语音输入、回答朗读、公开来源和动作确认
- VLM 提供通道可见原因，固定规则生成整改建议；LLM 负责睡眠小结、反馈摘要和生活助手
- 支持联系家人、家属协助请求、设备状态和隐私设置

真实睡眠记录始终优先展示。开发环境的空数据库在 Android 首次连接时会自动导入仓库内置的 8 晚非敏感演示数据，并明确保存为 `source=demo_generated`；“我的”页面可清除或重新导入。生产环境禁止演示数据接口，设备尚未连接或数据尚未同步时显示空状态。

## 系统组成

```text
萤石 C6c / 睡眠设备
        ↓
Windows 本地 Agent（FastAPI、设备连接、视觉检查、任务与语音）
        ↓ 局域网
Android 居安 APK（实时画面、风险提醒、处理与复查）
```

萤石 AppKey、AppSecret、设备验证码及大模型 API Key 只保存在 Windows 电脑的 `.env` 中。APK 保存本地服务地址，并在播放实时画面时向本地服务取得临时播放会话。

当前视觉方案直接调用 VLM，并由后端固定规则校正风险等级。无需下载 RTMDet、标注 CVAT 检测框、训练传统目标检测模型或导出 ONNX；本地采图和语义标注工具只用于离线评测。

## 快速开始

### 1. 配置并启动 Windows 服务

安装 Python 3.11，在仓库根目录运行：

```powershell
Copy-Item .env.example .env
.\scripts\start-backend.ps1
```

在 `.env` 中填写萤石应用和 C6c 信息：

```dotenv
EH_EZVIZ_APP_KEY=你的AppKey
EH_EZVIZ_APP_SECRET=你的AppSecret
EH_EZVIZ_DEVICE_SERIAL=设备序列号
EH_EZVIZ_CHANNEL_NO=1
EH_EZVIZ_VERIFY_CODE=设备验证码
EH_EZVIZ_AUTO_TOKEN=true
```

启用视觉检查和红色风险语音：

```dotenv
EH_VLM_ENABLED=true
EH_VLM_API_KEY=你的APIKey
EH_VLM_MODEL=ecnu-plus
EH_VLM_API_BASE=https://chat.ecnu.edu.cn/open/api/v1
EH_VLM_AUTO_CHECK_ENABLED=true

EH_TTS_ENABLED=true
EH_TTS_MODEL=ecnu-tts
EH_TTS_VOICE=liwa
EH_TTS_SPEED=0.9
```

如需启用生活助手和文案整理，可继续配置：

```dotenv
EH_LLM_ENABLED=true
EH_LLM_PROVIDER=openai
EH_LLM_API_KEY=你的APIKey
EH_LLM_MODEL=gpt-5.4-nano
EH_LLM_API_BASE=https://api.openai.com/v1
EH_ASSISTANT_WEB_SEARCH_ENABLED=true
EH_ASSISTANT_LOCATION=上海市
```

服务启动后，在电脑浏览器打开 `http://127.0.0.1:8000/docs` 查看接口。使用 `ipconfig` 查询电脑的局域网 IPv4 地址，例如 `192.168.1.10`。

### 2. 安装 APK

打开 GitHub 仓库的 `Actions` → `Android APK` → 最近一次成功任务，在 `Artifacts` 下载 `EHAgent-resident-debug-apk`。解压后将 `app-debug.apk` 安装到安卓手机。

也可以使用 Android Studio 打开 `android` 目录，运行 `app` 或选择 `Build APK(s)`。

### 3. 连接手机

1. 手机和 Windows 电脑连接同一个 Wi-Fi。
2. 打开“居安”，进入“我的”。
3. 在“家庭服务连接”中填写 `http://电脑IPv4地址:8000`。
4. 点击“保存并连接”。首页显示设备状态后即可使用。

Android 模拟器使用 `http://10.0.2.2:8000`。如果真机无法连接，请确认 Windows 服务使用 `0.0.0.0:8000` 启动，并允许 Python 或 8000 端口通过 Windows 防火墙。

## 自动通道检查流程

```text
萤石移动告警
→ 等待画面稳定并抓取当前图片
→ 与后台自动保存的通道参考画面比较
→ 视觉大模型返回通行影响、绊倒风险、物品类型和风险框
→ 固定规则结合真实通道边界确定绿、黄、红等级
→ APK 刷新风险框、原因和整改建议
→ 红色风险发送通知并自动播放语音
→ 住户整理后复查，确认通道恢复安全
```

连续 8 秒没有收到可用的萤石告警时，服务会执行本地画面变化检测。短暂经过的人影或光线闪动需要连续确认后才触发视觉分析，减少重复调用和误提醒。

## 开发与验证

后端检查：

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m pytest tests -q
```

Android 构建：

```powershell
cd android
.\gradlew.bat :app:assembleDebug
```

GitHub Actions 会在代码推送到 `main` 后自动构建 APK。当前 workflow 使用 Java 17、Gradle 8.13 和 Android Gradle Plugin 8.13.2。

## 文档

- [比赛期产品需求文档 PRD v1.9](docs/比赛期产品需求文档_PRD_v1.9.md)
- [萤石 C6c 接入与调试](docs/DEVICE_INTEGRATION.md)
- [视觉监测、试验数据与评测](docs/MODEL_AND_DATA_GUIDE.md)
- [后端接口说明](docs/API.md)
- [LLM 模块 PRD](docs/PRD_LLM_MODULE.md)

## 目录

```text
android/       Android 住户端
app/           Windows 本地 FastAPI 服务
scripts/       启动、采图和数据处理脚本
tests/         后端自动化测试
docs/          产品、设备、模型和接口文档
models/        模型交付约定
```
