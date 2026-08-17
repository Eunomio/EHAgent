import asyncio

import httpx

from app.core.config import Settings
from app.llm.service import LlmService


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
