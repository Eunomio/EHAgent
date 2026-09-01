import json
from typing import Any, Literal, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SafetyCopy(StrictOutput):
    title: str = Field(min_length=1, max_length=40)
    explanation: str = Field(min_length=1, max_length=160)
    suggestion: str = Field(min_length=1, max_length=120)


class SleepCopy(StrictOutput):
    summary: str = Field(min_length=1, max_length=220)
    attention: bool
    question: str | None = Field(default=None, max_length=80)


class FeedbackDigest(StrictOutput):
    summary: str = Field(min_length=1, max_length=160)
    category: str = Field(pattern="^(product|safety|sleep|help|other)$")
    needs_follow_up: bool


class ProfileFactCandidate(StrictOutput):
    fact_type: str = Field(
        pattern=(
            "^(fall_experience|near_fall_experience|fall_concern|activity_avoidance|health_condition|"
            "daily_preference|interaction_preference|routine_preference)$"
        )
    )
    display_text: str = Field(min_length=2, max_length=80)
    evidence_quote: str = Field(min_length=1, max_length=120)
    confidence: float = Field(ge=0, le=1)
    memory_mode: Literal["confirm", "inferred"] = "confirm"


class ProfileFactExtraction(StrictOutput):
    facts: list[ProfileFactCandidate] = Field(default_factory=list, max_length=3)


DeviceToolName = Literal[
    "none",
    "inspect_home_safety",
    "camera_status",
    "read_latest_sleep",
    "sync_latest_sleep",
    "camera_pause",
    "camera_resume",
    "sleep_pause",
    "sleep_resume",
    "care_pause",
    "care_resume",
]


class DeviceToolDecision(StrictOutput):
    tool_name: DeviceToolName
    reason: str = Field(min_length=1, max_length=120)
    confidence: float = Field(ge=0, le=1)


OutputT = TypeVar("OutputT", bound=StrictOutput)


