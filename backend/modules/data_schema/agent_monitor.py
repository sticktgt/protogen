from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from backend.modules.data_schema.agent_events import (
    add_token_usage,
    append_event,
    elapsed_seconds,
    increment_metric,
    read_metrics,
    reserve_metric_slot,
    update_metrics,
)
from backend.modules.data_schema.agent_paths import run_file, run_root
from backend.modules.data_schema.agent_tool_observability import (
    extract_tool_args,
    recoverable_tool_error,
    tool_argument_shape,
    tool_file_count,
    tool_message,
    tool_path,
    tool_signature,
)
from backend.modules.data_schema.files import read_json


class AgentRunStopped(RuntimeError):
    """Raised when an agent run reaches a configured execution limit."""


class AgentRepeatedToolStopped(AgentRunStopped):
    """Raised when a model repeats an identical tool call during one invocation."""


class AgentRunCancellation(RuntimeError):
    """Raised at the next callback boundary after cancellation is requested."""


def create_run_callback(
    *,
    module_root: Path,
    run_id: str,
    limits: dict[str, int],
):
    try:
        from langchain_core.callbacks import BaseCallbackHandler
    except ImportError as exc:
        raise RuntimeError("LangChain callback support is not installed") from exc

    class DataSchemaRunCallback(BaseCallbackHandler):
        raise_error = True

        def __init__(self) -> None:
            super().__init__()
            self._model_runs: set[str] = set()
            self._tool_runs: dict[str, str] = {}
            self._last_tool_signature = ""
            self._same_tool_streak = 0

        def on_chat_model_start(
            self,
            serialized: dict[str, Any],
            messages: list[list[Any]],
            *,
            run_id: UUID,
            **kwargs: Any,
        ) -> None:
            key = str(run_id)
            if key in self._model_runs:
                return
            self._model_runs.add(key)
            _check_cancellation(module_root, run_id_outer)
            pending_reason = _limit_reason(module_root, run_id_outer, limits)
            if pending_reason:
                raise AgentRunStopped(pending_reason)
            maximum = limits["max_llm_calls"]
            metrics = reserve_metric_slot(
                module_root,
                run_id_outer,
                "llm_calls",
                maximum=maximum,
                last_llm_started_at=_now_iso(),
            )
            if metrics is None:
                raise AgentRunStopped(f"Достигнут лимит вызовов LLM: {maximum}")
            number = int(metrics.get("llm_calls", 0))
            append_event(
                module_root,
                run_id_outer,
                event_type="llm_start",
                message=f"Вызов LLM #{number} начат",
                data={"llm_call": number, "messages": _message_count(messages)},
            )

        def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
            key = str(run_id)
            usage = _extract_usage(response)
            if usage:
                metrics = add_token_usage(module_root, run_id_outer, **usage)
                token_text = (
                    f"вход {usage['input_tokens']}, выход {usage['output_tokens']}, "
                    f"всего {usage['total_tokens']}"
                )
            else:
                metrics = update_metrics(module_root, run_id_outer, last_llm_completed_at=_now_iso())
                token_text = "провайдер не вернул статистику токенов"
            append_event(
                module_root,
                run_id_outer,
                event_type="llm_end",
                message=f"Вызов LLM завершён: {token_text}",
                data=usage or {},
            )
            self._model_runs.discard(key)
            pending_reason = _limit_reason(module_root, run_id_outer, limits)
            if pending_reason:
                update_metrics(
                    module_root,
                    run_id_outer,
                    limit_pending_reason=pending_reason,
                )
                append_event(
                    module_root,
                    run_id_outer,
                    event_type="limit_pending",
                    level="warning",
                    message=(
                        pending_reason
                        + ". Завершённый ответ будет обработан; новый вызов LLM не начнётся"
                    ),
                )

        def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
            self._model_runs.discard(str(run_id))
            append_event(
                module_root,
                run_id_outer,
                event_type="llm_error",
                level="error",
                message=f"Ошибка вызова LLM: {_short_error(error)}",
            )

        def on_tool_start(
            self,
            serialized: dict[str, Any],
            input_str: Any,
            *,
            run_id: UUID,
            **kwargs: Any,
        ) -> None:
            _check_cancellation(module_root, run_id_outer)
            maximum = limits["max_tool_calls"]

            serialized = serialized if isinstance(serialized, dict) else {}
            name = str(serialized.get("name") or kwargs.get("name") or "tool")
            args = extract_tool_args(input_str)
            signature = tool_signature(name, args)
            if signature == self._last_tool_signature:
                self._same_tool_streak += 1
            else:
                self._last_tool_signature = signature
                self._same_tool_streak = 1
            repeated_limit = limits["max_repeated_tool_calls"]
            if self._same_tool_streak > repeated_limit:
                raise AgentRepeatedToolStopped(
                    f"Остановлен повторяющийся вызов инструмента {name}: "
                    f"одинаковые аргументы использованы более {repeated_limit} раз подряд"
                )

            current_metrics = read_metrics(module_root, run_id_outer)
            metrics = reserve_metric_slot(
                module_root,
                run_id_outer,
                "tool_calls",
                maximum=maximum,
                last_tool=name,
                repeat_streak=self._same_tool_streak,
                max_repeat_streak=max(
                    int(current_metrics.get("max_repeat_streak", 0)),
                    self._same_tool_streak,
                ),
            )
            if metrics is None:
                raise AgentRunStopped(f"Достигнут лимит вызовов инструментов: {maximum}")
            self._tool_runs[str(run_id)] = name
            path = tool_path(args)
            file_count = tool_file_count(args)
            safe_data = {
                "tool": name,
                "path": path,
                "file_count": file_count,
                "tool_call": metrics.get("tool_calls", 0),
                "offset": _safe_int(args.get("offset")),
                "limit": _safe_int(args.get("limit")),
                "repeat_streak": self._same_tool_streak,
                "argument_digest": signature[:16],
                "argument_shape": tool_argument_shape(args),
            }
            append_event(
                module_root,
                run_id_outer,
                event_type="tool_start",
                message=tool_message(name, path),
                data={key: value for key, value in safe_data.items() if value is not None and value != ""},
            )

        def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
            name = self._tool_runs.pop(str(run_id), str(kwargs.get("name") or "tool"))
            recoverable_error = recoverable_tool_error(output)
            if recoverable_error:
                append_event(
                    module_root,
                    run_id_outer,
                    event_type="tool_rejected",
                    level="warning",
                    message=f"Инструмент {name} отклонил операцию: {recoverable_error}",
                    data={"tool": name},
                )
            else:
                validation = _validation_result(output) if name == "validate_data_schema_state" else None
                if validation is not None:
                    error_count = len(validation.get("errors", []))
                    append_event(
                        module_root,
                        run_id_outer,
                        event_type="validation_result",
                        level="info" if validation.get("valid") else "warning",
                        message=(
                            "Проверка пройдена; запуск завершается без дополнительного вызова LLM"
                            if validation.get("valid")
                            else f"Проверка не пройдена: ошибок {error_count}"
                        ),
                        data={
                            "tool": name,
                            "valid": bool(validation.get("valid")),
                            "error_count": error_count,
                        },
                    )
                else:
                    append_event(
                        module_root,
                        run_id_outer,
                        event_type="tool_end",
                        message=f"Инструмент завершил работу: {name}",
                        data={"tool": name},
                    )
            _check_cancellation(module_root, run_id_outer)

        def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
            name = self._tool_runs.pop(str(run_id), str(kwargs.get("name") or "tool"))
            append_event(
                module_root,
                run_id_outer,
                event_type="tool_error",
                level="error",
                message=f"Ошибка инструмента {name}: {_short_error(error)}",
                data={"tool": name},
            )

    run_id_outer = run_id
    return DataSchemaRunCallback()


