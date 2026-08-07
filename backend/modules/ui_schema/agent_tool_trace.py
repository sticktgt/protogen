from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_diagnostic_settings import run_diagnostic_settings
from backend.modules.ui_schema.agent_validation_history import validation_error_codes

_LOGGER = logging.getLogger(__name__)
_TRACE_LOCK = threading.RLock()


def tool_argument_summary(name: str, args: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {"tool": str(name)}
    for key in ("page_id", "parent_id", "file_path", "path", "target_id", "batch_id", "review_batch_id"):
        value = args.get(key)
        if isinstance(value, str) and value:
            summary[key] = value[:300]

    elements = args.get("elements")
    if isinstance(elements, list):
        summary["top_level_elements"] = len(elements)
    links = args.get("links")
    if isinstance(links, list):
        summary["links"] = len(links)
    elif isinstance(links, dict) and isinstance(links.get("links"), list):
        summary["links"] = len(links["links"])

    for key in (
        "removals", "element_ids", "changes", "moves", "items",
        "create_pages", "upsert_elements", "move_elements", "ui_links",
    ):
        value = args.get(key)
        if isinstance(value, list):
            summary[key] = len(value)
    batch_items = (
        args.get("changes")
        or args.get("moves")
        or args.get("upsert_elements")
        or args.get("move_elements")
    )
    page_ids: set[str] = set()
    created_pages = args.get("create_pages")
    if isinstance(created_pages, list):
        for item in created_pages:
            if isinstance(item, dict) and isinstance(item.get("page_id"), str):
                page_ids.add(item["page_id"])
    if isinstance(batch_items, list):
        element_ids: list[str] = []
        for item in batch_items:
            if not isinstance(item, dict):
                continue
            page_id = item.get("page_id")
            if isinstance(page_id, str) and page_id:
                page_ids.add(page_id)
            element_id = item.get("element_id")
            element = item.get("element")
            if not element_id and isinstance(element, dict):
                element_id = element.get("id")
            if isinstance(element_id, str) and element_id and element_id not in element_ids:
                element_ids.append(element_id)
        if element_ids:
            summary["element_ids"] = element_ids[:40]
    if page_ids:
        summary["page_ids"] = sorted(page_ids)[:20]
    supplied = [key for key in ("app", "schema_document") if args.get(key) is not None]
    if supplied:
        summary["documents"] = supplied
    item_values = args.get("items")
    if isinstance(item_values, list):
        summary["items"] = len(item_values)
        if name in {"write_ui_schema_coverage_plan_batch", "review_ui_schema_coverage_plan", "revise_ui_schema_coverage_plan"}:
            summary["planned_requirements"] = len(item_values)
    return summary


def tool_output_summary(output: Any) -> dict[str, Any]:
    payload = _json_payload(output)
    if not isinstance(payload, dict):
        return {}
    result: dict[str, Any] = {}
    for key in (
        "ok",
        "valid",
        "completed",
        "file_count",
        "path",
        "paths",
        "chunk_index",
        "requirements_touched",
        "change_count",
        "move_count",
        "page_count",
        "planned_requirements",
        "created_page_count",
        "element_change_count",
        "ui_link_count",
        "coverage_plan_changes",
        "batch_id",
        "review_batch_id",
        "batch_requirements",
        "batches_complete",
        "next_batch_id",
        "reviewed_candidates",
        "changed_requirements",
        "revised_count",
        "gap_count",
        "complete",
        "traceability_recheck_requirement_ids",
        "next_action",
        "review_complete",
        "no_changes",
    ):
        if key in payload:
            result[key] = payload[key]
    errors = payload.get("errors", [])
    if isinstance(errors, list):
        result["error_count"] = len(errors)
        result["error_codes"] = validation_error_codes([str(item) for item in errors])
    warnings = payload.get("warnings", [])
    if isinstance(warnings, list):
        result["warning_count"] = len(warnings)
    if payload.get("error"):
        result["error"] = str(payload.get("error"))[:600]
    return result


def append_tool_trace(run_path: Path, record: dict[str, Any]) -> None:
    try:
        _append_tool_trace(run_path, record)
    except (OSError, TypeError, ValueError):
        _LOGGER.exception("Failed to record UI Schema tool trace")


def _append_tool_trace(run_path: Path, record: dict[str, Any]) -> None:
    settings = run_diagnostic_settings(run_path).get("tool_trace", {})
    if not settings.get("enabled", True):
        return
    path = run_path / "result" / "tool_trace.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_record = _json_safe(record)
    safe_record.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    _truncate_error_fields(safe_record, int(settings.get("max_error_length", 600)))
    maximum = int(settings.get("max_entries", 256))
    with _TRACE_LOCK:
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        lines.append(json.dumps(safe_record, ensure_ascii=False, separators=(",", ":")))
        if len(lines) > maximum:
            lines = [lines[0], *lines[-(maximum - 1):]] if maximum > 1 else [lines[-1]]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _json_payload(output: Any) -> Any:
    value = getattr(output, "content", output)
    if isinstance(value, list):
        value = "".join(
            str(item.get("text") or "")
            for item in value
            if isinstance(item, dict)
        )
    if isinstance(value, dict):
        return value
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError):
        return None


def _json_safe(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _truncate_error_fields(value: Any, maximum: int) -> None:
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if key == "error" and isinstance(item, str):
                value[key] = item[:maximum]
            else:
                _truncate_error_fields(item, maximum)
    elif isinstance(value, list):
        for item in value:
            _truncate_error_fields(item, maximum)
