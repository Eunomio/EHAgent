"""Deterministic, source-labelled vertical slice for competition demonstrations."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app.db.models import AuditLogRecord, RiskTaskRecord
from app.db.session import Database
from app.domain.events import (
    CaptureMode,
    EventSource,
    ObservationEvent,
    QualityResult,
    SourceType,
)
from app.domain.runtime import RuntimeMode
from app.domain.tasks import TaskStatus
from app.schemas.tasks import (
    AgentStage,
    DemoAnalysisRequest,
    DemoAnalysisResponse,
    DemoMaterial,
)
from app.services.observation_service import ObservationService
from app.services.task_service import TaskService

MATERIALS = (
    DemoMaterial(
        case_id="corridor_clutter",
        name="走廊中部有纸箱",
        description="画质合格，纸箱侵入主要通道，用于生成二级整改任务。",
        thumbnail_url="/demo/corridor-clutter.svg",
        expected_outcome="生成一条走廊整改任务",
    ),
    DemoMaterial(
        case_id="corridor_clear",
        name="整改后的通畅走廊",
        description="与前一素材属于同一场景，用于复查并关闭待确认任务。",
        thumbnail_url="/demo/corridor-clear.svg",
        expected_outcome="不创建任务；可完成整改复查",
    ),
    DemoMaterial(
        case_id="quality_insufficient",
        name="严重模糊的走廊",
        description="模拟画质门控失败，Agent必须拒绝判断而不是宣称安全。",
        thumbnail_url="/demo/corridor-blur.svg",
        expected_outcome="证据不足，不生成任务",
    ),
)
MATERIAL_BY_ID = {material.case_id: material for material in MATERIALS}


class DemoAgentService:
    """Run replay/manual evidence through quality, rule and task stages."""

    def __init__(self, database: Database, observation_service: ObservationService) -> None:
        self._database = database
        self._observation_service = observation_service

    @staticmethod
    def materials() -> list[DemoMaterial]:
        return list(MATERIALS)

    @staticmethod
    def _stage(key: str, label: str, detail: str, *, blocked: bool = False) -> AgentStage:
        return AgentStage(
            key=key,
            label=label,
            detail=detail,
            status="blocked" if blocked else "complete",
        )

    def analyze(
        self, payload: DemoAnalysisRequest, *, runtime_mode: RuntimeMode
    ) -> DemoAnalysisResponse:
        """Execute the transparent deterministic path and persist its evidence."""

        material = MATERIAL_BY_ID[payload.case_id]
        source_type = SourceType.MANUAL if payload.preview_data_url else SourceType.REPLAY
        evidence_url = payload.preview_data_url or material.thumbnail_url
        material_name = payload.file_name or material.name
        now = datetime.now(UTC)
        quality_passed = payload.case_id != "quality_insufficient"
        event = ObservationEvent(
            occurred_at=now,
            received_at=now,
            source=EventSource(
                provider="manual" if source_type == SourceType.MANUAL else "replay",
                source_type=source_type,
                device_id="local-demo",
                channel_no=1,
                capture_mode=CaptureMode.FILE,
            ),
            event_type="demo_scene_analysis",
            runtime_mode=runtime_mode,
            scene_id="corridor_a",
            observations={
                "case_id": payload.case_id,
                "manual_label": source_type == SourceType.MANUAL,
                "object": "cardboard_box" if payload.case_id == "corridor_clutter" else None,
                "walkway_intrusion": payload.case_id == "corridor_clutter",
            },
            quality=QualityResult(
                passed=quality_passed,
                score=0.94 if quality_passed else 0.22,
                reason_codes=[] if quality_passed else ["BLUR_HIGH"],
            ),
            configuration_version="demo-agent-0.2.0",
        )
        self._observation_service.append(event)

        stages = [
            self._stage(
                "observe",
                "读取素材",
                f"已读取{material_name}；来源永久标记为{source_type.value}。",
            ),
            self._stage(
                "quality",
                "检查画质",
                "清晰度满足演示规则。" if quality_passed else "画面严重模糊，停止风险判断。",
                blocked=not quality_passed,
            ),
        ]
        if not quality_passed:
            return DemoAnalysisResponse(
                analysis_id=str(event.event_id),
                outcome="EVIDENCE_INSUFFICIENT",
                source_type=source_type,
                material_name=material_name,
                summary="本次画面不足以判断，请更换清晰素材。",
                stages=stages,
            )

        if payload.case_id == "corridor_clear":
            stages.append(self._stage("reason", "检查通道", "未发现物体侵入主要通行区域。"))
            resolved = self._resolve_pending_task(
                now, evidence_url=evidence_url, evidence_label=material_name
            )
            if resolved:
                stages.append(self._stage("act", "更新任务", "整改后复查通过，任务已完成。"))
                return DemoAnalysisResponse(
                    analysis_id=str(event.event_id),
                    outcome="RESOLVED",
                    source_type=source_type,
                    material_name=material_name,
                    summary="复查完成，走廊已经恢复通畅。",
                    stages=stages,
                    task=TaskService.to_response(resolved),
                )
            stages.append(self._stage("act", "决定动作", "没有待复查任务，不创建新提醒。"))
            return DemoAnalysisResponse(
                analysis_id=str(event.event_id),
                outcome="NO_ACTION",
                source_type=source_type,
                material_name=material_name,
                summary="通道中没有发现需要整改的物品。",
                stages=stages,
            )

        stages.extend(
            [
                self._stage("reason", "判断风险", "纸箱位于走廊中部并侵入主要通道，命中二级规则。"),
                self._stage("act", "生成建议", "建议将纸箱移到靠墙、不影响通行的位置。"),
            ]
        )
        task = self._create_or_update_task(
            now=now,
            source_type=source_type,
            runtime_mode=runtime_mode,
            evidence_url=evidence_url,
            evidence_label=material_name,
        )
        return DemoAnalysisResponse(
            analysis_id=str(event.event_id),
            outcome="TASK_CREATED",
            source_type=source_type,
            material_name=material_name,
            summary="发现一项需要处理的走廊通行风险。",
            stages=stages,
            task=TaskService.to_response(task),
        )

    def _create_or_update_task(
        self,
        *,
        now: datetime,
        source_type: SourceType,
        runtime_mode: RuntimeMode,
        evidence_url: str,
        evidence_label: str,
    ) -> RiskTaskRecord:
        with self._database.session() as session:
            record = session.scalar(
                select(RiskTaskRecord)
                .where(
                    RiskTaskRecord.scene_id == "corridor_a",
                    RiskTaskRecord.status.in_(
                        [
                            TaskStatus.OPEN.value,
                            TaskStatus.DEFERRED.value,
                            TaskStatus.RESCAN_PENDING.value,
                        ]
                    ),
                )
                .order_by(RiskTaskRecord.id.desc())
            )
            if record is None:
                record = RiskTaskRecord(
                    task_id=str(uuid4()),
                    scene_id="corridor_a",
                    case_id="corridor_clutter",
                    title="请移开走廊中部的纸箱",
                    location="走廊中部",
                    risk_type="通道障碍",
                    risk_level=2,
                    explanation="纸箱占用了主要通行位置，经过时更容易被绊到。",
                    suggested_action="请把纸箱移到靠墙且不影响通行的位置。",
                    status=TaskStatus.OPEN.value,
                    source_type=source_type.value,
                    runtime_mode=runtime_mode.value,
                    evidence_url=evidence_url,
                    evidence_label=evidence_label,
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
            else:
                record.status = TaskStatus.OPEN.value
                record.source_type = source_type.value
                record.runtime_mode = runtime_mode.value
                record.evidence_url = evidence_url
                record.evidence_label = evidence_label
                record.updated_at = now
                record.deferred_until = None
            session.add(
                AuditLogRecord(
                    action="DEMO_RISK_TASK_UPSERT",
                    actor="engineering-local",
                    object_type="risk_task",
                    object_id=record.task_id,
                    detail_json=json.dumps({"source_type": source_type.value}, ensure_ascii=False),
                    occurred_at=now,
                )
            )
            session.flush()
            return record

    def _resolve_pending_task(
        self, now: datetime, *, evidence_url: str, evidence_label: str
    ) -> RiskTaskRecord | None:
        with self._database.session() as session:
            record = session.scalar(
                select(RiskTaskRecord)
                .where(
                    RiskTaskRecord.scene_id == "corridor_a",
                    RiskTaskRecord.status == TaskStatus.RESCAN_PENDING.value,
                )
                .order_by(RiskTaskRecord.id.desc())
            )
            if record is None:
                return None
            record.status = TaskStatus.RESOLVED.value
            record.evidence_url = evidence_url
            record.evidence_label = evidence_label
            record.updated_at = now
            session.add(
                AuditLogRecord(
                    action="DEMO_TASK_RESCAN_RESOLVED",
                    actor="engineering-local",
                    object_type="risk_task",
                    object_id=record.task_id,
                    detail_json="{}",
                    occurred_at=now,
                )
            )
            session.flush()
            return record
