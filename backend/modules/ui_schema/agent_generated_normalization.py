from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_normalize_documents import normalize_document_conventions
from backend.modules.ui_schema.agent_normalize_elements import normalize_table_columns
from backend.modules.ui_schema.agent_normalize_links import normalize_generated_links
from backend.modules.ui_schema.files import read_json, write_json


def normalize_generated_schema(run_path: Path) -> list[str]:
    """Apply and persist narrow deterministic repairs before validation."""
    working_root = run_path / "working" / "ui_schema"
    base_root = run_path / "base" / "ui_schema"
    result_path = run_path / "result" / "normalization.json"

    document_actions = normalize_document_conventions(working_root=working_root)
    element_actions = normalize_table_columns(
        working_root=working_root,
        base_root=base_root,
    )
    link_actions = normalize_generated_links(
        working_root=working_root,
        descendant_remap={},
    )
    actions = [*document_actions, *element_actions, *link_actions]

    existing = read_json(result_path, {"actions": [], "warnings": []})
    existing_actions = existing.get("actions", []) if isinstance(existing, dict) else []
    merged_actions = _merge_actions(existing_actions, actions)
    warnings = [
        str(item.get("message") or "")
        for item in merged_actions
        if item.get("message") and item.get("severity", "warning") != "info"
    ]
    write_json(result_path, {"actions": merged_actions, "warnings": warnings})
    return warnings


def stored_normalization_warnings(run_path: Path) -> list[str]:
    data = read_json(run_path / "result" / "normalization.json", {})
    warnings = data.get("warnings", []) if isinstance(data, dict) else []
    return [str(item) for item in warnings if str(item).strip()]


def _merge_actions(existing: Any, new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = [item for item in (existing or []) if isinstance(item, dict)]
    signatures = {_action_signature(item) for item in result}
    for item in new:
        signature = _action_signature(item)
        if signature not in signatures:
            result.append(item)
            signatures.add(signature)
    return result


def _action_signature(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item.get("type"),
        item.get("object_id"),
        item.get("link_id"),
        item.get("old_id"),
        item.get("new_id"),
        item.get("count"),
    )
