from __future__ import annotations

from typing import Any

_REQUIRED_LIMITS = (
    "max_llm_calls",
    "max_tool_calls",
    "max_total_tokens",
    "max_duration_seconds",
    "recursion_limit",
    "request_timeout_seconds",
    "max_repeated_tool_calls",
)


def execution_limits(agent_config: dict[str, Any]) -> dict[str, int]:
    config = agent_config.get("execution") if isinstance(agent_config, dict) else None
    if not isinstance(config, dict):
        raise ValueError("agent.execution must be configured")
    result: dict[str, int] = {}
    for name in _REQUIRED_LIMITS:
        try:
            value = int(config[name])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"agent.execution.{name} must be a positive integer") from exc
        if value <= 0:
            raise ValueError(f"agent.execution.{name} must be a positive integer")
        result[name] = value
    return result
