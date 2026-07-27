from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.files import read_json, write_json


def normalize_table_columns(
    *,
    working_root: Path,
    base_root: Path,
) -> list[dict[str, Any]]:
    """Normalize generated table children to explicit table_column elements.

    The operation never removes table children. It only converts generated leaf
    elements directly inside ``table`` from the legacy ``text`` representation
    to ``table_column``. Existing base elements are left untouched so an
    incompatible historic structure remains visible to validation.
    """
    base_element_ids = _collect_element_ids_from_root(base_root)
    actions: list[dict[str, Any]] = []
    document_paths = [
        working_root / "app.json",
        *sorted((working_root / "pages").glob("*.json")),
    ]
    for path in document_paths:
        data = read_json(path, {})
        collection_key = "root_elements" if path.name == "app.json" else "elements"
        items = data.get(collection_key, []) if isinstance(data, dict) else []
        changed = _normalize_table_tree(
            items,
            base_element_ids=base_element_ids,
            actions=actions,
        )
        if changed:
            write_json(path, data)
    return actions


def _normalize_table_tree(
    items: Any,
    *,
    base_element_ids: set[str],
    actions: list[dict[str, Any]],
) -> bool:
    changed = False
    for item in items or []:
        if not isinstance(item, dict):
            continue
        children = item.get("children")
        if item.get("type") == "table" and isinstance(children, list):
            converted: list[str] = []
            for child in children:
                if not isinstance(child, dict):
                    continue
                child_id = child.get("id")
                if child_id in base_element_ids:
                    continue
                if child.get("type") != "text":
                    continue
                nested = child.get("children")
                if nested not in (None, []):
                    continue
                child["type"] = "table_column"
                if isinstance(child_id, str) and child_id:
                    converted.append(child_id)
            if converted:
                actions.append(
                    {
                        "type": "table_columns_typed",
                        "severity": "info",
                        "object_id": item.get("id"),
                        "affected_ids": sorted(converted),
                        "message": (
                            f"Backend уточнил тип {len(converted)} колонок таблицы "
                            f"{item.get('id')}: text → table_column."
                        ),
                    }
                )
                changed = True
            # Invalid non-column or nested children are intentionally preserved;
            # the validator must report them instead of silently deleting data.
            continue
        if isinstance(children, list):
            changed = _normalize_table_tree(
                children,
                base_element_ids=base_element_ids,
                actions=actions,
            ) or changed
    return changed


def _collect_element_ids_from_root(root: Path) -> set[str]:
    element_ids: set[str] = set()
    app = read_json(root / "app.json", {})
    _collect_tree_ids(app.get("root_elements", []) if isinstance(app, dict) else [], element_ids)
    for path in (root / "pages").glob("*.json"):
        page = read_json(path, {})
        _collect_tree_ids(page.get("elements", []) if isinstance(page, dict) else [], element_ids)
    return element_ids


def _collect_tree_ids(items: Any, target: set[str]) -> None:
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id:
            target.add(item_id)
        _collect_tree_ids(item.get("children", []), target)
