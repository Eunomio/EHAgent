import asyncio
import base64
import json
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app.core.config import Settings
from app.store import ProductStore
from app.vision.monitor import VisionChangeMonitor
from app.vision.service import (
    UnsafeBaselineError,
    VisionPrediction,
    VisionSafetyService,
    derive_assessment,
    display_regions,
    reconcile_walkway_geometry,
)
from app.vision.workflow import record_safety_result


class FakeCamera:
    async def capture(self) -> str:
        return "https://camera.test/capture.jpg"

    async def download_picture(self, picture_url: str) -> tuple[bytes, str]:
        assert picture_url == "https://camera.test/capture.jpg"
        return b"jpeg-image" * 20, "image/jpeg"


def test_model_image_is_resized_before_upload(tmp_path: Path) -> None:
    output = BytesIO()
    Image.new("RGB", (2000, 1000), (120, 120, 120)).save(output, format="JPEG")
    service = VisionSafetyService(Settings(evidence_root=tmp_path, vlm_image_max_dimension=1280))

    prepared, content_type = service._prepare_model_image(output.getvalue(), "image/jpeg")

    with Image.open(BytesIO(prepared)) as image:
        assert image.size == (1280, 640)
    assert content_type == "image/jpeg"


def test_long_item_at_side_does_not_create_cleanup_risk_by_itself() -> None:
    prediction = VisionPrediction(
        visibility="usable",
        hazard_present=True,
        hazard_types=["box"],
        position_zone="inner_side",
        walkway_occupation="under_quarter",
        walkway_length_occupation="over_half",
        passage_effect="narrowed",
        trip_risk="none",
        reason="纸箱沿通道方向占用较长。",
    )
    assert derive_assessment(prediction)["risk_level"] == "low"


def test_box_at_walkway_edge_is_clear_when_people_can_walk_straight() -> None:
    prediction = VisionPrediction(
        visibility="usable",
        hazard_present=True,
        hazard_types=["box"],
        position_zone="inner_side",
        walkway_occupation="under_quarter",
        walkway_length_occupation="under_quarter",
        passage_effect="none",
        trip_risk="none",
        reason="纸箱位于走道边缘，剩余宽度足够直行通过。",
    )
    assessment = derive_assessment(prediction)
    assert assessment["risk_level"] == "clear"
    assert assessment["headline"] == "通道可以正常通行"
    assert assessment["action_text"] == "当前无需整理"


def test_possible_trip_risk_always_requires_cleanup() -> None:
    prediction = VisionPrediction(
        visibility="usable",
        hazard_present=True,
        hazard_types=["box"],
        position_zone="inner_side",
        walkway_occupation="under_quarter",
        walkway_length_occupation="under_quarter",
        passage_effect="none",
        trip_risk="possible",
        reason="地面物品靠近日常落脚区域，可能绊倒。",
    )
    assessment = derive_assessment(prediction)
    assert assessment["risk_level"] == "medium"
    assert assessment["headline"] == "通道需要整理"


def test_trip_risk_in_reason_cannot_produce_clear_result() -> None:
    prediction = VisionPrediction(
        visibility="usable",
        hazard_present=True,
        hazard_types=["other_obstacle"],
        position_zone="inner_side",
        walkway_occupation="under_quarter",
        walkway_length_occupation="under_quarter",
        passage_effect="none",
        trip_risk="none",
        reason="玩具车散落在地面落脚区域，有绊倒风险。",
    )

    assessment = derive_assessment(prediction)

    assert assessment["risk_level"] == "medium"
    assert assessment["headline"] == "通道需要整理"
    assert "物品移到通道外" in assessment["action_text"]


