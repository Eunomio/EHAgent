from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class VitalSample(BaseModel):
    at: datetime
    respiratory_rate: float | None = Field(default=None, ge=1, le=80)
    heart_rate: float | None = Field(default=None, ge=20, le=240)
    in_bed: bool | None = None
    body_movement: float | None = Field(default=None, ge=0)


class SleepStage(BaseModel):
    start: datetime
    end: datetime
    stage: Literal["awake", "light", "deep", "rem", "unknown"]

    @model_validator(mode="after")
    def validate_period(self) -> "SleepStage":
        if self.end <= self.start:
            raise ValueError("睡眠阶段结束时间必须晚于开始时间")
        return self


class SleepReportIn(BaseModel):
    id: str | None = None
    external_report_id: str | None = Field(default=None, max_length=120)
    device_serial: str | None = Field(default=None, max_length=80)
    report_date: date | None = None
    timezone: str = Field(default="Asia/Shanghai", max_length=50)
    sleep_start: datetime
    sleep_end: datetime
    duration_minutes: int = Field(ge=1, le=1440)
    awake_minutes: int | None = Field(default=None, ge=0, le=1440)
    light_sleep_minutes: int | None = Field(default=None, ge=0, le=1440)
    deep_sleep_minutes: int | None = Field(default=None, ge=0, le=1440)
    rem_sleep_minutes: int | None = Field(default=None, ge=0, le=1440)
    sleep_score: float | None = Field(default=None, ge=0, le=100)
    respiratory_rate: float | None = Field(default=None, ge=1, le=80)
    heart_rate: float | None = Field(default=None, ge=20, le=240)
    respiratory_min: float | None = Field(default=None, ge=1, le=80)
    respiratory_max: float | None = Field(default=None, ge=1, le=80)
    heart_rate_min: float | None = Field(default=None, ge=20, le=240)
    heart_rate_max: float | None = Field(default=None, ge=20, le=240)
    bed_exit_count: int | None = Field(default=None, ge=0, le=100)
    quality: Literal["good", "usable", "insufficient"] = "usable"
    data_status: Literal["preliminary", "final", "corrected"] = "final"
    source: Literal["ezviz_sleep_assistant", "authorized_export", "research_import"]
    measured_at: datetime
    samples: list[VitalSample] = Field(default_factory=list)
    stages: list[SleepStage] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_report(self) -> "SleepReportIn":
        try:
            window_minutes = (self.sleep_end - self.sleep_start).total_seconds() / 60
        except TypeError as exc:
            raise ValueError("睡眠开始和结束时间必须使用相同的时区格式") from exc
        if window_minutes <= 0:
            raise ValueError("睡眠结束时间必须晚于开始时间")
        if self.duration_minutes > window_minutes + 5:
            raise ValueError("总睡眠时长不能超过睡眠记录时间段")
        if self.source == "ezviz_sleep_assistant" and not self.device_serial:
            raise ValueError("萤石睡眠报告必须包含device_serial")
        try:
            stage_outside_report = any(
                stage.start < self.sleep_start or stage.end > self.sleep_end
                for stage in self.stages
            )
        except TypeError as exc:
            raise ValueError("睡眠阶段必须和睡眠报告使用相同的时区格式") from exc
        if stage_outside_report:
            raise ValueError("睡眠阶段必须位于睡眠开始和结束时间之内")
        self._validate_vital_range(
            "呼吸频率", self.respiratory_min, self.respiratory_rate, self.respiratory_max
        )
        self._validate_vital_range(
            "心率", self.heart_rate_min, self.heart_rate, self.heart_rate_max
        )
        return self

    @staticmethod
    def _validate_vital_range(
        name: str, minimum: float | None, average: float | None, maximum: float | None
    ) -> None:
        values = [value for value in (minimum, average, maximum) if value is not None]
        if len(values) >= 2 and values != sorted(values):
            raise ValueError(f"{name}最低值、平均值和最高值顺序不正确")
