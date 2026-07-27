from __future__ import annotations

from typing import Any


def execution_limits(agent_config: dict[str, Any]) -> dict[str, int]:
    config = agent_config.get("execution", {}) if isinstance(agent_config, dict) else {}
    config = config if isinstance(config, dict) else {}
    return {
        "max_llm_calls": _positive_int(config.get("max_llm_calls"), 20),
        "max_tool_calls": _positive_int(config.get("max_tool_calls"), 120),
        "max_total_tokens": _positive_int(config.get("max_total_tokens"), 500_000),
        "max_duration_seconds": _positive_int(config.get("max_duration_seconds"), 1200),
        "recursion_limit": _positive_int(config.get("recursion_limit"), 100),
        "request_timeout_seconds": _positive_int(config.get("request_timeout_seconds"), 300),
        "max_repeated_tool_calls": _positive_int(config.get("max_repeated_tool_calls"), 3),
    }


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
