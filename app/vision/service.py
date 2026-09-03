import asyncio
import base64
import json
import mimetypes
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

import httpx
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.core.config import Settings
from app.devices.ezviz import EzvizClient


class VisionSafetyError(RuntimeError):
    pass


class BaselineMissingError(VisionSafetyError):
    pass


class UnsafeBaselineError(VisionSafetyError):
    pass


HazardType = Literal["box", "bag", "shoe", "stool", "cable", "other_obstacle"]


class HazardRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hazard_type: HazardType
    label: str = Field(min_length=1, max_length=20)
    risk_level: Literal["low", "medium", "high"]
    x1: int = Field(ge=0, le=1000)
    y1: int = Field(ge=0, le=1000)
    x2: int = Field(ge=0, le=1000)
    y2: int = Field(ge=0, le=1000)

    @model_validator(mode="after")
    def valid_rectangle(self) -> "HazardRegion":
        if self.x2 - self.x1 < 10 or self.y2 - self.y1 < 10:
            raise ValueError("风险框范围过小")
        return self


class VisionPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visibility: Literal["usable", "limited", "insufficient"]
    hazard_present: bool | None
    hazard_types: list[HazardType]
    position_zone: Literal["outside", "boundary", "inner_side", "center", "unknown"]
    walkway_occupation: Literal["none", "under_quarter", "quarter_to_half", "over_half", "unknown"]
    walkway_length_occupation: Literal["none", "under_quarter", "quarter_to_half", "over_half", "unknown"]
    passage_effect: Literal["none", "narrowed", "detour", "difficult", "blocked", "unknown"]
    trip_risk: Literal["none", "possible", "obvious", "unknown"]
    reason: str = Field(min_length=1, max_length=200)
    hazard_regions: list[HazardRegion] = Field(default_factory=list, max_length=6)
    walkway_near_x1: int | None = Field(default=None, ge=0, le=1000)
    walkway_near_x2: int | None = Field(default=None, ge=0, le=1000)


HAZARD_ALIASES = {
    "boxes": "box", "cardboard_box": "box", "carton": "box",
    "package": "box", "packaging": "box", "bags": "bag",
    "shoes": "shoe", "slippers": "shoe", "chair": "stool",
    "wire": "cable", "wires": "cable", "cord": "cable",
    "debris": "other_obstacle", "obstacle": "other_obstacle",
    "obstacles": "other_obstacle", "clutter": "other_obstacle",
}

HAZARD_LABELS = {
    "box": "纸箱", "bag": "袋子", "shoe": "鞋子", "stool": "凳子",
    "cable": "电线", "other_obstacle": "障碍物",
}


def reconcile_walkway_geometry(prediction: VisionPrediction) -> VisionPrediction:
    """Correct contradictory semantic fields using the model's own risk boxes."""

    positive_trip_phrases = (
        "存在绊倒风险",
        "有绊倒风险",
        "可能绊倒",
        "容易绊倒",
        "会绊倒",
        "可能踩到",
        "可能踢到",
    )
    negative_trip_phrases = (
        "没有绊倒风险",
        "无绊倒风险",
        "不存在绊倒风险",
        "不易绊倒",
    )
    if (
        prediction.hazard_present is True
        and prediction.trip_risk == "none"
        and any(phrase in prediction.reason for phrase in positive_trip_phrases)
        and not any(phrase in prediction.reason for phrase in negative_trip_phrases)
    ):
        prediction = prediction.model_copy(update={"trip_risk": "possible"})

    walkway_x1 = prediction.walkway_near_x1
    walkway_x2 = prediction.walkway_near_x2
    if (
        walkway_x1 is None
        or walkway_x2 is None
        or walkway_x2 - walkway_x1 < 150
    ):
        # The current C6c view places the doorway and near walking line slightly
        # right of the full-frame center. Model-provided boundaries take priority.
        walkway_x1, walkway_x2 = 400, 850
    walkway_width = walkway_x2 - walkway_x1
    walkway_center = (walkway_x1 + walkway_x2) / 2

    crossing: tuple[HazardRegion, float] | None = None
    for region in prediction.hazard_regions:
        overlap = max(0, min(region.x2, walkway_x2) - max(region.x1, walkway_x1))
        overlap_ratio = overlap / walkway_width
        if (
            region.y2 >= 850
            and region.x2 - region.x1 >= 250
            and (
                region.x1 <= walkway_center <= region.x2
                or overlap_ratio >= 0.4
            )
            and overlap_ratio >= 0.25
        ):
            crossing = region, overlap_ratio
            break
    if crossing is None:
        return prediction

    region, overlap_ratio = crossing
    occupation = "over_half" if overlap_ratio >= 0.5 else "quarter_to_half"
    passage_effect = "difficult" if overlap_ratio >= 0.5 else "detour"
    return prediction.model_copy(update={
        "position_zone": "center",
        "walkway_occupation": occupation,
        "passage_effect": passage_effect,
        "trip_risk": "possible" if prediction.trip_risk == "none" else prediction.trip_risk,
        "reason": (
            f"{region.label}位于画面近处并伸入通道中央落脚区域，"
            "正常通过时需要绕开，存在碰撞或绊倒风险。"
        ),
        "walkway_near_x1": walkway_x1,
        "walkway_near_x2": walkway_x2,
    })


