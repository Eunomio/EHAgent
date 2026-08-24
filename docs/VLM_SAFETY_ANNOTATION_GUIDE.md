# 居家走道 VLM 离线评测标注规范 V2

本文档用于给 C6c 试验图片制作语义真值，评估视觉大模型和固定规则的判断效果。当前产品不会使用这些标签训练 RTMDet 等传统目标检测模型，也不会在运行时读取本地标签文件。

标注页面中的畅通参考图和通道区域只帮助离线脚本统一比较同一摄像头的图片。住户日常使用时，后台会自动识别通道参考画面，无需手动打开此页面。

## 1. 使用方式

在项目根目录运行 `scripts/start-annotation.ps1`，然后打开：

- 图片标注：<http://127.0.0.1:8010>
- 设置离线评测用过道区域：<http://127.0.0.1:8010/walkway>

图片标注保存在 `evidence/c6c-collection/labels.json` 和 `labels.jsonl`，离线评测用过道区域保存在 `evidence/c6c-collection/walkway.json`。

## 2. 标注原则

V2 先记录画面中可以观察到的事实，再由离线工具计算风险等级和建议动作。

人工判断：画面质量、是否有障碍物、障碍物类型、物品所在区域、占用比例、通行影响、绊倒风险和判断依据。

程序计算：`risk_level` 和 `recommended_action`。

不要根据预期风险反向修改事实字段。

## 3. V2 JSON 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `sample_id` | 字符串 | 页面自动生成的样本编号 |
| `image_path` | 字符串 | 当前截图路径 |
| `baseline_path` | 字符串 | 离线评测时用于比较的同视角畅通参考图 |
| `lighting` | 枚举 | 光线条件 |
| `visibility` | 枚举 | 画面质量 |
| `hazard_present` | 布尔值或 `null` | 有障碍、无障碍或无法确认 |
| `hazard_types` | 数组 | 障碍物类型，可多选 |
| `position_zone` | 枚举 | 物品所在区域 |
| `walkway_occupation` | 枚举 | 横向占用过道宽度比例 |
| `walkway_length_occupation` | 枚举 | 纵向占用过道长度比例 |
| `passage_effect` | 枚举 | 对通行的实际影响 |
| `trip_risk` | 枚举 | 绊倒风险 |
| `risk_level` | 枚举 | 程序自动计算 |
| `recommended_action` | 枚举 | 程序自动计算 |
| `reason` | 字符串 | 一句可观察的判断依据 |

## 4. 画面质量 `visibility`

| 值 | 判断标准 |
| --- | --- |
| `usable` | 画面清晰，过道和物品位置可以正常判断 |
| `limited` | 偏暗、轻微模糊或局部遮挡，但仍能完成主要判断 |
| `insufficient` | 严重模糊、过暗、过曝、镜头遮挡或主要过道不可见 |

选择 `insufficient` 后，障碍物状态使用 `null`，其他障碍属性使用 `unknown`。

## 5. 是否存在障碍物 `hazard_present`

| 页面选项 | JSON | 使用条件 |
| --- | --- | --- |
| 有障碍物 | `true` | 可以确认存在候选障碍物 |
| 无障碍物 | `false` | 可以确认没有需要记录的临时物品 |
| 无法确认 | `null` | 画面不足以确认 |

选择无障碍物时，`hazard_types=[]`，位置选择 `outside`，占用、通行影响和绊倒风险都选择 `none`。

## 6. 障碍物类型 `hazard_types`

| 值 | 内容 |
| --- | --- |
| `box` | 快递箱、纸箱、硬质收纳箱 |
| `bag` | 手提袋、购物袋、塑料袋、背包 |
| `shoe` | 鞋、拖鞋 |
| `stool` | 小凳、折叠凳、小型椅子 |
| `cable` | 电线、充电线、插线板线 |
| `other_obstacle` | 水桶、玩具、衣物和其他临时杂物 |

确认有障碍物时至少选择一种类型。

## 7. 物品所在区域 `position_zone`

| 值 | 判断标准 |
| --- | --- |
| `outside` | 完全位于过道区域外 |
| `boundary` | 接触边界，或只有少部分越过边界 |
| `inner_side` | 位于过道内部一侧，中央行走路线仍可使用 |
| `center` | 覆盖日常行走路线或位于过道中央 |
| `unknown` | 无法确认位置 |

物品主体已经位于过道内时选择 `inner_side` 或 `center`。

## 8. 横向占用过道宽度 `walkway_occupation`

在物品所在位置画一条横跨过道的线，用“物品占用的横向宽度 ÷ 此处过道横向宽度”判断。
不计算物品覆盖整块过道的面积，也不使用物品在画面中的面积比例。不要求计算精确像素：

| 值 | 判断标准 |
| --- | --- |
| `none` | 没有占用过道 |
| `under_quarter` | 少于过道宽度的四分之一 |
| `quarter_to_half` | 约四分之一至二分之一 |
| `over_half` | 超过一半 |
| `unknown` | 无法估计 |

## 9. 纵向占用过道长度 `walkway_length_occupation`

沿日常行走方向观察物品持续占用多长的过道路段：

