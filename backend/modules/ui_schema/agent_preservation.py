from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from backend.modules.ui_schema.files import read_json, write_json


def preservation_validation(
    base_root: Path,
    working_root: Path,
    validation: dict[str, Any],
    *,
    approved_page_ids: set[str] | None = None,
    approved_element_ids: set[str] | None = None,
) -> dict[str, Any]:
    errors = list(validation.get("errors", []))
    missing_pages, missing_elements = find_missing_base_objects(base_root, working_root)
    missing_pages = sorted(set(missing_pages) - set(approved_page_ids or set()))
    missing_elements = sorted(set(missing_elements) - set(approved_element_ids or set()))
    if missing_pages:
        errors.append(
            "Синхронизация не может удалять существующие страницы: "
            + ", ".join(missing_pages[:20])
            + (f"; ещё {len(missing_pages) - 20}" if len(missing_pages) > 20 else "")
        )
    if missing_elements:
        errors.append(
            "Синхронизация не может удалять существующие UI-элементы: "
            + ", ".join(missing_elements[:20])
            + (f"; ещё {len(missing_elements) - 20}" if len(missing_elements) > 20 else "")
        )
    result = dict(validation)
    result["errors"] = errors
    result["valid"] = not errors
    return result


def find_missing_base_objects(
    base_root: Path,
    working_root: Path,
) -> tuple[list[str], list[str]]:
    base_pages, base_elements = collect_schema_ids(base_root)
    working_pages, working_elements = collect_schema_ids(working_root)
    return (
        sorted(base_pages - working_pages),
        sorted(base_elements - working_elements),
    )


def collect_schema_ids(root: Path) -> tuple[set[str], set[str]]:
    page_ids: set[str] = set()
    element_ids: set[str] = set()
    app = read_json(root / "app.json", {})
    _collect_tree_ids(app.get("root_elements", []), element_ids)
    pages_root = root / "pages"
    if pages_root.exists():
        for page_path in sorted(pages_root.glob("*.json")):
            page = read_json(page_path, {})
            page_id = page.get("id")
            if isinstance(page_id, str) and page_id:
                page_ids.add(page_id)
            _collect_tree_ids(page.get("elements", []), element_ids)
    return page_ids, element_ids


def delete_new_elements(
    *,
    base_root: Path,
    working_root: Path,
    element_ids: Iterable[str],
    reason: str,
) -> dict[str, Any]:
    normalized = _normalize_element_ids(element_ids)
    if not reason.strip():
        raise ValueError("reason must explain why newly generated elements are removed")
    _, protected_ids = collect_schema_ids(base_root)
    protected = sorted(set(normalized) & protected_ids)
    if protected:
        raise ValueError(
            "Existing base elements cannot be deleted by synchronization: "
            + ", ".join(protected)
        )

    deleted: list[str] = []
    app_path = working_root / "app.json"
    app = read_json(app_path, {})
    app["root_elements"], removed = _remove_tree_ids(
        app.get("root_elements", []), set(normalized)
    )
    if removed:
        write_json(app_path, app)
        deleted.extend(removed)

    pages_root = working_root / "pages"
    for page_path in sorted(pages_root.glob("*.json")):
        page = read_json(page_path, {})
        page["elements"], removed = _remove_tree_ids(
            page.get("elements", []), set(normalized)
        )
        if removed:
            write_json(page_path, page)
            deleted.extend(removed)

    missing = sorted(set(normalized) - set(deleted))
    return {
        "ok": True,
        "message": f"Deleted {len(deleted)} elements created during this run",
        "deleted_element_ids": sorted(deleted),
        "not_found": missing,
        "reason": reason.strip(),
    }


def normalize_element_ids(value: Any) -> list[str]:
    candidate = value
    if isinstance(candidate, str):
        text = candidate.strip()
        if text.startswith("["):
            try:
                candidate = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"element_ids must be a JSON list: {exc.msg}") from exc
        else:
            candidate = [text]
    return _normalize_element_ids(candidate)


def _normalize_element_ids(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("element_ids must be a non-empty list")
    if len(value) > 50:
        raise ValueError("At most 50 newly generated elements can be deleted at once")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"element_ids[{index}] must be a non-empty string")
        normalized = item.strip()
        if normalized not in result:
            result.append(normalized)
    return result


def _collect_tree_ids(items: Any, target: set[str]) -> None:
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id:
            target.add(item_id)
        _collect_tree_ids(item.get("children", []), target)


def _remove_tree_ids(
    items: Any,
    targets: set[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    result: list[dict[str, Any]] = []
    deleted: list[str] = []
    for raw_item in items or []:
        if not isinstance(raw_item, dict):
            continue
        item = deepcopy(raw_item)
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id in targets:
            deleted.extend(_descendant_ids(item))
            continue
        children, child_deleted = _remove_tree_ids(item.get("children", []), targets)
        if "children" in item:
            item["children"] = children
        deleted.extend(child_deleted)
        result.append(item)
    return result, deleted


def _descendant_ids(item: dict[str, Any]) -> list[str]:
    result: list[str] = []
    item_id = item.get("id")
    if isinstance(item_id, str):
        result.append(item_id)
    for child in item.get("children", []) or []:
        if isinstance(child, dict):
            result.extend(_descendant_ids(child))
    return result
