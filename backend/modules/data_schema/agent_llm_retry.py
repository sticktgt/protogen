from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from backend.modules.data_schema.agent_events import append_event

T = TypeVar("T")


@dataclass(frozen=True)
class TransientLlmRetryPolicy:
    max_retries: int
    delay_seconds: float
    status_codes: frozenset[int]


def transient_llm_retry_policy(agent_config: dict[str, Any]) -> TransientLlmRetryPolicy:
    llm = agent_config.get("llm", {}) if isinstance(agent_config, dict) else {}
    retry = llm.get("transient_retry", {}) if isinstance(llm, dict) else {}
    if not isinstance(retry, dict):
        raise ValueError("agent.llm.transient_retry must be an object")

    max_retries = _non_negative_int(retry, "max_retries")
    delay_seconds = _non_negative_float(retry, "delay_seconds")
    raw_status_codes = retry.get("status_codes")
    if not isinstance(raw_status_codes, list) or not raw_status_codes:
        raise ValueError(
            "agent.llm.transient_retry.status_codes must be a non-empty array"
        )
    status_codes: set[int] = set()
    for value in raw_status_codes:
        try:
            code = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "agent.llm.transient_retry.status_codes must contain integers"
            ) from exc
        if code < 100 or code > 599:
            raise ValueError(
                "agent.llm.transient_retry.status_codes must contain HTTP status codes"
            )
        status_codes.add(code)
    return TransientLlmRetryPolicy(
        max_retries=max_retries,
        delay_seconds=delay_seconds,
        status_codes=frozenset(status_codes),
    )


def invoke_with_transient_llm_retry(
    operation: Callable[[], T],
    *,
    agent_config: dict[str, Any],
    module_root: Path | None = None,
    run_id: str = "",
    operation_name: str = "LLM",
) -> T:
    """Retry only explicitly configured transient HTTP failures.

    Provider-internal retries remain disabled. Timeouts and errors without a
    configured HTTP status code are propagated immediately.
    """
    policy = transient_llm_retry_policy(agent_config)
    retry_number = 0
    while True:
        try:
            return operation()
        except Exception as exc:
            status_code = llm_http_status_code(exc)
            if (
                retry_number >= policy.max_retries
                or status_code not in policy.status_codes
            ):
                raise
            retry_number += 1
            if module_root is not None and run_id:
                append_event(
                    module_root,
                    run_id,
                    event_type="llm_transient_retry",
                    level="warning",
                    message=(
                        f"Временная ошибка {operation_name}: HTTP {status_code}. "
                        f"Повтор {retry_number}/{policy.max_retries}"
                    ),
                    data={
                        "operation": operation_name,
                        "status_code": status_code,
                        "retry": retry_number,
                        "max_retries": policy.max_retries,
                        "delay_seconds": policy.delay_seconds,
                    },
                )
            if policy.delay_seconds > 0:
                time.sleep(policy.delay_seconds)


def llm_http_status_code(error: BaseException) -> int | None:
    """Extract an HTTP status code without depending on one provider SDK."""
    visited: set[int] = set()
    current: BaseException | None = error
    for _ in range(4):
        if current is None or id(current) in visited:
            break
        visited.add(id(current))
        direct = _status_value(getattr(current, "status_code", None))
        if direct is not None:
            return direct
        response = getattr(current, "response", None)
        response_code = _status_value(getattr(response, "status_code", None))
        if response_code is not None:
            return response_code
        next_error = getattr(current, "__cause__", None) or getattr(
            current, "__context__", None
        )
        current = next_error if isinstance(next_error, BaseException) else None
    return None


def _status_value(value: Any) -> int | None:
    try:
        code = int(value)
    except (TypeError, ValueError):
        return None
    return code if 100 <= code <= 599 else None


def _non_negative_int(config: dict[str, Any], key: str) -> int:
    if key not in config:
        raise ValueError(f"agent.llm.transient_retry.{key} must be configured")
    try:
        value = int(config[key])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"agent.llm.transient_retry.{key} must be a non-negative integer"
        ) from exc
    if value < 0:
        raise ValueError(
            f"agent.llm.transient_retry.{key} must be a non-negative integer"
        )
    return value


def _non_negative_float(config: dict[str, Any], key: str) -> float:
    if key not in config:
        raise ValueError(f"agent.llm.transient_retry.{key} must be configured")
    try:
        value = float(config[key])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"agent.llm.transient_retry.{key} must be a non-negative number"
        ) from exc
    if value < 0:
        raise ValueError(
            f"agent.llm.transient_retry.{key} must be a non-negative number"
        )
    return value
