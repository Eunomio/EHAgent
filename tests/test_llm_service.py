import asyncio
import json

import httpx

from app.core.config import Settings
from app.llm.service import LlmService


def test_sleep_care_prompt_and_unavailable_response() -> None:
    async def scenario() -> None:
        def handler(request):
            body = json.loads(request.content)
            assert "不要按轮次背固定台词" in body["instructions"]
            assert "未来意愿" in body["instructions"]
            assert "trigger_report" in body["input"]
            return httpx.Response(200, json={"output": [{"type": "message", "content": [
                {"type": "output_text", "text": "您说是噪声吵醒的，后来安静下来了吗？"}
            ]}]})

        settings = Settings(llm_enabled=True, llm_api_key="test", llm_model="test")
        context = {"sleep_care": {"trigger_report": {"report_date": "2026-08-27"}}}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            service = LlmService(settings, http)
            reply, _, source = await service.chat_assistant("是楼下太吵", context, [])
            assert source == "llm"
            assert "噪声" in reply
            settings.llm_enabled = False
            reply, _, source = await service.chat_assistant("我睡不着", context, [])
            assert source == "unavailable"
            assert "连不上" in reply
            assert "白噪音" not in reply

    asyncio.run(scenario())


def test_structured_safety_copy_from_responses_api() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/responses"
            assert request.headers["Authorization"] == "Bearer test-key"
            return httpx.Response(200, json={
                "output": [{
                    "type": "message",
                    "content": [{
                        "type": "output_text",
                        "text": (
                            '{"title":"走道上有纸箱",'
                            '"explanation":"卧室外的走道上放着纸箱，经过时需要留意。",'
                            '"suggestion":"请把纸箱移到走道外。"}'
                        ),
                    }],
                }]
            })

        settings = Settings(
            llm_enabled=True, llm_api_key="test-key", llm_model="test-model",
            llm_api_base="https://example.test/v1",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = LlmService(settings, client)
            copy, source = await service.explain_safety("卧室外走道", "纸箱", "纸箱侵入走道")
        assert source == "llm"
        assert copy.title == "走道中有纸箱"
        assert copy.explanation == "卧室外的走道上放着纸箱，经过时需要留意。"

    asyncio.run(scenario())


def test_invalid_llm_output_uses_template() -> None:
    async def scenario() -> None:
        transport = httpx.MockTransport(
            lambda _: httpx.Response(200, json={"output": []})
        )
        settings = Settings(
            llm_enabled=True, llm_api_key="test-key", llm_model="test-model",
            llm_api_base="https://example.test/v1",
        )
        async with httpx.AsyncClient(transport=transport) as client:
            service = LlmService(settings, client)
            copy, source = await service.explain_safety("卧室外走道", "纸箱", "纸箱侵入走道")
        assert source == "template"
        assert copy.suggestion == "建议将纸箱移到走道外。"

    asyncio.run(scenario())


def test_assistant_enables_web_search_and_returns_sources() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = request.read().decode("utf-8")
            assert '"type":"web_search"' in body.replace(" ", "")
            return httpx.Response(200, json={
                "output": [{
                    "type": "message",
                    "content": [{
                        "type": "output_text",
                        "text": "上海今天有雨，出门请带伞。",
                        "annotations": [{
                            "type": "url_citation",
                            "title": "天气信息",
                            "url": "https://example.test/weather",
                        }],
                    }],
                }]
            })

        settings = Settings(
            llm_enabled=True, llm_api_key="test-key", llm_model="test-model",
            llm_api_base="https://example.test/v1",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = LlmService(settings, client)
            reply, sources, source = await service.chat_assistant("今天出门带伞吗？", {}, [])
        assert source == "llm"
        assert "带伞" in reply
        assert sources == [{
            "title": "天气信息", "url": "https://example.test/weather"
        }]

    asyncio.run(scenario())


def test_assistant_formats_markdown_and_requests_self_help_first() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = request.read().decode("utf-8")
            assert "低负担" in body
            assert "第一轮不要直接要求尽快就医" in body
            assert "起夜后难以再次入睡" in body
            return httpx.Response(200, json={
                "output": [{
                    "type": "message",
                    "content": [{
                        "type": "output_text",
                        "text": "## 可以先这样做\n\n1. **听一会儿白噪音**",
                    }],
                }]
            })

        settings = Settings(
            llm_enabled=True, llm_api_key="test-key", llm_model="test-model",
            llm_api_base="https://example.test/v1",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = LlmService(settings, client)
            reply, _, source = await service.chat_assistant(
                "我起夜以后很难再次入睡", {}, []
            )
        assert source == "llm"
        assert reply == "可以先这样做\n听一会儿白噪音"
        assert "**" not in reply

    asyncio.run(scenario())


def test_llm_semantically_selects_camera_tool_without_device_keyword() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = request.read().decode("utf-8")
            assert "inspect_home_safety" in body
            assert "帮我确认一下家里现在是否安全" in body
            return httpx.Response(200, json={
                "output": [{
                    "type": "message",
                    "content": [{
                        "type": "output_text",
                        "text": (
                            '{"tool_name":"inspect_home_safety",'
                            '"reason":"用户希望查看当前居家环境",'
                            '"confidence":0.96}'
                        ),
                    }],
                }]
            })

        settings = Settings(
            llm_enabled=True, llm_api_key="test-key", llm_model="test-model",
            llm_api_base="https://example.test/v1",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = LlmService(settings, client)
            decision, source = await service.plan_device_tool(
                "帮我确认一下家里现在是否安全",
                {"camera_configured": True},
            )
        assert source == "llm"
        assert decision.tool_name == "inspect_home_safety"
        assert decision.confidence == 0.96

    asyncio.run(scenario())
