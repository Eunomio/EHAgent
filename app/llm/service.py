import json
from typing import Any, TypeVar

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
    def _sleep_fields(item: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "sleep_start", "sleep_end", "duration_minutes", "respiratory_rate",
            "heart_rate", "bed_exit_count", "quality", "measured_at",
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
