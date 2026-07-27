from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_paths import completed_run_file, run_root
from backend.modules.ui_schema.files import read_json, write_json

_LOGGER = logging.getLogger(__name__)
_EVENTS_LOCK = threading.RLock()


def initialize_observability(
    module_root: Path,
    run_id: str,
    *,
    limits: dict[str, int],
    started_at: str,
) -> dict[str, Any]:
    root = run_root(module_root, run_id)
    metrics = {
        "llm_calls": 0,
        "tool_calls": 0,
        "last_tool": "",
        "repeat_streak": 0,
        "max_repeat_streak": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "token_usage_available": False,
        "last_seq": 0,
        "last_event_at": None,
        "last_llm_started_at": None,
        "last_llm_completed_at": None,
        "limits": dict(limits),
        "started_at": started_at,
    }
    write_json(root / "metrics.json", metrics)
    (root / "events.jsonl").write_text("", encoding="utf-8")
    return metrics


def append_event(
    module_root: Path,
    run_id: str,
    *,
    event_type: str,
    message: str,
    level: str = "info",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = run_root(module_root, run_id)
    with _EVENTS_LOCK:
        metrics = read_metrics(module_root, run_id)
        seq = int(metrics.get("last_seq", 0)) + 1
        timestamp = _now_iso()
        event = {
            "seq": seq,
            "timestamp": timestamp,
            "level": level,
            "type": event_type,
            "message": str(message),
            "data": _json_safe_dict(data or {}),
        }
        path = root / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        metrics["last_seq"] = seq
        metrics["last_event_at"] = timestamp
        write_json(root / "metrics.json", metrics)
    getattr(_LOGGER, level if level in {"debug", "info", "warning", "error"} else "info")(
        "[ui_schema_agent][%s] %s", run_id, message
    )
    return event


def read_events(
    module_root: Path,
    run_id: str,
    *,
    after: int = 0,
    limit: int = 200,
) -> dict[str, Any]:
    root = run_root(module_root, run_id)
    path = root / "events.jsonl"
    result: list[dict[str, Any]] = []
    if not path.is_file():
        completed = read_json(completed_run_file(module_root, run_id), {})
        stored_events = completed.get("recent_events", []) if isinstance(completed, dict) else []
        safe_limit = max(1, min(int(limit), 500))
        result = [
            event for event in stored_events
            if isinstance(event, dict) and int(event.get("seq", 0)) > int(after)
        ][:safe_limit]
        metrics = completed.get("metrics", {}) if isinstance(completed, dict) else {}
        next_after = int(result[-1].get("seq", after)) if result else int(after)
        return {"events": result, "metrics": metrics, "next_after": next_after}
    safe_limit = max(1, min(int(limit), 500))
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if int(event.get("seq", 0)) <= int(after):
                continue
            result.append(event)
            if len(result) >= safe_limit:
                break
    metrics = read_metrics(module_root, run_id)
    next_after = int(result[-1]["seq"]) if result else int(after)
    return {"events": result, "metrics": metrics, "next_after": next_after}


def read_metrics(module_root: Path, run_id: str) -> dict[str, Any]:
    path = run_root(module_root, run_id) / "metrics.json"
    value = read_json(path, {})
    if isinstance(value, dict) and value:
        return value
    completed = read_json(completed_run_file(module_root, run_id), {})
    metrics = completed.get("metrics", {}) if isinstance(completed, dict) else {}
    return metrics if isinstance(metrics, dict) else {}


def increment_metric(
    module_root: Path,
    run_id: str,
    key: str,
    amount: int = 1,
    **updates: Any,
) -> dict[str, Any]:
    with _EVENTS_LOCK:
        metrics = read_metrics(module_root, run_id)
        metrics[key] = int(metrics.get(key, 0)) + int(amount)
        metrics.update(updates)
        write_json(run_root(module_root, run_id) / "metrics.json", metrics)
        return metrics


def add_token_usage(
    module_root: Path,
    run_id: str,
    *,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
) -> dict[str, Any]:
    with _EVENTS_LOCK:
        metrics = read_metrics(module_root, run_id)
        metrics["input_tokens"] = int(metrics.get("input_tokens", 0)) + max(0, int(input_tokens))
        metrics["output_tokens"] = int(metrics.get("output_tokens", 0)) + max(0, int(output_tokens))
        metrics["total_tokens"] = int(metrics.get("total_tokens", 0)) + max(0, int(total_tokens))
        metrics["token_usage_available"] = True
        metrics["last_llm_completed_at"] = _now_iso()
        write_json(run_root(module_root, run_id) / "metrics.json", metrics)
        return metrics


def update_metrics(module_root: Path, run_id: str, **updates: Any) -> dict[str, Any]:
    with _EVENTS_LOCK:
        metrics = read_metrics(module_root, run_id)
        metrics.update(updates)
        write_json(run_root(module_root, run_id) / "metrics.json", metrics)
        return metrics


def elapsed_seconds(started_at: str | None) -> int:
    if not started_at:
        return 0
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - started).total_seconds()))


def _json_safe_dict(value: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return {"value": str(value)}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
