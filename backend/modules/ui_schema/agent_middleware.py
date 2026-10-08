from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


def create_tool_error_middleware():
    """Convert provider/tool argument errors into recoverable ToolMessages.

    Execution-limit and cancellation exceptions must keep propagating so the
    backend can stop the run immediately.
    """
    try:
        from langchain.agents.middleware import wrap_tool_call
        from langchain.messages import ToolMessage
        from langchain.tools.tool_node import ToolCallRequest
    except ImportError as exc:
        raise RuntimeError("LangChain tool middleware is not installed") from exc

    @wrap_tool_call
    def handle_ui_schema_tool_error(
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ):
        try:
            return handler(request)
        except Exception as exc:
            if exc.__class__.__name__ in {"AgentRunStopped", "AgentRunCancellation", "AgentRunCompleted"}:
                raise
            tool_call = getattr(request, "tool_call", {})
            tool_call_id = (
                str(tool_call.get("id") or "")
                if isinstance(tool_call, dict)
                else str(getattr(tool_call, "id", "") or "")
            )
            payload = {
                "ok": False,
                "error": _short_error(exc),
                "hint": _tool_error_hint(_tool_name(tool_call), exc),
            }
            return ToolMessage(
                content=json.dumps(payload, ensure_ascii=False),
                tool_call_id=tool_call_id,
            )

    return handle_ui_schema_tool_error


def _short_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    return text[:1000]


def _tool_name(tool_call: Any) -> str:
    if isinstance(tool_call, dict):
        return str(tool_call.get("name") or "")
    return str(getattr(tool_call, "name", "") or "")


def _tool_error_hint(tool_name: str, exc: Exception) -> str:
    del exc
    common = (
        "Исправь только технически неверные аргументы и следуй workflow_context.next_action. "
        "Передавай обычные JSON-объекты и массивы без Markdown. Не повторяй тот же payload."
    )
    if tool_name == "apply_ui_schema_changes":
        return (
            common
            + " create_pages содержит новые страницы, а upsert_elements — точечные изменения с page_id, title, description и elements; "
            "поле id допустимо только как технический алиас page_id. Для нового корневого элемента "
            "страницы parent_id можно не указывать, для дочернего нужен точный parent_id. В app.json "
            "используй только app-типы: текст верхней панели — app_text, действие — app_action, "
            "навигация — menu_item. Дочерняя колонка table использует table_column. Вложенные children технически разворачиваются в отдельные upsert-операции без неявного перемещения. При ошибке откатывается только текущий вызов; повтори его исправленный пакет, но не повторяй изменения из ранее успешных вызовов."
        )
    if tool_name == "write_ui_schema_coverage_plan_batch":
        return (
            common
            + " Передай только оставшиеся requirement ID из current_requirement_batch_context. "
            "ID группы backend определяет сам. Для каждого требования нужны согласованные ui_effect, "
            "classification, targets и note."
        )
    if tool_name == "review_ui_schema_coverage_plan":
        return (
            common
            + " Передай полный CoveragePlanItem только для оставшихся candidate ID из "
            "quality_review_context. ID review-группы backend определяет сам; уже принятые записи "
            "не повторяй."
        )
    if tool_name == "write_ui_schema_traceability_batch":
        return (
            common
            + " Передай только оставшиеся requirement ID из текущего контекста. ID группы backend "
            "определяет сам. Используй единый TraceabilityItem; direct_ui требует targets с "
            "implementation_status, остальные классы передаются без целей."
        )
    if tool_name == "review_ui_schema_traceability":
        return (
            common
            + " Передай полный TraceabilityItem только для оставшихся candidate ID из "
            "quality_review_context. ID review-группы backend определяет сам; уже принятые записи "
            "не повторяй."
        )
    if tool_name == "finalize_ui_schema_changes":
        return (
            common
            + " Если возвращены blocking gaps, внеси недостающие изменения либо пересмотри только указанные "
            "пункты через revise_ui_schema_coverage_plan. Неблокирующие observations учитывай при итоговом implementation_status."
        )
    if tool_name == "revise_ui_schema_coverage_plan":
        return (
            common
            + " Передай полные replacement items только для перечисленных requirement ID и объясни "
            "изменение действия или цели. Для reuse/extend используй существующую точную пару target_type/target_id; "
            "если ID существует как страница, не объявляй его ui_element."
        )
    return common