def remediation_advice(prediction: VisionPrediction, risk: str) -> str:
    hazard = prediction.hazard_types[0] if prediction.hazard_types else "other_obstacle"
    advice = {
        "box": "请将纸箱移到通道外，避免经过时碰到或绊倒",
        "bag": "请将袋子收好并移出常用行走路线",
        "shoe": "请将鞋子收入鞋柜或靠墙整齐摆放",
        "stool": "请将凳子移出通道，留出自然直行空间",
        "cable": "请将电线沿墙固定，避免横穿落脚区域",
        "other_obstacle": "请将影响行走的物品移到通道外",
    }[hazard]
    if risk == "high":
        return advice.replace("请", "请立即", 1)
    return advice


def display_regions(prediction: VisionPrediction, risk: str) -> list[dict[str, Any]]:
    if risk not in {"low", "medium", "high"}:
        return []
    regions = [region.model_copy(deep=True) for region in prediction.hazard_regions]
    if not regions:
        return []
    if risk == "low":
        for region in regions:
            region.risk_level = "low"
    elif not any(region.risk_level in {"medium", "high"} for region in regions):
        regions[0].risk_level = risk  # type: ignore[assignment]
    elif risk == "high" and not any(region.risk_level == "high" for region in regions):
        next(region for region in regions if region.risk_level == "medium").risk_level = "high"
    return [region.model_dump(mode="json") for region in regions]


def derive_assessment(prediction: VisionPrediction) -> dict[str, str]:
    prediction = reconcile_walkway_geometry(prediction)
    near_field_crossing = any(
        region.y2 >= 850
        and region.x2 - region.x1 >= 250
        and region.x1
        <= (
            (prediction.walkway_near_x1 or 400)
            + (prediction.walkway_near_x2 or 850)
        ) / 2
        <= region.x2
        for region in prediction.hazard_regions
    )
    if prediction.visibility == "insufficient" or prediction.hazard_present is None:
        risk = "insufficient"
    elif prediction.hazard_present is False:
        risk = "low" if prediction.visibility == "limited" else "clear"
    elif (
        prediction.passage_effect in {"difficult", "blocked"}
        or prediction.walkway_occupation == "over_half"
        or prediction.trip_risk == "obvious"
        or (near_field_crossing and prediction.trip_risk == "possible")
    ):
        risk = "high"
    elif (
        prediction.passage_effect == "detour"
        or near_field_crossing
        or (
            prediction.walkway_occupation == "quarter_to_half"
            and prediction.position_zone == "center"
        )
        or prediction.trip_risk == "possible"
    ):
        risk = "medium"
    elif (
        prediction.passage_effect == "narrowed"
        or prediction.visibility == "limited"
    ):
        risk = "low"
    else:
        risk = "clear"

    clear_copy = (
        ("通道可以正常通行", "当前无需整理")
        if prediction.hazard_present
        else ("通道畅通", "保持通道整洁")
    )
    headline, action_text = {
        "clear": clear_copy,
        "low": ("通道可以通行", "保持观察即可"),
        "medium": ("通道需要整理", "请将物品移到通道外"),
        "high": ("通道通行受阻", "请尽快清理通道"),
        "insufficient": ("暂时看不清通道", "请调整光线后重新检查"),
    }[risk]
    if risk in {"medium", "high"}:
        action_text = remediation_advice(prediction, risk)
    return {"risk_level": risk, "headline": headline, "action_text": action_text}


