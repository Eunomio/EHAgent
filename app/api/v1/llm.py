from typing import Any

from fastapi import APIRouter

from app.dependencies import LlmDep, StoreDep

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/status")
def llm_status(llm: LlmDep, store: StoreDep) -> dict[str, Any]:
    return {
        "enabled": llm.settings.llm_enabled,
        "configured": llm.configured,
        "provider": llm.settings.llm_provider,
        "model": llm.settings.llm_model,
        "fallback": "template",
        "usage": store.llm_stats(),
    }


@router.post("/test")
async def test_llm(llm: LlmDep) -> dict[str, Any]:
    digest, source = await llm.summarize_feedback("product", "今天使用页面很顺利")
    return {"success": source == "llm", "source": source, "result": digest.model_dump()}
