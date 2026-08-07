from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from backend.modules.ui_schema.agent_audit_context_details import build_audit_target_context
from backend.modules.ui_schema.agent_context import (
    build_element_type_context,
    build_ui_schema_context,
)
from backend.modules.ui_schema.agent_requirement_scope import compact_requirements
from backend.modules.ui_schema.agent_target_catalog import build_target_catalog, target_summary
from backend.modules.ui_schema.files import read_json


def requirement_records(
    run_path: Path,
    *,
    agent_config: dict[str, Any],
) -> list[dict[str, Any]]:
    context = agent_config.get("context", {}) if isinstance(agent_config, dict) else {}
    fields = context.get("requirement_fields") if isinstance(context, dict) else None
    return compact_requirements(
        run_path,
        fields=fields if isinstance(fields, list) else None,
    )


def fixed_batches(items: list[Any], size: int) -> list[list[Any]]:
    return [items[offset : offset + size] for offset in range(0, len(items), size)]


def common_context(
    run_path: Path,
    *,
    include_schema: bool,
) -> dict[str, Any]:
    task = read_json(run_path / "input" / "task.json", {})
    result: dict[str, Any] = {
        "task": task,
        "element_types": build_element_type_context(),
    }
    if include_schema:
        result["ui_schema"] = build_ui_schema_context(run_path / "working" / "ui_schema")
    return result


def audit_context(
    *,
    run_path: Path,
    requirements: list[dict[str, Any]],
    decisions: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    working_root = run_path / "working" / "ui_schema"
    working_catalog = build_target_catalog(working_root)
    decision_items = [_compact_audit_decision(dict(item)) for item in decisions]
    targets: dict[str, dict[str, Any]] = {}
    target_keys: set[tuple[str, str]] = set()
    for decision in decision_items:
        for target in decision.get("targets", []) if isinstance(decision, dict) else []:
            if not isinstance(target, dict):
                continue
            target_type = str(target.get("target_type") or "")
            target_id = str(target.get("target_id") or "")
            if not target_type or not target_id:
                continue
            target_keys.add((target_type, target_id))
            key = f"{target_type}:{target_id}"
            summary = target_summary(
                working_catalog,
                target_type=target_type,
                target_id=target_id,
            )
            targets[key] = _compact_audit_summary(summary)

    target_outlines, related_keys = build_audit_target_context(
        working_root,
        target_keys=target_keys,
    )
    return {
        **common_context(run_path, include_schema=False),
        "requirements": requirements,
        "decisions": decision_items,
        "target_summaries": targets,
        "target_outlines": target_outlines,
        "related_ui_links": _related_ui_links(working_root, related_keys),
    }


def _compact_audit_decision(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item[key]
        for key in ("requirement_id", "ui_effect", "classification", "targets")
        if key in item
    }


def _compact_audit_summary(summary: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "target_type",
        "target_id",
        "exists",
        "page_id",
        "parent_id",
        "element_type",
        "label",
        "description",
        "child_count",
        "title",
        "root_element_count",
    )
    result = {
        key: summary[key]
        for key in keys
        if key in summary and summary[key] not in (None, "", [], {})
    }
    if summary.get("link_source") is True:
        result["link_source"] = True
    return result

def _related_ui_links(
    working_root: Path,
    target_keys: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    document = read_json(working_root / "links.json", {"links": []})
    links = document.get("links", []) if isinstance(document, dict) else []
    if not isinstance(links, list) or not target_keys:
        return []
    result: list[dict[str, Any]] = []
    for raw in links:
        if not isinstance(raw, dict):
            continue
        source = (
            str(raw.get("source_type") or ""),
            str(raw.get("source_id") or ""),
        )
        target = (
            str(raw.get("target_type") or ""),
            str(raw.get("target_id") or ""),
        )
        if source in target_keys or target in target_keys:
            result.append(dict(raw))
    return result
