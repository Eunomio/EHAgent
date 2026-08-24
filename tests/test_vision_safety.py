import asyncio
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
)


class FakeCamera:
    async def capture(self) -> str:
        return "https://camera.test/capture.jpg"

    async def download_picture(self, picture_url: str) -> tuple[bytes, str]:
        assert picture_url == "https://camera.test/capture.jpg"
        return b"jpeg-image" * 20, "image/jpeg"


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


def test_uncertain_trip_risk_at_edge_does_not_require_cleanup() -> None:
    prediction = VisionPrediction(
        visibility="usable",
        hazard_present=True,
        hazard_types=["box"],
        position_zone="inner_side",
        walkway_occupation="under_quarter",
        walkway_length_occupation="under_quarter",
        passage_effect="none",
        trip_risk="possible",
        reason="纸箱靠近走道边缘，没有观察到需要绕脚或跨越。",
    )
    assessment = derive_assessment(prediction)
    assert assessment["risk_level"] == "low"
    assert assessment["headline"] == "通道可以通行"


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