class VisionSafetyService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=settings.vlm_timeout_seconds)
        self._owns_client = client is None
        self.root = Path(settings.evidence_root).resolve() / "safety-vision" / "c6c"
        self.analysis_lock = asyncio.Lock()
        self.speech_lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self.settings.llm_enabled if self.settings.vlm_enabled is None else self.settings.vlm_enabled

    @property
    def api_key(self) -> str:
        return self.settings.vlm_api_key or self.settings.llm_api_key

    @property
    def model(self) -> str:
        return self.settings.vlm_model or self.settings.llm_model

    @property
    def api_base(self) -> str:
        return self.settings.vlm_api_base or self.settings.llm_api_base

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.api_key and self.model and self.api_base)

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    def baseline_status(self) -> dict[str, Any]:
        baseline = self.root / "baseline.jpg"
        metadata_path = self.root / "baseline.json"
        metadata: dict[str, Any] = {}
        if metadata_path.is_file():
            try:
                parsed = json.loads(metadata_path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    metadata = parsed
            except (OSError, json.JSONDecodeError):
                metadata = {}
        return {
            "ready": baseline.is_file() and not bool(metadata.get("stale")),
            "captured_at": metadata.get("captured_at"),
            "stale": bool(metadata.get("stale")),
        }

    async def set_baseline(self, ezviz: EzvizClient) -> dict[str, Any]:
        async with self.analysis_lock:
            picture_url = await ezviz.capture()
            image, content_type = await ezviz.download_picture(picture_url)
            self._validate_image(image, content_type)
            if self.configured:
                prediction = await self._predict(
                    image,
                    content_type,
                    image,
                    baseline_validation=True,
                )
                assessment = derive_assessment(prediction)
                if (
                    prediction.visibility != "usable"
                    or assessment["risk_level"] in {"medium", "high", "insufficient"}
                ):
                    raise UnsafeBaselineError(
                        f"当前画面还不适合作为安全基准：{prediction.reason}"
                    )
            captured_at = datetime.now().astimezone().isoformat(timespec="seconds")
            self.root.mkdir(parents=True, exist_ok=True)
            self._replace_file(self.root / "baseline.jpg", image)
            self._replace_file(
                self.root / "baseline.json",
                json.dumps(
                    {"captured_at": captured_at, "stale": False}, ensure_ascii=False
                ).encode("utf-8"),
            )
        return {"ready": True, "captured_at": captured_at}

    def invalidate_baseline(self) -> dict[str, Any]:
        status = self.baseline_status()
        if not (self.root / "baseline.jpg").is_file():
            return status
        self.root.mkdir(parents=True, exist_ok=True)
        self._replace_file(
            self.root / "baseline.json",
            json.dumps(
                {"captured_at": status.get("captured_at"), "stale": True},
                ensure_ascii=False,
            ).encode("utf-8"),
        )
        return self.baseline_status()

    async def analyze(self, ezviz: EzvizClient) -> dict[str, Any]:
        picture_url = await ezviz.capture()
        current_image, content_type = await ezviz.download_picture(picture_url)
        return await self.analyze_image(current_image, content_type)

    async def analyze_image(
        self, current_image: bytes, content_type: str = "image/jpeg"
    ) -> dict[str, Any]:
        async with self.analysis_lock:
            return await self._analyze_image(current_image, content_type)

    async def _analyze_image(
        self, current_image: bytes, content_type: str
    ) -> dict[str, Any]:
        if not self.configured:
            raise VisionSafetyError("安全检查服务尚未配置")
        baseline_path = self.root / "baseline.jpg"
        if not self.baseline_status()["ready"] or not baseline_path.is_file():
            raise BaselineMissingError("请先设置当前视角的通道基准")
        self._validate_image(current_image, content_type)
        checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
        self.root.mkdir(parents=True, exist_ok=True)
        current_path = self.root / f"check-{datetime.now().astimezone():%Y%m%d-%H%M%S-%f}.jpg"
        self._replace_file(current_path, current_image)
        prediction = await self._predict(
            current_image,
            content_type,
            baseline_path.read_bytes(),
        )
        assessment = derive_assessment(prediction)
        return {
            "checked_at": checked_at,
            "prediction": prediction.model_dump(mode="json"),
            "assessment": assessment,
            "reason": prediction.reason,
            "hazard_regions": display_regions(prediction, assessment["risk_level"]),
            "evidence_path": str(current_path),
        }

    async def synthesize_warning(self, text: str) -> bytes:
        if not self.settings.tts_enabled or not self.api_key or not self.api_base:
            raise VisionSafetyError("语音提醒暂时不可用")
        cleaned = " ".join(text.split())[:500]
        if not cleaned:
            raise VisionSafetyError("语音提醒内容为空")
        response = await self.client.post(
            f"{self.api_base.rstrip('/')}/audio/speech",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.tts_model,
                "input": cleaned,
                "voice": self.settings.tts_voice,
                "response_format": "mp3",
                "speed": self.settings.tts_speed,
            },
            timeout=self.settings.vlm_timeout_seconds,
        )
        response.raise_for_status()
        if len(response.content) < 128:
            raise VisionSafetyError("语音提醒生成失败")
        return response.content

    async def warning_audio(self, check_id: str, text: str) -> bytes:
        path = self.root / f"speech-{check_id}.mp3"
        async with self.speech_lock:
            if path.is_file() and path.stat().st_size >= 128:
                return path.read_bytes()
            audio = await self.synthesize_warning(text)
            self.root.mkdir(parents=True, exist_ok=True)
            self._replace_file(path, audio)
            return audio

    async def _predict(
        self,
        current_image: bytes,
        content_type: str,
        baseline_image: bytes,
        baseline_validation: bool = False,
    ) -> VisionPrediction:
        current_model_image, current_model_type = self._prepare_model_image(
            current_image, content_type
        )
        baseline_model_image, baseline_model_type = self._prepare_model_image(
            baseline_image, "image/jpeg"
        )
        current_url = self._data_url(current_model_image, current_model_type)
        baseline_url = self._data_url(baseline_model_image, baseline_model_type)
        prediction: VisionPrediction | None = None
        last_error: Exception | None = None
        for correction_attempt in range(2):
            body = self._request_body(
                current_url,
                baseline_url,
                correction=correction_attempt == 1,
                baseline_validation=baseline_validation,
            )
            try:
                response = await self.client.post(
                    f"{self.api_base.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                response.raise_for_status()
                raw = response.json()["choices"][0]["message"]["content"]
                prediction = reconcile_walkway_geometry(VisionPrediction.model_validate(
                    self._normalize(self._parse_object(raw))
                ))
                break
            except (
                httpx.HTTPError,
                KeyError,
                IndexError,
                TypeError,
                ValueError,
                ValidationError,
            ) as exc:
                last_error = exc
        if prediction is None:
            raise VisionSafetyError("本次检查没有完成，请稍后重试") from last_error
        return prediction

    @staticmethod
    def image_signature(image: bytes) -> tuple[int, ...]:
        try:
            with Image.open(BytesIO(image)) as opened:
                grayscale = opened.convert("L").resize((32, 18), Image.Resampling.BILINEAR)
                return tuple(grayscale.getdata())
        except (OSError, UnidentifiedImageError) as exc:
            raise VisionSafetyError("摄像头返回的图片无法读取") from exc

    @staticmethod
    def signature_difference(first: tuple[int, ...], second: tuple[int, ...]) -> float:
        if len(first) != len(second) or not first:
            return 1.0
        return sum(abs(left - right) for left, right in zip(first, second, strict=True)) / (
            len(first) * 255
        )

    def _request_body(
        self,
        current_url: str,
        baseline_url: str,
        correction: bool = False,
        baseline_validation: bool = False,
    ) -> dict[str, Any]:
        prompt = (
            "第一张图片是当前截图，第二张是同一摄像头、同一位置拍摄的安全畅通基准图。"
            "请从基准图识别供人通行的走道边界，比较当前截图中新增或移动的物品。"
            "允许摄像头存在轻微角度变化，不要因为透视或边界的小幅偏移判断为通行风险。"
            "判断目标是人能否沿原有走道正常、安全通行，不要求画面中完全没有物品。"
            "通行宽度和跌倒风险是两个独立结论：即使旁边仍有空间通过，只要脚可能碰到物品、"
            "需要绕脚或跨越、物品伸入门槛或实际落脚区域，trip_risk也必须是possible或obvious。"
            "玩具车、积木、球、拖鞋等低矮小物品散落在地面时，要重点判断脚是否可能踩到或踢到；"
            "只要它们位于常用行走路线、门口、门槛或落脚区域，就属于绊倒风险，至少返回possible，"
            "不能因为剩余通行宽度足够、物品较小或靠近一侧而返回none。"
            "只要trip_risk为possible或obvious，本次画面就需要提醒整理，不能得出无需整理的结论。"
            "reason与trip_risk必须一致；reason中写明存在、有、可能或容易绊倒时，trip_risk禁止为none。"
            "同时不要仅因为物品靠近通道边界就推断跌倒风险。家庭通道边缘存在固定置物很常见；"
            "若物品没有伸入常用落脚路线、不需要改变脚步、可以自然直行通过，trip_risk应为none。"
            "物品出现在画面中不等于需要整理；放在走道外或紧靠边缘，并且不缩窄有效通行宽度、"
            "不要求绕行、没有绊倒风险时，应判断为不影响通行。"
            "visibility只能是usable、limited、insufficient。"
            "hazard_present只能是true、false或null；null表示无法确认。"
            "hazard_types只能从box、bag、shoe、stool、cable、other_obstacle中选择，"
            "没有障碍物时返回空数组。"
            "position_zone只能是outside、boundary、inner_side、center、unknown。"
            "walkway_occupation表示物品所在位置横向占掉的通行宽度比例；"
            "只能是none、under_quarter、quarter_to_half、over_half、unknown，禁止返回数字。"
            "walkway_length_occupation表示物品从近处到远处沿行走方向占用的长度比例。"
            "只能是none、under_quarter、quarter_to_half、over_half、unknown，禁止返回数字。"
            "passage_effect只能是none、narrowed、detour、difficult、blocked、unknown。"
            "只有正常行走路线确实需要改变时才使用detour；物品在边缘且可直行通过时使用none。"
            "trip_risk只能是none、possible、obvious、unknown。position_zone位于边缘不能直接推出"
            "trip_risk为none；必须单独检查物品是否实际伸入脚的行进区域。只有画面中能观察到"
            "物品进入常用落脚位置、需要绕脚或跨越时，才使用possible或obvious，禁止仅凭靠近边缘推测。"
            "只依据可见内容判断。看不清时使用unknown、null或insufficient，不补充图片外的信息。"
            "reason使用一句简短中文说明可见依据。hazard_regions用于标出真正需要关注的物品，"
            "最多6个；每项包含hazard_type、中文label、risk_level和x1、y1、x2、y2。"
            "坐标以当前图片左上角为原点，在0到1000之间归一化，框住物品可见范围。"
            "risk_level只能是low、medium、high；不影响通行的边缘置物不要添加风险框。"
            "walkway_near_x1和walkway_near_x2表示基准图中画面近处实际可通行开口的左右边界，"
            "同样使用0到1000归一化横坐标；无法可靠判断时返回null。"
            "如果无法可靠定位，hazard_regions返回空数组，禁止编造坐标。必须返回十二个字段："
            "visibility、hazard_present、hazard_types、position_zone、walkway_occupation、"
            "walkway_length_occupation、passage_effect、trip_risk、reason、hazard_regions、"
            "walkway_near_x1、walkway_near_x2。前九个字段必须出现，hazard_regions无法定位时"
            "也要返回空数组。"
            "输出示例："
            '{"visibility":"usable","hazard_present":false,"hazard_types":[],'
            '"position_zone":"outside","walkway_occupation":"none",'
            '"walkway_length_occupation":"none","passage_effect":"none",'
            '"trip_risk":"none","reason":"当前通道与安全基准图一致，未见新增障碍物。",'
            '"hazard_regions":[],"walkway_near_x1":400,"walkway_near_x2":850}'
            "边缘纸箱且不影响通行的输出示例："
            '{"visibility":"usable","hazard_present":true,"hazard_types":["box"],'
            '"position_zone":"inner_side","walkway_occupation":"under_quarter",'
            '"walkway_length_occupation":"under_quarter","passage_effect":"none",'
            '"trip_risk":"none","reason":"纸箱位于走道边缘，剩余宽度足够直行通过。",'
            '"hazard_regions":[],"walkway_near_x1":400,"walkway_near_x2":850}'
            "地面散落玩具车的输出示例："
            '{"visibility":"usable","hazard_present":true,"hazard_types":["other_obstacle"],'
            '"position_zone":"inner_side","walkway_occupation":"under_quarter",'
            '"walkway_length_occupation":"under_quarter","passage_effect":"none",'
            '"trip_risk":"possible","reason":"玩具车散落在地面落脚区域，经过时可能踩到或绊倒。",'
            '"hazard_regions":[],"walkway_near_x1":400,"walkway_near_x2":850}'
        )
        if baseline_validation:
            prompt += (
                "这次是在检查候选基准图，两张图片内容相同。不要因为两图一致就认为安全。"
                "请直接检查画面本身是否适合作为安全基准，重点查看门口、门槛和从近处到远处的"
                "实际落脚区域。走道边缘不影响自然直行的固定置物可以保留；需要绕脚、跨越或"
                "确实进入落脚位置的物品才标记跌倒风险。"
            )
        if correction:
            prompt += (
                "上一次输出存在字段缺失或类型错误。请重新检查图片，完整返回上述十个字段。"
                "占用比例必须使用指定英文枚举，不能使用0、0.0、百分数或其他数字。"
            )
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "检查候选基准画面本身是否安全，并严格按JSON Schema输出。"
                        if baseline_validation
                        else "比较当前截图和基准图，同时独立判断通行宽度和跌倒风险，并严格按JSON Schema输出。"
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "第一张：当前截图。"},
                        {"type": "image_url", "image_url": {"url": current_url}},
                        {"type": "text", "text": "第二张：安全畅通基准图。"},
                        {"type": "image_url", "image_url": {"url": baseline_url}},
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
            "stream": False,
            "temperature": 0.1,
            "max_tokens": self.settings.llm_max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "walkway_safety", "schema": VisionPrediction.model_json_schema()},
            },
        }

    @staticmethod
    def _parse_object(value: Any) -> dict[str, Any]:
        if not isinstance(value, str):
            raise ValueError("响应内容为空")
        cleaned = value.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("响应格式错误")
        return parsed

    @staticmethod
    def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(raw)
        if normalized.get("visibility") == "clear":
            normalized["visibility"] = "usable"
        hazards = normalized.get("hazard_types")
        if isinstance(hazards, list):
            normalized["hazard_types"] = list(dict.fromkeys(
                HAZARD_ALIASES.get(str(item).lower(), item) for item in hazards
            ))
        regions: list[dict[str, Any]] = []
        raw_regions = normalized.get("hazard_regions", [])
        if isinstance(raw_regions, list):
            for raw in raw_regions[:6]:
                if not isinstance(raw, dict):
                    continue
                try:
                    hazard = HAZARD_ALIASES.get(
                        str(raw.get("hazard_type", "other_obstacle")).lower(),
                        str(raw.get("hazard_type", "other_obstacle")).lower(),
                    )
                    if hazard not in HAZARD_LABELS:
                        hazard = "other_obstacle"
                    x1 = max(0, min(1000, int(float(raw.get("x1", 0)))))
                    y1 = max(0, min(1000, int(float(raw.get("y1", 0)))))
                    x2 = max(0, min(1000, int(float(raw.get("x2", 0)))))
                    y2 = max(0, min(1000, int(float(raw.get("y2", 0)))))
                    if x2 - x1 < 10 or y2 - y1 < 10:
                        continue
                    region_risk = str(raw.get("risk_level", "low")).lower()
                    if region_risk not in {"low", "medium", "high"}:
                        region_risk = "low"
                    regions.append({
                        "hazard_type": hazard,
                        "label": str(raw.get("label") or HAZARD_LABELS[hazard])[:20],
                        "risk_level": region_risk,
                        "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    })
                except (TypeError, ValueError):
                    continue
        normalized["hazard_regions"] = regions
        return normalized

    @staticmethod
    def _data_url(image: bytes, content_type: str) -> str:
        mime = content_type.split(";", 1)[0].strip()
        if not mime.startswith("image/"):
            mime = mimetypes.guess_type("capture.jpg")[0] or "image/jpeg"
        return f"data:{mime};base64,{base64.b64encode(image).decode('ascii')}"

    def _prepare_model_image(self, image: bytes, content_type: str) -> tuple[bytes, str]:
        """Reduce upload and multimodal preprocessing time without changing evidence files."""

        try:
            with Image.open(BytesIO(image)) as opened:
                converted = opened.convert("RGB")
                converted.thumbnail(
                    (
                        self.settings.vlm_image_max_dimension,
                        self.settings.vlm_image_max_dimension,
                    ),
                    Image.Resampling.LANCZOS,
                )
                output = BytesIO()
                converted.save(
                    output,
                    format="JPEG",
                    quality=self.settings.vlm_image_jpeg_quality,
                    optimize=True,
                )
                return output.getvalue(), "image/jpeg"
        except (OSError, UnidentifiedImageError):
            return image, content_type

    @staticmethod
    def _validate_image(image: bytes, content_type: str) -> None:
        if len(image) < 100 or not content_type.lower().startswith("image/"):
            raise VisionSafetyError("摄像头返回的图片无效，请重新抓取")

    @staticmethod
    def _replace_file(path: Path, content: bytes) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
