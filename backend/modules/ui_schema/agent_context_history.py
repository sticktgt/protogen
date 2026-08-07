from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

_DEFAULT_KEEP_CHANGE_EXCHANGES = 1


@dataclass(frozen=True)
class ToolExchange:
    start: int
    end: int
    tool_names: tuple[str, ...]


def context_history_settings(agent_config: dict[str, Any] | None) -> dict[str, Any]:
    config = agent_config if isinstance(agent_config, dict) else {}
    context = config.get("context", {})
    context = context if isinstance(context, dict) else {}
    history = context.get("history_compaction", {})
    history = history if isinstance(history, dict) else {}
    try:
        keep_change_exchanges = int(
            history.get("keep_change_bundle_exchanges", _DEFAULT_KEEP_CHANGE_EXCHANGES)
        )
    except (TypeError, ValueError):
        keep_change_exchanges = _DEFAULT_KEEP_CHANGE_EXCHANGES
    return {
        "enabled": bool(history.get("enabled", True)),
        "keep_change_bundle_exchanges": max(1, keep_change_exchanges),
    }


def create_context_history_middleware(agent_config: dict[str, Any] | None):
    """Create bounded-history middleware for the tool-driven synchronization loop.

    The workflow persists its authoritative state in run files. Keeping every previous
    requirement batch, review batch and model payload in chat history causes the input
    context to grow on every step without adding useful information. The middleware
    retains the stable schema anchor and only the exchanges needed for the current stage.
    It does not summarize or interpret requirements.
    """

    settings = context_history_settings(agent_config)
    if not settings["enabled"]:
        return None

    try:
        from langchain.agents.middleware import before_model
        from langchain.messages import RemoveMessage
        from langgraph.graph.message import REMOVE_ALL_MESSAGES
    except ImportError as exc:
        raise RuntimeError("LangChain context-history middleware is not installed") from exc

    @before_model
    def compact_ui_schema_history(state: Any, runtime: Any) -> dict[str, Any] | None:
        del runtime
        messages = _state_messages(state)
        compacted = compact_agent_messages(
            messages,
            keep_change_bundle_exchanges=settings["keep_change_bundle_exchanges"],
        )
        if len(compacted) == len(messages) and all(
            left is right for left, right in zip(compacted, messages)
        ):
            return None
        return {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                *compacted,
            ]
        }

    return compact_ui_schema_history


def compact_agent_messages(
    messages: list[Any],
    *,
    keep_change_bundle_exchanges: int = _DEFAULT_KEEP_CHANGE_EXCHANGES,
) -> list[Any]:
    """Return a protocol-valid bounded message history.

    Retained information:
    - the initial human instruction;
    - a sanitized initial synchronization-context exchange as the stable schema anchor;
    - the final coverage-review exchange while schema changes are being prepared;
    - recent transactional change exchanges while tracing their resulting targets;
    - the latest tool exchange, which carries the current batch or repair result.

    Previous requirement/review batches are intentionally discarded because their
    accepted results are already stored in result files and supplied again when needed.
    """

    if len(messages) <= 3:
        return list(messages)

    exchanges = _tool_exchanges(messages)
    if not exchanges:
        return _first_human_and_recent(messages)

    latest = exchanges[-1]
    latest_names = set(latest.tool_names)
    keep: set[int] = set()

    first_human = _first_human_index(messages)
    if first_human is not None:
        keep.add(first_human)

    load_exchange = next(
        (item for item in exchanges if "load_synchronization_context" in item.tool_names),
        None,
    )
    if load_exchange is not None:
        _add_exchange_indices(keep, load_exchange)

    traceability_started = bool(
        latest_names
        & {
            "write_ui_schema_traceability_batch",
            "review_ui_schema_traceability",
        }
    )

    if not traceability_started:
        final_coverage_review = _last_exchange(
            exchanges,
            "review_ui_schema_coverage_plan",
        )
        if final_coverage_review is not None:
            _add_exchange_indices(keep, final_coverage_review)

    change_exchanges = [
        item for item in exchanges if "apply_ui_schema_changes" in item.tool_names
    ]
    for item in change_exchanges[-max(1, int(keep_change_bundle_exchanges)) :]:
        _add_exchange_indices(keep, item)

    _add_exchange_indices(keep, latest)

    compacted: list[Any] = []
    for index in sorted(keep):
        message = messages[index]
        if (
            load_exchange is not None
            and latest is not load_exchange
            and load_exchange.start < index < load_exchange.end
            and _is_tool_message(message)
        ):
            message = _sanitize_load_context_message(message)
        compacted.append(message)
    return compacted