| 值 | 判断标准 |
| --- | --- |
| `none` | 沿行走方向没有占用 |
| `under_quarter` | 占用可见过道长度少于四分之一 |
| `quarter_to_half` | 占用约四分之一至二分之一 |
| `over_half` | 占用超过一半，受限路段较长 |
| `unknown` | 无法估计 |

纵向长度需要与通行影响组合判断。狭窄状态持续超过一半路段时，风险至少为中风险；物品靠墙且不影响通行时，纵向较长不会单独提高风险。

## 10. 通行影响 `passage_effect`

| 值 | 判断标准 |
| --- | --- |
| `none` | 可以按原路线正常通过 |
| `narrowed` | 通道变窄，但仍可直接通过 |
| `detour` | 需要明显绕开物品 |
| `difficult` | 需要侧身、跨越或非常谨慎地移动 |
| `blocked` | 基本无法正常通过 |
| `unknown` | 无法判断 |

优先根据正常行走动作选择，不根据物品类别直接决定。

## 11. 绊倒风险 `trip_risk`

| 值 | 判断标准 |
| --- | --- |
| `none` | 物品明显可见，位置不会影响落脚 |
| `possible` | 位于落脚区域、较低矮或经过时需要留意 |
| `obvious` | 电线横跨路线、小物品难发现或存在明显跨越动作 |
| `unknown` | 无法确认 |

纸箱位于行走路线中央时通常选择 `possible`；电线横跨主要路线通常选择 `obvious`。

## 12. 离线标签风险规则

标注工具按照以下顺序生成标签中的 `risk_level` 和 `recommended_action`，较高等级优先：

- `insufficient`：画面无法判断，或无法确认是否有障碍物。动作 `recheck`。
- `high`：通行困难/堵塞、占用超过一半、明显绊倒风险，或同图存在两种以上障碍物。动作 `remind_resident`。
- `medium`：需要绕开、横向占用四分之一至一半、存在潜在绊倒风险、物品位于中央，或纵向超过一半且通道持续变窄。动作 `create_task`。
- `low`：通道轻微变窄、占用少于四分之一、物品位于边界/内侧，或画面质量有限。动作 `recheck`。
- `clear`：画面清晰且无障碍；或物品在过道外且没有影响。动作 `record_clear`。

产品自动监测还会使用 VLM 返回的风险框与近处通道开口计算重叠比例。风险框覆盖通道宽度 25% 以上时至少按需要整改处理，覆盖 50% 以上时按严重风险处理。模型文字与几何位置冲突时，产品使用重叠结果校正最终状态。因此，离线标签规则一致率和产品最终风险评测需要分别记录。

## 13. 完整示例

畅通：

```json
{"sample_id":"c6c01_day_baseline_0001","image_path":"c6c01/c6c01_day_baseline_20260820_093000_000.jpg","baseline_path":"c6c01/c6c01_day_baseline_20260820_093000_000.jpg","lighting":"day","visibility":"usable","hazard_present":false,"hazard_types":[],"position_zone":"outside","walkway_occupation":"none","walkway_length_occupation":"none","passage_effect":"none","trip_risk":"none","risk_level":"clear","recommended_action":"record_clear","reason":"走道内没有临时物品，通行区域完整。"}
```

少量占用，需要绕开：

```json
{"sample_id":"c6c01_day_box_0001","image_path":"c6c01/c6c01_day_box_20260820_101500_000.jpg","baseline_path":"c6c01/c6c01_day_baseline_20260820_093000_000.jpg","lighting":"day","visibility":"usable","hazard_present":true,"hazard_types":["box"],"position_zone":"inner_side","walkway_occupation":"under_quarter","walkway_length_occupation":"under_quarter","passage_effect":"detour","trip_risk":"possible","risk_level":"medium","recommended_action":"create_task","reason":"纸箱位于过道内侧，占用少量空间，经过时需要绕开。"}
```

无法判断：

```json
{"sample_id":"c6c01_dim_clear_0001","image_path":"c6c01/c6c01_dim_clear_20260820_190000_000.jpg","baseline_path":"c6c01/c6c01_day_baseline_20260820_093000_000.jpg","lighting":"dim","visibility":"insufficient","hazard_present":null,"hazard_types":[],"position_zone":"unknown","walkway_occupation":"unknown","walkway_length_occupation":"unknown","passage_effect":"unknown","trip_risk":"unknown","risk_level":"insufficient","recommended_action":"recheck","reason":"画面过暗，无法确认走道内是否存在障碍物。"}
```

## 14. 独立评测视觉大模型

重新完成 V2 标注后运行：

```powershell
.\.venv\Scripts\python.exe .\scripts\test-vlm-safety.py --model ecnu-plus --all
```

脚本默认使用 ECNU `chat/completions` 多模态接口和 `response_format=json_schema`，读取 `.env` 中的 `EH_LLM_API_KEY`、`EH_LLM_API_BASE` 和 `EH_LLM_MODEL`；`--model` 可以临时覆盖模型名。结果保存在 `evidence/vlm-experiments/<时间>/results.json`。

没有障碍物或无法确认时，不评测位置、占用、通行影响和绊倒风险。评测结果以总体字段一致率和各字段一致率为主，不要求每张图片所有字段完全相同才计为有效；高风险漏检和边缘安全物品误整改需要单独统计。
