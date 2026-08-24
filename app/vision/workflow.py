from typing import Any

from app.core.config import Settings
from app.store import ProductStore


def record_safety_result(
    store: ProductStore,
    settings: Settings,
    result: dict[str, Any],
    source: str = "camera_safety",
) -> dict[str, Any]:
    current_task = store.latest_task()
    recheck_task = (
        current_task
        if current_task and current_task["status"] == "rescan_pending"
        else None
    )
    assessment = result["assessment"]
    reason = result["reason"]
    risk_level = assessment["risk_level"]
    check = store.add_safety_check(risk_level, source, reason)
    task = None

    if recheck_task and risk_level in {"medium", "high"}:
        if risk_level == "high":
            title = "再次检查，通道仍然受阻"
            action_text = "仍有物品影响通行，请尽快清理"
        else:
            title = "再次检查，通道仍需整理"
            action_text = "通道里仍有物品，请继续移到通道外"
        assessment.update({"headline": title, "action_text": action_text})
        task = store.update_safety_task(
            recheck_task["id"],
            title=title,
            explanation=f"再次检查后，{reason}",
            suggestion=action_text,
        )
    elif recheck_task and risk_level == "insufficient":
        title = "再次检查时暂时看不清"
        action_text = "请调整光线后再检查一次"
        assessment.update({"headline": title, "action_text": action_text})
        task = store.update_safety_task(
            recheck_task["id"],
            title=title,
            explanation=reason,
            suggestion=action_text,
        )
    elif risk_level in {"clear", "low"}:
        if current_task:
            store.resolve_safety_task(current_task["id"])
        if recheck_task:
            if risk_level == "clear":
                assessment.update({
                    "headline": "再次检查，通道已经畅通",
                    "action_text": "整理已经完成",
                })
            else:
                assessment.update({
                    "headline": "再次检查，通道可以正常通行",
                    "action_text": "当前无需继续整理",
                })
    elif risk_level in {"medium", "high"} and current_task:
        task = store.update_safety_task(
            current_task["id"],
            title=assessment["headline"],
            explanation=reason,
            suggestion=assessment["action_text"],
        )
    elif risk_level in {"medium", "high"}:
        task = store.create_safety_task(
            title=assessment["headline"],
            location=settings.safety_area_name,
            explanation=reason,
            suggestion=assessment["action_text"],
            source=source,
        )
    elif current_task:
        task = current_task

    return {
        **result,
        "recheck": recheck_task is not None,
        "check_id": check["id"],
        "task_id": task["id"] if task else None,
    }