def _state_messages(state: Any) -> list[Any]:
    if isinstance(state, dict):
        value = state.get("messages", [])
    else:
        value = getattr(state, "messages", [])
    return list(value) if isinstance(value, list) else []


def _tool_exchanges(messages: list[Any]) -> list[ToolExchange]:
    result: list[ToolExchange] = []
    index = 0
    while index < len(messages):
        names = _ai_tool_names(messages[index])
        if not names:
            index += 1
            continue
        end = index + 1
        while end < len(messages) and _is_tool_message(messages[end]):
            end += 1
        if end > index + 1:
            result.append(
                ToolExchange(
                    start=index,
                    end=end,
                    tool_names=tuple(names),
                )
            )
        index = max(end, index + 1)
    return result


def _ai_tool_names(message: Any) -> list[str]:
    if isinstance(message, dict):
        calls = message.get("tool_calls", [])
    else:
        calls = getattr(message, "tool_calls", [])
    result: list[str] = []
    for call in calls if isinstance(calls, list) else []:
        if isinstance(call, dict):
            name = str(call.get("name") or "").strip()
        else:
            name = str(getattr(call, "name", "") or "").strip()
        if name:
            result.append(name)
    return result


def _is_tool_message(message: Any) -> bool:
    if isinstance(message, dict):
        return str(message.get("role") or message.get("type") or "").lower() == "tool"
    message_type = str(getattr(message, "type", "") or "").lower()
    return message_type == "tool" or message.__class__.__name__ == "ToolMessage"


def _is_human_message(message: Any) -> bool:
    if isinstance(message, dict):
        return str(message.get("role") or message.get("type") or "").lower() in {
            "user",
            "human",
        }
    message_type = str(getattr(message, "type", "") or "").lower()
    return message_type in {"user", "human"} or message.__class__.__name__ == "HumanMessage"


def _first_human_index(messages: list[Any]) -> int | None:
    for index, message in enumerate(messages):
        if _is_human_message(message):
            return index
    return 0 if messages else None


def _first_human_and_recent(messages: list[Any]) -> list[Any]:
    first = _first_human_index(messages)
    indices = {index for index in range(max(0, len(messages) - 2), len(messages))}
    if first is not None:
        indices.add(first)
    return [messages[index] for index in sorted(indices)]


def _last_exchange(exchanges: list[ToolExchange], tool_name: str) -> ToolExchange | None:
    for item in reversed(exchanges):
        if tool_name in item.tool_names:
            return item
    return None


def _add_exchange_indices(target: set[int], exchange: ToolExchange) -> None:
    target.update(range(exchange.start, exchange.end))


def _sanitize_load_context_message(message: Any) -> Any:
    content = _message_content(message)
    if not isinstance(content, str):
        return message
    try:
        payload = json.loads(content)
    except (TypeError, ValueError, json.JSONDecodeError):
        return message
    if not isinstance(payload, dict):
        return message

    requirements = payload.get("requirements")
    if isinstance(requirements, dict):
        payload["requirements"] = {
            "total_count": requirements.get("total_count", 0),
            "current_batch": {
                "omitted_from_history_anchor": True,
                "reason": "Use the current batch context from the latest tool result",
            },
        }
    payload.pop("agent_report", None)
    payload.pop("validation", None)
    sanitized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return _copy_message_with_content(message, sanitized)


def _message_content(message: Any) -> Any:
    if isinstance(message, dict):
        return message.get("content")
    return getattr(message, "content", None)


def _copy_message_with_content(message: Any, content: str) -> Any:
    if isinstance(message, dict):
        result = dict(message)
        result["content"] = content
        return result
    model_copy = getattr(message, "model_copy", None)
    if callable(model_copy):
        return model_copy(update={"content": content})
    copy_method = getattr(message, "copy", None)
    if callable(copy_method):
        try:
            return copy_method(update={"content": content})
        except TypeError:
            pass
    return message
