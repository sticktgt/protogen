from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_context import build_element_type_context
from backend.modules.ui_schema.agent_target_catalog import (
    build_target_catalog,
    build_technical_index,
)
from backend.modules.ui_schema.files import read_json


def build_planning_repair_context(
    *,
    run_path: Path,
    requirement_batch: list[dict[str, Any]],
    batch_analysis: list[dict[str, Any]],
    rejected_plan: dict[str, Any],
    technical_issues: list[dict[str, Any]],
    batch_index: int,
    batch_total: int,
) -> dict[str, Any]:
    """Build a local context sufficient to repair one rejected planning bundle."""
    schema_root = run_path / "working" / "ui_schema"
    references = _collect_references(rejected_plan, technical_issues)
    affected_pages = _affected_pages(schema_root, rejected_plan, references)
    return {
        "task": read_json(run_path / "input" / "task.json", {}),
        "element_types": build_element_type_context(),
        "batch": {
            "index": batch_index,
            "total": batch_total,
            "requirements": requirement_batch,
            "analysis": batch_analysis,
        },
        "rejected_plan": rejected_plan,
        "technical_issues": technical_issues,
        "technical_errors": [
            str(item.get("message") or item.get("code") or "")
            for item in technical_issues
        ],
        "technical_index": build_technical_index(
            schema_root,
            page_ids=affected_pages,
            target_ids=references,
        ),
        "ui_schema": _local_schema_context(
            schema_root,
            page_ids=affected_pages,
            referenced_ids=references,
            requirement_ids={str(item.get("id") or "") for item in requirement_batch},
        ),
    }


def _collect_references(
    rejected_plan: dict[str, Any],
    technical_issues: list[dict[str, Any]],
) -> set[str]:
    result: set[str] = set()

    def walk(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, str(child_key))
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        elif isinstance(value, str):
            if key.endswith("_id") or key in {
                "id",
                "target_id",
                "source_id",
                "parent_id",
                "new_parent_id",
                "element_id",
                "page_id",
            }:
                text = value.strip()
                if text:
                    result.add(text)

    walk(rejected_plan)
    walk(technical_issues)
    return result


def _affected_pages(
    schema_root: Path,
    rejected_plan: dict[str, Any],
    references: set[str],
) -> set[str]:
    result: set[str] = set()
    changes = rejected_plan.get("changes", {}) if isinstance(rejected_plan, dict) else {}
    for field in ("create_pages", "update_pages", "upsert_elements", "move_elements"):
        for item in changes.get(field, []) if isinstance(changes, dict) else []:
            if not isinstance(item, dict):
                continue
            page_id = str(item.get("page_id") or item.get("id") or "").strip()
            if page_id:
                result.add(page_id)
    catalog = build_target_catalog(schema_root)
    for target_id in references:
        page_record = catalog.get(("page", target_id))
        if page_record is not None:
            result.add(target_id)
        element_record = catalog.get(("ui_element", target_id))
        if element_record is not None:
            page_id = str(element_record.get("page_id") or "")
            if page_id:
                result.add(page_id)
    return result


def _local_schema_context(
    schema_root: Path,
    *,
    page_ids: set[str],
    referenced_ids: set[str],
    requirement_ids: set[str],
) -> dict[str, Any]:
    pages: dict[str, Any] = {}
    for page_id in sorted(item for item in page_ids if item and item != "app"):
        path = schema_root / "pages" / f"{page_id}.json"
        if path.is_file():
            pages[path.name] = read_json(path, {})

    schema = read_json(schema_root / "schema.json", {})
    page_entries = schema.get("pages", []) if isinstance(schema, dict) else []
    if not isinstance(page_entries, list):
        page_entries = []
    filtered_schema = dict(schema) if isinstance(schema, dict) else {}
    filtered_schema["pages"] = [
        item
        for item in page_entries
        if isinstance(item, dict) and str(item.get("id") or "") in page_ids
    ]

    catalog = build_target_catalog(schema_root)

    def target_page(target_type: str, target_id: str) -> str:
        if target_type == "page":
            return target_id
        item = catalog.get(("ui_element", target_id))
        return str((item or {}).get("page_id") or "")

    links = read_json(schema_root / "links.json", {"links": []})
    link_items = links.get("links", []) if isinstance(links, dict) else []
    if not isinstance(link_items, list):
        link_items = []
    relevant_links = []
    for item in link_items:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id") or "")
        target_id = str(item.get("target_id") or "")
        source_page = target_page(str(item.get("source_type") or ""), source_id)
        target_page_id = target_page(str(item.get("target_type") or ""), target_id)
        if (
            source_id in referenced_ids
            or target_id in referenced_ids
            or source_page in page_ids
            or target_page_id in page_ids
        ):
            relevant_links.append(item)

    requirement_links = read_json(
        schema_root / "mappings" / "requirement_ui_links.json",
        {"links": []},
    )
    requirement_link_items = (
        requirement_links.get("links", [])
        if isinstance(requirement_links, dict)
        else []
    )
    if not isinstance(requirement_link_items, list):
        requirement_link_items = []
    relevant_requirement_links = [
        item
        for item in requirement_link_items
        if isinstance(item, dict)
        and str(item.get("requirement_id") or "") in requirement_ids
    ]

    return {
        "app": read_json(schema_root / "app.json", {}) if "app" in page_ids else {},
        "schema": filtered_schema,
        "links": {"links": relevant_links},
        "requirement_ui_links": {"links": relevant_requirement_links},
        "pages": pages,
    }