def test_baseline_and_analysis_use_two_images(tmp_path: Path) -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            content = body["messages"][1]["content"]
            images = [item for item in content if item["type"] == "image_url"]
            assert len(images) == 2
            assert all(item["image_url"]["url"].startswith("data:image/jpeg;base64,") for item in images)
            text = "".join(item["text"] for item in content if item["type"] == "text")
            if "候选基准图" in text:
                prediction = {
                    "visibility": "usable",
                    "hazard_present": False,
                    "hazard_types": [],
                    "position_zone": "outside",
                    "walkway_occupation": "none",
                    "walkway_length_occupation": "none",
                    "passage_effect": "none",
                    "trip_risk": "none",
                    "reason": "门口和通道落脚区域保持畅通。",
                }
            else:
                prediction = {
                    "visibility": "usable",
                    "hazard_present": True,
                    "hazard_types": ["box"],
                    "position_zone": "center",
                    "walkway_occupation": "quarter_to_half",
                    "walkway_length_occupation": "under_quarter",
                    "passage_effect": "detour",
                    "trip_risk": "possible",
                    "reason": "纸箱位于通道中部，经过时需要绕开。",
                }
            return httpx.Response(200, json={
                "choices": [{"message": {"content": json.dumps(prediction, ensure_ascii=False)}}],
            })

        settings = Settings(
            evidence_root=tmp_path,
            vlm_enabled=True,
            vlm_api_key="test-key",
            vlm_model="ecnu-plus",
            vlm_api_base="https://chat.test/v1",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = VisionSafetyService(settings, client)
            baseline = await service.set_baseline(FakeCamera())  # type: ignore[arg-type]
            assert baseline["ready"] is True
            assert service.baseline_status()["ready"] is True
            result = await service.analyze(FakeCamera())  # type: ignore[arg-type]
            assert result["assessment"]["risk_level"] == "medium"
            assert result["assessment"]["headline"] == "通道需要整理"

    asyncio.run(scenario())


def test_safety_endpoints_save_baseline_and_create_task(client) -> None:
    async def fake_set_baseline(_camera) -> dict[str, object]:
        return {"ready": True, "captured_at": "2026-08-21T18:00:00+08:00"}

    async def fake_analyze(_camera) -> dict[str, object]:
        return {
            "checked_at": "2026-08-21T18:01:00+08:00",
            "prediction": {},
            "assessment": {
                "risk_level": "medium",
                "headline": "通道需要整理",
                "action_text": "请将物品移到通道外",
            },
            "reason": "纸箱位于通道中部，经过时需要绕开。",
            "evidence_path": "test.jpg",
        }

    client.app.state.vision_safety.set_baseline = fake_set_baseline
    client.app.state.vision_safety.analyze = fake_analyze

    baseline = client.post("/api/v1/devices/c6c/safety/baseline")
    assert baseline.status_code == 200
    assert baseline.json()["ready"] is True

    analysis = client.post("/api/v1/devices/c6c/safety/analyze")
    assert analysis.status_code == 200
    assert analysis.json()["assessment"]["risk_level"] == "medium"
    assert analysis.json()["task_id"]
    task = client.get("/api/v1/resident/safety").json()["task"]
    assert task["title"] == "通道需要整理"


def test_safety_frame_uses_existing_vision_analysis(client) -> None:
    received: dict[str, object] = {}

    async def fake_analyze_image(image: bytes, content_type: str) -> dict[str, object]:
        received.update({"image": image, "content_type": content_type})
        return {
            "checked_at": "2026-08-21T18:02:00+08:00",
            "prediction": {},
            "assessment": {
                "risk_level": "medium",
                "headline": "通道需要整理",
                "action_text": "请将影响通行的物品移到通道外",
            },
            "reason": "画面中的物品伸入了日常行走区域。",
            "hazard_regions": [],
            "evidence_path": "frame.jpg",
        }

    client.app.state.vision_safety.analyze_image = fake_analyze_image
    image = b"jpeg-frame" * 20
    response = client.post(
        "/api/v1/devices/c6c/safety/analyze-frame",
        json={"image_base64": base64.b64encode(image).decode("ascii")},
    )

    assert response.status_code == 200
    assert received == {"image": image, "content_type": "image/jpeg"}
    assert response.json()["reason"] == "画面中的物品伸入了日常行走区域。"
    assert response.json()["task_id"]


def test_analysis_retries_when_platform_omits_required_fields(tmp_path: Path) -> None:
    async def scenario() -> None:
        analysis_request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal analysis_request_count
            body = json.loads(request.content)
            text = "".join(
                item["text"]
                for item in body["messages"][1]["content"]
                if item["type"] == "text"
            )
            if "候选基准图" in text:
                content = {
                    "visibility": "usable",
                    "hazard_present": False,
                    "hazard_types": [],
                    "position_zone": "outside",
                    "walkway_occupation": "none",
                    "walkway_length_occupation": "none",
                    "passage_effect": "none",
                    "trip_risk": "none",
                    "reason": "门口和通道落脚区域保持畅通。",
                }
            elif analysis_request_count == 0:
                analysis_request_count += 1
                content = {
                    "walkway_occupation": 0.0,
                    "walkway_length_occupation": 0.0,
                    "reason": "当前通道未见变化。",
                }
            else:
                analysis_request_count += 1
                last_text = body["messages"][1]["content"][-1]["text"]
                assert "上一次输出存在字段缺失或类型错误" in last_text
                content = {
                    "visibility": "usable",
                    "hazard_present": False,
                    "hazard_types": [],
                    "position_zone": "outside",
                    "walkway_occupation": "none",
                    "walkway_length_occupation": "none",
                    "passage_effect": "none",
                    "trip_risk": "none",
                    "reason": "当前通道与安全基准图一致，未见新增障碍物。",
                }
            return httpx.Response(200, json={
                "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]
            })

        settings = Settings(
            evidence_root=tmp_path,
            vlm_enabled=True,
            vlm_api_key="test-key",
            vlm_model="ecnu-plus",
            vlm_api_base="https://chat.test/v1",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = VisionSafetyService(settings, client)
            await service.set_baseline(FakeCamera())  # type: ignore[arg-type]
            result = await service.analyze(FakeCamera())  # type: ignore[arg-type]
        assert analysis_request_count == 2
        assert result["assessment"]["risk_level"] == "clear"

    asyncio.run(scenario())


def test_baseline_is_rejected_when_object_intrudes_into_foot_path(tmp_path: Path) -> None:
    async def scenario() -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "choices": [{"message": {"content": json.dumps({
                    "visibility": "usable",
                    "hazard_present": True,
                    "hazard_types": ["box"],
                    "position_zone": "center",
                    "walkway_occupation": "quarter_to_half",
                    "walkway_length_occupation": "under_quarter",
                    "passage_effect": "detour",
                    "trip_risk": "possible",
                    "reason": "纸箱伸入门口落脚区域，经过时需要绕脚。",
                }, ensure_ascii=False)}}],
            })

        settings = Settings(
            evidence_root=tmp_path,
            vlm_enabled=True,
            vlm_api_key="test-key",
            vlm_model="ecnu-plus",
            vlm_api_base="https://chat.test/v1",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = VisionSafetyService(settings, client)
            with pytest.raises(UnsafeBaselineError, match="需要绕脚"):
                await service.set_baseline(FakeCamera())  # type: ignore[arg-type]
            assert service.baseline_status()["ready"] is False

    asyncio.run(scenario())


def test_baseline_accepts_normal_storage_at_walkway_edge(tmp_path: Path) -> None:
    async def scenario() -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "choices": [{"message": {"content": json.dumps({
                    "visibility": "usable",
                    "hazard_present": True,
                    "hazard_types": ["box"],
                    "position_zone": "inner_side",
                    "walkway_occupation": "under_quarter",
                    "walkway_length_occupation": "under_quarter",
                    "passage_effect": "none",
                    "trip_risk": "none",
                    "reason": "纸箱位于走道边缘，不影响自然直行和落脚。",
                }, ensure_ascii=False)}}],
            })

        settings = Settings(
            evidence_root=tmp_path,
            vlm_enabled=True,
            vlm_api_key="test-key",
            vlm_model="ecnu-plus",
            vlm_api_base="https://chat.test/v1",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = VisionSafetyService(settings, client)
            result = await service.set_baseline(FakeCamera())  # type: ignore[arg-type]
            assert result["ready"] is True
            assert service.baseline_status()["ready"] is True

    asyncio.run(scenario())


def test_cleaned_task_rechecks_and_changes_copy_when_risk_remains(client) -> None:
    outcomes = iter(["medium", "medium", "clear"])

    async def fake_analyze(_camera) -> dict[str, object]:
        risk = next(outcomes)
        if risk == "clear":
            assessment = {
                "risk_level": "clear",
                "headline": "通道畅通",
                "action_text": "保持通道整洁",
            }
            reason = "当前通道与安全基准图一致，未见新增障碍物。"
        else:
            assessment = {
                "risk_level": "medium",
                "headline": "通道需要整理",
                "action_text": "请将物品移到通道外",
            }
            reason = "纸箱位于通道中部，经过时需要绕开。"
        return {
            "checked_at": "2026-08-22T14:30:00+08:00",
            "prediction": {},
            "assessment": assessment,
            "reason": reason,
            "evidence_path": "test.jpg",
        }

    client.app.state.vision_safety.analyze = fake_analyze

    first = client.post("/api/v1/devices/c6c/safety/analyze").json()
    task_id = first["task_id"]
    assert task_id

    assert client.post(
        f"/api/v1/resident/safety/tasks/{task_id}/actions",
        json={"action": "done"},
    ).status_code == 200
    second = client.post("/api/v1/devices/c6c/safety/analyze").json()
    assert second["recheck"] is True
    assert second["task_id"] == task_id
    assert second["assessment"]["headline"] == "再次检查，通道仍需整理"
    task = client.get("/api/v1/resident/safety").json()["task"]
    assert task["title"] == "再次检查，通道仍需整理"
    assert task["suggestion"] == "通道里仍有物品，请继续移到通道外"

    assert client.post(
        f"/api/v1/resident/safety/tasks/{task_id}/actions",
        json={"action": "done"},
    ).status_code == 200
    third = client.post("/api/v1/devices/c6c/safety/analyze").json()
    assert third["assessment"]["headline"] == "再次检查，通道已经畅通"
    assert client.get("/api/v1/resident/safety").json()["task"] is None


def test_clear_manual_check_resolves_previous_cleanup_task(client) -> None:
    risk = "medium"

    async def fake_analyze(_camera) -> dict[str, object]:
        if risk == "medium":
            assessment = {
                "risk_level": "medium",
                "headline": "通道需要整理",
                "action_text": "请将影响通行的物品移到通道外",
            }
            reason = "纸箱位于通道中部，经过时需要绕开。"
        else:
            assessment = {
                "risk_level": "clear",
                "headline": "通道可以正常通行",
                "action_text": "当前无需整理",
            }
            reason = "纸箱位于走道边缘，剩余宽度足够直行通过。"
        return {
            "checked_at": "2026-08-22T15:00:00+08:00",
            "prediction": {},
            "assessment": assessment,
            "reason": reason,
            "evidence_path": "test.jpg",
        }

    client.app.state.vision_safety.analyze = fake_analyze
    assert client.post("/api/v1/devices/c6c/safety/analyze").json()["task_id"]
    assert client.get("/api/v1/resident/safety").json()["task"] is not None

    risk = "clear"
    result = client.post("/api/v1/devices/c6c/safety/analyze").json()
    assert result["assessment"]["risk_level"] == "clear"
    assert client.get("/api/v1/resident/safety").json()["task"] is None
    latest = client.get("/api/v1/devices/c6c/safety/latest").json()["analysis"]
    assert latest["risk_level"] == "clear"


def test_monitor_analyzes_only_after_a_change_persists(tmp_path: Path) -> None:
    def jpeg(gray: int) -> bytes:
        output = BytesIO()
        Image.new("RGB", (64, 36), (gray, gray, gray)).save(output, format="JPEG")
        return output.getvalue()

    class AutoCamera:
        configured = True

        async def capture(self) -> str:
            return "https://camera.test/changed.jpg"

        async def download_picture(self, _picture_url: str) -> tuple[bytes, str]:
            return jpeg(210), "image/jpeg"

    async def scenario() -> None:
        settings = Settings(
            database_path=tmp_path / "monitor.db",
            evidence_root=tmp_path / "evidence",
            ezviz_device_serial="C6C123",
            ezviz_access_token="test-token",
            vlm_enabled=True,
            vlm_api_key="test-key",
            vlm_model="ecnu-plus",
            vlm_api_base="https://chat.test/v1",
            vlm_change_threshold=0.08,
            vlm_change_confirmations=2,
            ezviz_alarm_detection_enabled=False,
        )
        store = ProductStore(settings.database_path)
        store.initialize()
        service = VisionSafetyService(settings)
        service.root.mkdir(parents=True)
        (service.root / "baseline.jpg").write_bytes(jpeg(30))
        (service.root / "baseline.json").write_text(
            json.dumps({"captured_at": "2026-08-22T15:00:00+08:00", "stale": False}),
            encoding="utf-8",
        )
        analyzed = 0

        async def fake_analyze_image(_image: bytes, _content_type: str) -> dict[str, object]:
            nonlocal analyzed
            analyzed += 1
            return {
                "checked_at": "2026-08-22T15:01:00+08:00",
                "prediction": {},
                "assessment": {
                    "risk_level": "clear",
                    "headline": "通道可以正常通行",
                    "action_text": "当前无需整理",
                },
                "reason": "纸箱位于走道边缘，剩余宽度足够直行通过。",
                "evidence_path": "test.jpg",
            }

        service.analyze_image = fake_analyze_image  # type: ignore[method-assign]
        monitor = VisionChangeMonitor(
            settings,
            AutoCamera(),  # type: ignore[arg-type]
            service,
            store,
        )
        assert await monitor.check_once() is False
        assert analyzed == 0
        assert await monitor.check_once() is True
        assert analyzed == 1
        assert store.recent_checks(1)[0]["source"] == "camera_safety_auto"
        monitor.next_alarm_poll_at = 0.0
        assert await monitor.check_once() is False
        assert analyzed == 1
        await service.close()

    asyncio.run(scenario())


def test_monitor_uses_ezviz_alarm_before_local_confirmations(tmp_path: Path) -> None:
    def jpeg(gray: int) -> bytes:
        output = BytesIO()
        Image.new("RGB", (64, 36), (gray, gray, gray)).save(output, format="JPEG")
        return output.getvalue()

    class AlarmCamera:
        configured = True

        async def alarm_list(self, _start: int, _end: int) -> list[dict[str, object]]:
            return [{"alarmId": "alarm-1", "deviceSerial": "C6C123", "channelNo": 1}]

        async def capture(self) -> str:
            return "https://camera.test/alarm.jpg"

        async def download_picture(self, _picture_url: str) -> tuple[bytes, str]:
            return jpeg(210), "image/jpeg"

    async def scenario() -> None:
        settings = Settings(
            database_path=tmp_path / "alarm-monitor.db",
            evidence_root=tmp_path / "alarm-evidence",
            ezviz_device_serial="C6C123",
            ezviz_access_token="test-token",
            ezviz_alarm_detection_enabled=True,
            ezviz_alarm_settle_seconds=0,
            vlm_enabled=True,
            vlm_api_key="test-key",
            vlm_model="ecnu-plus",
            vlm_api_base="https://chat.test/v1",
            vlm_change_threshold=0.08,
            vlm_change_confirmations=2,
        )
        store = ProductStore(settings.database_path)
        store.initialize()
        service = VisionSafetyService(settings)
        service.root.mkdir(parents=True)
        (service.root / "baseline.jpg").write_bytes(jpeg(30))
        (service.root / "baseline.json").write_text(
            json.dumps({"captured_at": "2026-08-24T12:00:00+08:00", "stale": False}),
            encoding="utf-8",
        )
        analyzed = 0

        async def fake_analyze_image(_image: bytes, _content_type: str) -> dict[str, object]:
            nonlocal analyzed
            analyzed += 1
            return {
                "checked_at": "2026-08-24T12:00:03+08:00",
                "prediction": {},
                "assessment": {
                    "risk_level": "clear",
                    "headline": "通道畅通",
                    "action_text": "保持通道整洁",
                },
                "reason": "通道可以正常通过。",
                "evidence_path": "alarm.jpg",
            }

        service.analyze_image = fake_analyze_image  # type: ignore[method-assign]
        monitor = VisionChangeMonitor(settings, AlarmCamera(), service, store)  # type: ignore[arg-type]

        assert await monitor.check_once() is True
        assert analyzed == 1
        assert store.recent_checks(1)[0]["source"] == "camera_safety_auto"
        await service.close()

    asyncio.run(scenario())


def test_monitor_falls_back_to_local_change_when_alarm_api_times_out(tmp_path: Path) -> None:
    def jpeg(gray: int) -> bytes:
        output = BytesIO()
        Image.new("RGB", (64, 36), (gray, gray, gray)).save(output, format="JPEG")
        return output.getvalue()

    class TimeoutCamera:
        configured = True

        async def alarm_list(self, _start: int, _end: int) -> list[dict[str, object]]:
            raise httpx.ReadTimeout("alarm timeout")

        async def capture(self) -> str:
            return "https://camera.test/fallback.jpg"

        async def download_picture(self, _picture_url: str) -> tuple[bytes, str]:
            return jpeg(210), "image/jpeg"

    async def scenario() -> None:
        settings = Settings(
            database_path=tmp_path / "fallback-monitor.db",
            evidence_root=tmp_path / "fallback-evidence",
            ezviz_device_serial="C6C123",
            ezviz_access_token="test-token",
            ezviz_alarm_detection_enabled=True,
            vlm_enabled=True,
            vlm_api_key="test-key",
            vlm_model="ecnu-plus",
            vlm_api_base="https://chat.test/v1",
            vlm_change_threshold=0.08,
            vlm_change_confirmations=2,
        )
        store = ProductStore(settings.database_path)
        store.initialize()
        service = VisionSafetyService(settings)
        service.root.mkdir(parents=True)
        (service.root / "baseline.jpg").write_bytes(jpeg(30))
        (service.root / "baseline.json").write_text(
            json.dumps({"captured_at": "2026-08-24T12:00:00+08:00", "stale": False}),
            encoding="utf-8",
        )

        async def fake_analyze_image(_image: bytes, _content_type: str) -> dict[str, object]:
            return {
                "checked_at": "2026-08-24T12:00:06+08:00",
                "prediction": {},
                "assessment": {
                    "risk_level": "clear",
                    "headline": "通道畅通",
                    "action_text": "保持通道整洁",
                },
                "reason": "通道可以正常通过。",
                "evidence_path": "fallback.jpg",
            }

        service.analyze_image = fake_analyze_image  # type: ignore[method-assign]
        monitor = VisionChangeMonitor(settings, TimeoutCamera(), service, store)  # type: ignore[arg-type]

        assert await monitor.check_once() is False
        monitor.next_local_check_at = 0.0
        assert await monitor.check_once() is True
        assert store.recent_checks(1)[0]["source"] == "camera_safety_auto"
        await service.close()

    asyncio.run(scenario())


def test_monitor_identifies_baseline_automatically_when_missing(tmp_path: Path) -> None:
    class AutoCamera:
        configured = True

    async def scenario() -> None:
        settings = Settings(
            database_path=tmp_path / "auto-baseline.db",
            evidence_root=tmp_path / "evidence",
            ezviz_device_serial="C6C123",
            ezviz_access_token="test-token",
            vlm_enabled=True,
            vlm_api_key="test-key",
            vlm_model="ecnu-plus",
            vlm_api_base="https://chat.test/v1",
        )
        store = ProductStore(settings.database_path)
        store.initialize()
        service = VisionSafetyService(settings)
        attempts = 0

        async def fake_set_baseline(_camera) -> dict[str, object]:
            nonlocal attempts
            attempts += 1
            service.root.mkdir(parents=True, exist_ok=True)
            (service.root / "baseline.jpg").write_bytes(b"jpeg-image" * 20)
            (service.root / "baseline.json").write_text(
                json.dumps({"captured_at": "2026-08-22T15:30:00+08:00", "stale": False}),
                encoding="utf-8",
            )
            return service.baseline_status()

        service.set_baseline = fake_set_baseline  # type: ignore[method-assign]
        monitor = VisionChangeMonitor(
            settings,
            AutoCamera(),  # type: ignore[arg-type]
            service,
            store,
        )

        assert service.baseline_status()["ready"] is False
        assert await monitor.check_once() is False
        assert attempts == 1
        assert service.baseline_status()["ready"] is True
        await service.close()

    asyncio.run(scenario())


def test_risk_regions_are_sanitized_and_promoted_for_cleanup() -> None:
    normalized = VisionSafetyService._normalize({
        "visibility": "usable",
        "hazard_present": True,
        "hazard_types": ["carton"],
        "position_zone": "center",
        "walkway_occupation": "quarter_to_half",
        "walkway_length_occupation": "under_quarter",
        "passage_effect": "detour",
        "trip_risk": "possible",
        "reason": "纸箱伸入通道，经过时需要绕开。",
        "hazard_regions": [
            {
                "hazard_type": "carton", "label": "纸箱", "risk_level": "low",
                "x1": -20, "y1": 300, "x2": 680.5, "y2": 1100,
            },
            {"hazard_type": "box", "x1": 10, "y1": 10, "x2": 12, "y2": 12},
        ],
    })
    prediction = VisionPrediction.model_validate(normalized)
    assessment = derive_assessment(prediction)
    regions = display_regions(prediction, assessment["risk_level"])

    assert assessment["risk_level"] == "high"
    assert "纸箱" in assessment["action_text"]
    assert regions == [{
        "hazard_type": "box", "label": "纸箱", "risk_level": "high",
        "x1": 0, "y1": 300, "x2": 680, "y2": 1000,
    }]


def test_near_field_box_crossing_foot_path_requires_cleanup() -> None:
    prediction = VisionPrediction.model_validate({
        "visibility": "usable",
        "hazard_present": True,
        "hazard_types": ["box"],
        "position_zone": "inner_side",
        "walkway_occupation": "under_quarter",
        "walkway_length_occupation": "under_quarter",
        "passage_effect": "none",
        "trip_risk": "possible",
        "reason": "纸箱横跨画面近处的常用落脚区域。",
        "hazard_regions": [{
            "hazard_type": "box", "label": "纸箱", "risk_level": "low",
            "x1": 260, "y1": 574, "x2": 720, "y2": 1000,
        }],
    })

    assert derive_assessment(prediction)["risk_level"] == "high"


def test_near_field_box_on_right_side_is_reconciled_with_walkway_geometry() -> None:
    prediction = VisionPrediction.model_validate({
        "visibility": "usable",
        "hazard_present": True,
        "hazard_types": ["box"],
        "position_zone": "inner_side",
        "walkway_occupation": "under_quarter",
        "walkway_length_occupation": "under_quarter",
        "passage_effect": "none",
        "trip_risk": "none",
        "reason": "纸箱位于走道边缘。",
        "hazard_regions": [{
            "hazard_type": "box", "label": "纸箱", "risk_level": "low",
            "x1": 520, "y1": 510, "x2": 860, "y2": 990,
        }],
        "walkway_near_x1": 400,
        "walkway_near_x2": 850,
    })

    reconciled = reconcile_walkway_geometry(prediction)

    assert reconciled.position_zone == "center"
    assert reconciled.walkway_occupation == "over_half"
    assert reconciled.passage_effect == "difficult"
    assert reconciled.trip_risk == "possible"
    assert "通道中央落脚区域" in reconciled.reason
    assert derive_assessment(prediction)["risk_level"] == "high"


def test_automatic_red_alert_is_deduplicated_until_risk_worsens(tmp_path: Path) -> None:
    settings = Settings(database_path=tmp_path / "alerts.db", evidence_root=tmp_path)
    store = ProductStore(settings.database_path)
    store.initialize()

    def result(risk: str) -> dict[str, object]:
        return {
            "checked_at": "2026-08-24T10:00:00+08:00",
            "prediction": {},
            "assessment": {
                "risk_level": risk,
                "headline": "通道通行受阻" if risk == "high" else "通道需要整理",
                "action_text": "请立即清理" if risk == "high" else "请整理通道",
            },
            "reason": "纸箱伸入常用落脚区域。",
            "hazard_regions": [],
            "evidence_path": "test.jpg",
        }

    first = record_safety_result(store, settings, result("medium"), "camera_safety_auto")
    repeated = record_safety_result(store, settings, result("medium"), "camera_safety_auto")
    worsened = record_safety_result(store, settings, result("high"), "camera_safety_auto")

    assert first["notification_required"] is True
    assert first["speech_auto_play"] is True
    assert repeated["notification_required"] is False
    assert repeated["speech_auto_play"] is False
    assert worsened["notification_required"] is True
    assert worsened["speech_auto_play"] is True


def test_manual_red_check_requests_automatic_speech_without_push(tmp_path: Path) -> None:
    settings = Settings(database_path=tmp_path / "manual-speech.db", evidence_root=tmp_path)
    store = ProductStore(settings.database_path)
    store.initialize()
    result = {
        "checked_at": "2026-08-24T10:00:00+08:00",
        "prediction": {},
        "assessment": {
            "risk_level": "medium",
            "headline": "通道需要整理",
            "action_text": "请将纸箱移到通道外",
        },
        "reason": "纸箱伸入通道。",
        "hazard_regions": [],
        "evidence_path": "test.jpg",
    }

    recorded = record_safety_result(store, settings, result, "camera_safety")

    assert recorded["notification_required"] is False
    assert recorded["speech_auto_play"] is True


def test_latest_analysis_exposes_regions_and_cached_tts_route(client) -> None:
    async def fake_analyze(_camera) -> dict[str, object]:
        return {
            "checked_at": "2026-08-24T10:00:00+08:00",
            "prediction": {},
            "assessment": {
                "risk_level": "high",
                "headline": "通道通行受阻",
                "action_text": "请立即将纸箱移到通道外",
            },
            "reason": "纸箱挡住常用行走路线。",
            "hazard_regions": [{
                "hazard_type": "box", "label": "纸箱", "risk_level": "high",
                "x1": 100, "y1": 300, "x2": 650, "y2": 900,
            }],
            "evidence_path": "test.jpg",
        }

    async def fake_audio(check_id: str, text: str) -> bytes:
        assert check_id
        assert "纸箱" in text
        return b"ID3" + b"audio" * 40

    client.app.state.vision_safety.analyze = fake_analyze
    client.app.state.vision_safety.warning_audio = fake_audio
    created = client.post("/api/v1/devices/c6c/safety/analyze")
    assert created.status_code == 200
    latest = client.get("/api/v1/devices/c6c/safety/latest").json()["analysis"]
    assert latest["hazard_regions"][0]["label"] == "纸箱"
    assert latest["speech_auto_play"] is True
    assert latest["speech_url"].endswith("/speech")
    speech = client.get(latest["speech_url"])
    assert speech.status_code == 200
    assert speech.headers["content-type"].startswith("audio/mpeg")


def test_later_action_hides_cleanup_until_reminder_time(client) -> None:
    async def fake_analyze(_camera) -> dict[str, object]:
        return {
            "checked_at": "2026-08-24T10:00:00+08:00",
            "prediction": {},
            "assessment": {
                "risk_level": "medium",
                "headline": "通道需要整理",
                "action_text": "请将纸箱移到通道外",
            },
            "reason": "纸箱伸入通道。",
            "hazard_regions": [],
            "evidence_path": "test.jpg",
        }

    client.app.state.vision_safety.analyze = fake_analyze
    task_id = client.post("/api/v1/devices/c6c/safety/analyze").json()["task_id"]
    response = client.post(
        f"/api/v1/resident/safety/tasks/{task_id}/actions",
        json={"action": "later"},
    )
    assert response.status_code == 200
    assert client.get("/api/v1/resident/safety").json()["task"] is None
    deferred = client.app.state.store.latest_task(include_deferred=True)
    assert deferred["status"] == "deferred"
    assert deferred["remind_at"]