def _validation_result(output: Any) -> dict[str, Any] | None:
    content = getattr(output, "content", output)
    if isinstance(content, list):
        text_parts = [
            str(item.get("text") or "")
            for item in content
            if isinstance(item, dict)
        ]
        content = "".join(text_parts)
    if not isinstance(content, str):
        return None
    try:
        import json

        payload = json.loads(content)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) and "valid" in payload else None


def _check_cancellation(module_root: Path, run_id_value: str) -> None:
    run = read_json(run_file(module_root, run_id_value), {})
    if run.get("status") in {"cancelling", "cancelled"}:
        raise AgentRunCancellation("Задача отменена пользователем")


def _limit_reason(
    module_root: Path,
    run_id_value: str,
    limits: dict[str, int],
) -> str:
    metrics = read_metrics(module_root, run_id_value)
    maximum_tokens = limits["max_total_tokens"]
    if int(metrics.get("total_tokens", 0)) > maximum_tokens:
        return f"Превышен лимит токенов: {maximum_tokens}"
    started_at = metrics.get("started_at")
    if elapsed_seconds(str(started_at or "")) > limits["max_duration_seconds"]:
        return (
            "Превышен максимальный срок выполнения: "
            f"{limits['max_duration_seconds']} секунд"
        )
    return ""


def _message_count(messages: Any) -> int:
    if not isinstance(messages, list):
        return 0
    return sum(len(group) for group in messages if isinstance(group, list))


def _extract_usage(response: Any) -> dict[str, int] | None:
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    found = False
    generations = getattr(response, "generations", None)
    if isinstance(generations, list):
        for group in generations:
            if not isinstance(group, list):
                continue
            for generation in group:
                message = getattr(generation, "message", None)
                usage = getattr(message, "usage_metadata", None)
                if isinstance(usage, dict):
                    _merge_usage(totals, usage)
                    found = True
    if not found:
        output = getattr(response, "llm_output", None)
        if isinstance(output, dict):
            usage = output.get("token_usage") or output.get("usage")
            if isinstance(usage, dict):
                _merge_usage(totals, usage)
                found = True
    if not found:
        return None
    if totals["total_tokens"] <= 0:
        totals["total_tokens"] = totals["input_tokens"] + totals["output_tokens"]
    return totals


def _reported_model(response: Any) -> str:
    """Return the provider-reported model name when response metadata exposes it."""
    output = getattr(response, "llm_output", None)
    if isinstance(output, dict):
        for key in ("model_name", "model", "model_id"):
            value = output.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    generations = getattr(response, "generations", None)
    if not isinstance(generations, list):
        return ""
    for group in generations:
        if not isinstance(group, list):
            continue
        for generation in group:
            message = getattr(generation, "message", None)
            metadata = getattr(message, "response_metadata", None)
            if isinstance(metadata, dict):
                for key in ("model_name", "model", "model_id"):
                    value = metadata.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
            info = getattr(generation, "generation_info", None)
            if isinstance(info, dict):
                for key in ("model_name", "model", "model_id"):
                    value = info.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
    return ""


def _merge_usage(target: dict[str, int], usage: dict[str, Any]) -> None:
    target["input_tokens"] += _usage_int(usage, "input_tokens", "prompt_tokens")
    target["output_tokens"] += _usage_int(usage, "output_tokens", "completion_tokens")
    target["total_tokens"] += _usage_int(usage, "total_tokens")


def _usage_int(usage: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, (int, float)):
            return max(0, int(value))
    return 0


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _short_error(error: BaseException) -> str:
    text = str(error).strip() or error.__class__.__name__
    return text[:500]


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