class LlmService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=settings.llm_timeout_seconds)
        self._owns_client = client is None

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.llm_enabled
            and self.settings.llm_provider == "openai"
            and self.settings.llm_api_key
            and self.settings.llm_model
        )

    @property
    def model_name(self) -> str:
        return self.settings.llm_model if self.configured else "template"

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def explain_safety(
        self, location: str, object_name: str, detail: str
    ) -> tuple[SafetyCopy, str]:
        fallback = SafetyCopy(
            title=f"走道中有{object_name}",
            explanation=f"{location}发现{object_name}，可能影响通行。",
            suggestion=f"建议将{object_name}移到走道外。",
        )
        prompt = {
            "confirmed_result": "obstacle",
            "location": location,
            "object_name": object_name,
            "model_detail": detail,
        }
        generated, source = await self._generate(
            "safety_copy",
            SafetyCopy,
            prompt,
            fallback,
            "把已经确认的通道障碍结果改写为老人易懂的中文。保持结论不变，只说明位置、物品和一个具体动作。不要提模型、概率、ROI或诊断。",
        )
        return generated.model_copy(update={"title": fallback.title}), source

    async def analyze_sleep(
        self, latest: dict[str, Any], history: list[dict[str, Any]]
    ) -> tuple[SleepCopy, str]:
        duration = int(latest["duration_minutes"])
        parts = [f"昨晚共睡眠{duration // 60}小时{duration % 60}分钟。"]
        if latest.get("respiratory_rate") is not None:
            parts.append(f"平均呼吸频率{latest['respiratory_rate']}次/分。")
        if latest.get("heart_rate") is not None:
            parts.append(f"平均心率{latest['heart_rate']}次/分。")
        attention = self._sleep_attention(history)
        fallback = SleepCopy(
            summary="".join(parts),
            attention=attention,
            question="最近睡眠变化比较明显，今天感觉怎么样？" if attention else None,
        )
        prompt = {
            "latest_night": self._sleep_fields(latest),
            "recent_nights": [self._sleep_fields(item) for item in history[:7]],
            "rule_attention": attention,
        }
        generated, source = await self._generate(
            "sleep_copy",
            SleepCopy,
            prompt,
            fallback,
            "根据提供的真实睡眠记录生成简短中文总结。只描述数值和与近期记录的变化，不判断正常异常，不诊断疾病，不补充缺失数据。保持rule_attention不变。",
        )
        return generated.model_copy(
            update={
                "attention": attention,
                "question": generated.question if attention else None,
            }
        ), source

    async def summarize_feedback(
        self, topic: str, message: str
    ) -> tuple[FeedbackDigest, str]:
        category = topic if topic in {"product", "safety", "sleep", "help"} else "other"
        follow_up_words = ("帮忙", "求助", "摔", "跌倒", "疼", "不舒服", "危险", "诈骗")
        needs_follow_up = topic in {"safety", "help"} or any(
            word in message for word in follow_up_words
        )
        fallback = FeedbackDigest(
            summary=message[:160], category=category, needs_follow_up=needs_follow_up
        )
        generated, source = await self._generate(
            "feedback_digest",
            FeedbackDigest,
            {"topic": topic, "resident_message": message},
            fallback,
            "整理老人原话供家属或工作人员查看。保留原意，使用简短中文，不添加事实。涉及求助、安全或身体不适时needs_follow_up设为true。",
        )
        return generated.model_copy(
            update={"needs_follow_up": generated.needs_follow_up or needs_follow_up}
        ), source

    async def extract_profile_facts(
        self, message: str
    ) -> tuple[ProfileFactExtraction, str]:
        """Extract explicit sensitive facts for consent and low-risk preferences for memory."""

        fallback = self._profile_fact_fallback(message)
        generated, source = await self._generate(
            "profile_fact_extraction",
            ProfileFactExtraction,
            {"resident_message": message},
            fallback,
            (
                "从老人本人的一句话中提取可以帮助后续交流的事实。跌倒经历、近跌倒、跌倒担忧和"
                "活动回避必须设为confirm，等待本人确认。低敏感度的生活偏好、交流偏好和重复出现的"
                "日常习惯可以设为inferred，用于无感记忆。老人明确说出的本人确诊疾病可设为"
                "health_condition和confirm，但不得根据症状、设备数据或语气推断疾病。"
                "不要把亲友跌倒当成本人经历，不根据睡眠或语气推断，不诊断焦虑，不提取否定句。"
                "不得无感记录疾病、用药、精确住址、财务、宗教、身份号码、联系人或家庭矛盾；这些"
                "敏感信息不要作为inferred输出。一次性的当下行为也不是稳定偏好。"
                "display_text用老人能看懂的简短中文，evidence_quote必须来自原话。没有明确事实时返回空列表。"
            ),
        )
        return generated, source

    async def plan_device_tool(
        self, message: str, device_state: dict[str, Any]
    ) -> tuple[DeviceToolDecision, str]:
        """Use the language model to map natural language onto one device tool."""

        fallback = self._device_tool_fallback(message)
        generated, source = await self._generate(
            "device_tool_decision",
            DeviceToolDecision,
            {
                "resident_message": message,
                "connected_device_state": device_state,
                "available_tools": {
                    "inspect_home_safety": "抓取摄像头当前画面并用VLM检查居家通道",
                    "camera_status": "查询摄像头是否在线",
                    "read_latest_sleep": "读取已经同步的最近一次睡眠记录",
                    "sync_latest_sleep": "从睡眠助手同步昨晚数据",
                    "camera_pause": "暂停通道摄像头分析",
                    "camera_resume": "恢复通道摄像头分析",
                    "sleep_pause": "暂停睡眠提醒",
                    "sleep_resume": "恢复睡眠提醒",
                    "care_pause": "暂停主动关怀",
                    "care_resume": "恢复主动关怀",
                    "none": "本轮不需要调用设备",
                },
            },
            fallback,
            (
                "你是居家助手的设备工具规划器。根据老人自然语言表达的目标选择最多一个工具。"
                "按语义判断，不要求用户说出设备名。例如‘帮我看看家里现在怎么样’应选择"
                "inspect_home_safety；询问昨晚睡得怎样选择read_latest_sleep；明确要求更新昨晚"
                "数据才选择sync_latest_sleep。闲聊、健康解释和无法由现有工具完成的请求选择none。"
                "用户说‘看摄像头’或‘看看家里’时选择inspect_home_safety；只有单纯询问摄像头"
                "是否已经连接、是否在线时才选择camera_status。"
                "不要因为上下文中存在设备就擅自调用；只有用户本轮表达了查看或控制意图才调用。"
            ),
        )
        return generated, source

    async def chat_assistant(
        self,
        message: str,
        context: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, str]], str]:
        fallback = self._assistant_fallback(message, context)
        if not self.configured:
            return fallback, [], "template"

        conversation = [
            {"role": item["role"], "content": item["content"]}
            for item in history[-10:]
        ]
        request_body: dict[str, Any] = {
            "model": self.settings.llm_model,
            "instructions": (
                "你叫小安，是面向老年人的中文生活助手。回答直接、温和、具体，优先使用短句。"
                "可以回答一般生活问题，也可以使用提供的当前生活信息。只引用其中真实存在的数据，不补充缺失数值。"
                "涉及天气、新闻、政策、交通、诈骗案例等会变化的信息时使用联网搜索。"
                "不要展示模型、接口或内部处理过程。不要把健康数据解释成诊断。"
                "如果用户描述胸痛、呼吸困难、失去意识或正在跌倒等紧急情况，先建议立即呼叫急救并联系身边的人。"
                "涉及联系家人时只说明可以协助，等待产品提供确认按钮。"
                "涉及设备状态时不要自行声称已经执行；产品会根据已保存的一次性授权执行，"
                "或在尚未选择权限时提供按钮。"
                "如果current_life_context包含device_tool_result，说明设备工具已经真实执行；"
                "必须优先依据其中的summary和data回答，不要再说自己看不到画面或无法访问设备。"
            ),
            "input": json.dumps(
                {
                    "current_life_context": context,
                    "recent_conversation": conversation,
                    "resident_message": message,
                },
                ensure_ascii=False,
            ),
            "max_output_tokens": self.settings.llm_max_output_tokens,
        }
        if self.settings.assistant_web_search_enabled:
            request_body["tools"] = [{"type": "web_search"}]

        try:
            response = await self.client.post(
                f"{self.settings.llm_api_base.rstrip('/')}/responses",
                headers={
                    "Authorization": f"Bearer {self.settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json=request_body,
            )
            response.raise_for_status()
            payload = response.json()
            return self._output_text(payload), self._output_sources(payload), "llm"
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return fallback, [], "template"

    async def _generate(
        self,
        name: str,
        output_type: type[OutputT],
        content: dict[str, Any],
        fallback: OutputT,
        instruction: str,
    ) -> tuple[OutputT, str]:
        if not self.configured:
            return fallback, "template"
        schema = output_type.model_json_schema()
        try:
            response = await self.client.post(
                f"{self.settings.llm_api_base.rstrip('/')}/responses",
                headers={
                    "Authorization": f"Bearer {self.settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.settings.llm_model,
                    "instructions": instruction,
                    "input": json.dumps(content, ensure_ascii=False),
                    "max_output_tokens": self.settings.llm_max_output_tokens,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": name,
                            "strict": True,
                            "schema": schema,
                        }
                    },
                },
            )
            response.raise_for_status()
            parsed = output_type.model_validate_json(self._output_text(response.json()))
            return parsed, "llm"
        except (httpx.HTTPError, KeyError, TypeError, ValueError, ValidationError):
            return fallback, "template"

    @staticmethod
    def _output_text(payload: dict[str, Any]) -> str:
        for item in payload.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    return str(content["text"])
        raise ValueError("LLM response did not contain output text")

    @staticmethod
    def _output_sources(payload: dict[str, Any]) -> list[dict[str, str]]:
        sources: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in payload.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                for annotation in content.get("annotations", []):
                    if annotation.get("type") != "url_citation":
                        continue
                    url = str(annotation.get("url") or "")
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    sources.append({
                        "title": str(annotation.get("title") or "查看来源"),
                        "url": url,
                    })
        return sources[:5]

    @staticmethod
    def _assistant_fallback(message: str, context: dict[str, Any]) -> str:
        tool_result = context.get("device_tool_result")
        if isinstance(tool_result, dict) and tool_result.get("summary"):
            return str(tool_result["summary"])
        sleep = context.get("latest_sleep")
        safety = context.get("open_safety_task")
        if any(word in message for word in ("睡", "心率", "呼吸")) and sleep:
            minutes = int(sleep["duration_minutes"])
            parts = [f"最近一次睡眠共{minutes // 60}小时{minutes % 60}分钟。"]
            if sleep.get("heart_rate") is not None:
                parts.append(f"平均心率{sleep['heart_rate']}次/分。")
            if sleep.get("respiratory_rate") is not None:
                parts.append(f"平均呼吸{sleep['respiratory_rate']}次/分。")
            return "".join(parts)
        if any(word in message for word in ("安全", "走道", "摄像头")):
            if safety:
                return f"当前有一条提醒：{safety['explanation']} {safety['suggestion']}"
            return "当前没有待处理的居家安全提醒。您也可以到“居家安全”查看实时画面。"
        if "联系" in message and "家人" in message:
            return "可以，我会先请您确认，确认后再通知家人联系您。"
        return "我现在可以回答家中的安全和睡眠情况。其他生活问题暂时无法查询，请稍后再试。"

    @staticmethod
    def _device_tool_fallback(message: str) -> DeviceToolDecision:
        compact = message.strip()
        semantic_rules: tuple[tuple[tuple[str, ...], DeviceToolName, str], ...] = (
            (
                (
                    "看看家里", "家里怎么样", "我家现在怎么样", "查看家里",
                    "看看摄像头", "看下摄像头", "看我的摄像头", "看摄像头",
                    "摄像头画面", "看看通道",
                ),
                "inspect_home_safety",
                "用户希望查看当前居家画面或环境",
            ),
            (("摄像头在线", "摄像头连", "摄像头状态"), "camera_status", "用户询问摄像头连接状态"),
            (("同步睡眠", "更新睡眠", "重新获取睡眠"), "sync_latest_sleep", "用户要求从睡眠助手同步数据"),
            (
                ("昨晚睡", "睡眠怎么样", "睡得怎么样", "看看睡眠", "睡眠数据"),
                "read_latest_sleep",
                "用户希望了解最近睡眠记录",
            ),
            (("暂停摄像头", "关闭摄像头", "停止通道检查", "暂停通道检查"), "camera_pause", "用户要求暂停通道检查"),
            (("打开摄像头", "恢复摄像头", "开启通道检查", "恢复通道检查"), "camera_resume", "用户要求恢复通道检查"),
            (("暂停睡眠提醒", "关闭睡眠提醒"), "sleep_pause", "用户要求暂停睡眠提醒"),
            (("开启睡眠提醒", "打开睡眠提醒", "恢复睡眠提醒"), "sleep_resume", "用户要求恢复睡眠提醒"),
            (("暂停主动关怀", "关闭主动关怀"), "care_pause", "用户要求暂停主动关怀"),
            (("开启主动关怀", "恢复主动关怀"), "care_resume", "用户要求恢复主动关怀"),
        )
        for phrases, tool_name, reason in semantic_rules:
            if any(phrase in compact for phrase in phrases):
                return DeviceToolDecision(
                    tool_name=tool_name, reason=reason, confidence=0.8
                )
        return DeviceToolDecision(
            tool_name="none", reason="本轮没有明确的设备查看或控制意图", confidence=0.7
        )

    @staticmethod
    def _profile_fact_fallback(message: str) -> ProfileFactExtraction:
        compact = message.strip()
        if not compact or any(word in compact for word in ("没有摔", "没摔", "不担心摔")):
            return ProfileFactExtraction()
        facts: list[ProfileFactCandidate] = []
        if any(word in compact for word in ("差点摔", "险些摔", "差点跌倒")):
            facts.append(ProfileFactCandidate(
                fact_type="near_fall_experience",
                display_text="曾经差点摔倒",
                evidence_quote=compact[:120],
                confidence=0.9,
            ))
        elif any(word in compact for word in ("我摔倒", "我跌倒", "摔过", "跌倒过")):
            facts.append(ProfileFactCandidate(
                fact_type="fall_experience",
                display_text="曾经摔倒过",
                evidence_quote=compact[:120],
                confidence=0.9,
            ))
        if "摔" in compact and any(word in compact for word in ("担心", "害怕", "后怕", "紧张")):
            facts.append(ProfileFactCandidate(
                fact_type="fall_concern",
                display_text="最近会担心摔倒",
                evidence_quote=compact[:120],
                confidence=0.85,
            ))
        if any(word in compact for word in ("不敢走", "不敢出门", "少走", "减少走动", "不敢起夜")):
            facts.append(ProfileFactCandidate(
                fact_type="activity_avoidance",
                display_text="最近因担心而减少走动",
                evidence_quote=compact[:120],
                confidence=0.85,
            ))
        known_conditions = ("高血压", "糖尿病", "冠心病", "关节炎", "骨质疏松", "帕金森")
        if any(prefix in compact for prefix in ("我有", "我得了", "我确诊", "医生说我有")):
            condition = next((item for item in known_conditions if item in compact), None)
            if condition:
                facts.append(ProfileFactCandidate(
                    fact_type="health_condition",
                    display_text=f"本人提供的健康情况：{condition}",
                    evidence_quote=compact[:120],
                    confidence=0.9,
                ))
        if "我喜欢" in compact and not any(
            word in compact for word in ("药", "医院", "钱", "住址", "密码")
        ):
            preference = compact.split("我喜欢", 1)[1].strip("，。！？ ")
            if 1 <= len(preference) <= 40:
                facts.append(ProfileFactCandidate(
                    fact_type="daily_preference",
                    display_text=f"喜欢{preference}",
                    evidence_quote=compact[:120],
                    confidence=0.75,
                    memory_mode="inferred",
                ))
        return ProfileFactExtraction(facts=facts[:3])

    @staticmethod
    def _sleep_fields(item: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "sleep_start", "sleep_end", "duration_minutes", "respiratory_rate",
            "heart_rate", "bed_exit_count", "quality", "sleep_score",
            "awake_minutes", "light_sleep_minutes", "deep_sleep_minutes",
            "rem_sleep_minutes", "data_status", "measured_at",
        )
        return {key: item.get(key) for key in keys}

    @staticmethod
    def _sleep_attention(history: list[dict[str, Any]]) -> bool:
        if len(history) < 2:
            return False
        latest = history[0]
        baselines = history[1:7]
        average_duration = sum(int(item["duration_minutes"]) for item in baselines) / len(baselines)
        duration_changed = abs(int(latest["duration_minutes"]) - average_duration) >= 90
        repeated_bed_exits = int(latest.get("bed_exit_count") or 0) >= 3
        return duration_changed or repeated_bed_exits
