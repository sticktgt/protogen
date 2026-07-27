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
                "hint": (
                    "Исправь аргументы и продолжи ограниченный цикл. Передавай native JSON "
                    "objects/arrays, не JSON-строки и не markdown code fences."
                ),
            }
            return ToolMessage(
                content=json.dumps(payload, ensure_ascii=False),
                tool_call_id=tool_call_id,
            )

    return handle_ui_schema_tool_error


def _short_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    return text[:1000]
