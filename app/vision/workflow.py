from typing import Any

from app.core.config import Settings
from app.store import ProductStore, now_iso


def record_safety_result(
    store: ProductStore,
    settings: Settings,
    result: dict[str, Any],
    source: str = "camera_safety",
) -> dict[str, Any]:
    previous_checks = store.recent_checks(1)
    previous_risk = previous_checks[0]["result"] if previous_checks else None
    current_task = store.latest_task(include_deferred=True)
    deferred_ready = bool(
        current_task
        and current_task["status"] == "deferred"
        and (
            not current_task.get("remind_at")
            or str(current_task["remind_at"]) <= now_iso()
        )
    )
    recheck_task = (
        current_task
        if current_task and current_task["status"] == "rescan_pending"
        else None
    )
    assessment = result["assessment"]
    reason = result["reason"]
    risk_level = assessment["risk_level"]
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
        if current_task["status"] == "deferred" and not deferred_ready:
            task = current_task
        else:
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

    is_new_alert = bool(
        risk_level in {"medium", "high"}
        and (
            previous_risk not in {"medium", "high"}
            or (risk_level == "high" and previous_risk != "high")
            or deferred_ready
        )
    )
    notification_required = source == "camera_safety_auto" and is_new_alert
    speech_auto_play = bool(
        risk_level in {"medium", "high"}
        and (source != "camera_safety_auto" or is_new_alert)
    )
    stored_result = {
        **result,
        "notification_required": notification_required,
        "speech_auto_play": speech_auto_play,
    }
    check = store.add_safety_check(
        risk_level,
        source,
        reason,
        result.get("evidence_path"),
        stored_result,
    )

    return {
        **stored_result,
        "recheck": recheck_task is not None,
        "check_id": check["id"],
        "task_id": task["id"] if task else None,
    }
