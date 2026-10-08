from __future__ import annotations

from copy import deepcopy
from typing import Any


def merge_preserving_agent_content(
    file_path: str,
    current: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    """Merge generated schema data without treating omissions as deletions."""
    if file_path == "app.json":
        return _merge_document(current, incoming, collection_key="root_elements")
    if file_path.startswith("pages/"):
        return _merge_document(current, incoming, collection_key="elements")
    if file_path == "schema.json":
        return _merge_schema(current, incoming)
    return deepcopy(incoming)


def _merge_document(
    current: dict[str, Any],
    incoming: dict[str, Any],
    *,
    collection_key: str,
) -> dict[str, Any]:
    merged = deepcopy(current)
    for key, value in incoming.items():
        if key != collection_key:
            merged[key] = deepcopy(value)
    current_items = current.get(collection_key, [])
    incoming_items = incoming.get(collection_key)
    if incoming_items is None:
        merged[collection_key] = deepcopy(current_items)
    else:
        merged[collection_key] = _merge_tree(current_items, incoming_items)
    return merged


def _merge_schema(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(current)
    for key, value in incoming.items():
        if key == "pages":
            continue
        if key == "application" and isinstance(value, dict):
            base_application = current.get("application", {})
            merged[key] = {
                **(deepcopy(base_application) if isinstance(base_application, dict) else {}),
                **deepcopy(value),
            }
        else:
            merged[key] = deepcopy(value)
    if "pages" in incoming:
        merged["pages"] = _merge_id_list(current.get("pages", []), incoming.get("pages", []))
    return merged


def _merge_id_list(current: Any, incoming: Any) -> list[dict[str, Any]]:
    current_items = [item for item in (current or []) if isinstance(item, dict)]
    incoming_items = [item for item in (incoming or []) if isinstance(item, dict)]
    current_by_id = {
        item.get("id"): item for item in current_items if isinstance(item.get("id"), str)
    }
    incoming_ids: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in incoming_items:
        item_id = item.get("id")
        existing = current_by_id.get(item_id, {}) if isinstance(item_id, str) else {}
        result.append({**deepcopy(existing), **deepcopy(item)})
        if isinstance(item_id, str):
            incoming_ids.add(item_id)
    for item in current_items:
        item_id = item.get("id")
        if not isinstance(item_id, str) or item_id not in incoming_ids:
            result.append(deepcopy(item))
    return result


def _merge_tree(
    current: Any,
    incoming: Any,
    *,
    current_index: dict[str, dict[str, Any]] | None = None,
    incoming_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    current_items = [item for item in (current or []) if isinstance(item, dict)]
    incoming_items = [item for item in (incoming or []) if isinstance(item, dict)]
    if current_index is None:
        current_index = {}
        _index_tree(current_items, current_index)
    if incoming_ids is None:
        incoming_ids = set()
        _collect_tree_ids(incoming_items, incoming_ids)

    result = [
        _merge_tree_item(item, current_index=current_index, incoming_ids=incoming_ids)
        for item in incoming_items
    ]
    for item in current_items:
        preserved = _preserve_omitted_tree(item, incoming_ids)
        if preserved is not None:
            result.append(preserved)
    return result


def _merge_tree_item(
    incoming: dict[str, Any],
    *,
    current_index: dict[str, dict[str, Any]],
    incoming_ids: set[str],
) -> dict[str, Any]:
    item_id = incoming.get("id")
    current = current_index.get(item_id, {}) if isinstance(item_id, str) else {}
    merged = deepcopy(current)
    for key, value in incoming.items():
        if key != "children":
            merged[key] = deepcopy(value)
    incoming_children = incoming.get("children")
    current_children = current.get("children", []) if isinstance(current, dict) else []
    if incoming_children is None:
        merged["children"] = [
            child
            for item in current_children
            if (child := _preserve_omitted_tree(item, incoming_ids)) is not None
        ]
    else:
        merged["children"] = _merge_tree(
            current_children,
            incoming_children,
            current_index=current_index,
            incoming_ids=incoming_ids,
        )
    if not merged.get("children") and "children" not in incoming and "children" not in current:
        merged.pop("children", None)
    return merged


def _preserve_omitted_tree(
    item: dict[str, Any],
    incoming_ids: set[str],
) -> dict[str, Any] | None:
    item_id = item.get("id")
    if isinstance(item_id, str) and item_id in incoming_ids:
        return None
    preserved = deepcopy(item)
    if "children" in preserved:
        preserved["children"] = [
            child
            for child_item in item.get("children", [])
            if (child := _preserve_omitted_tree(child_item, incoming_ids)) is not None
        ]
    return preserved


def _index_tree(items: Any, target: dict[str, dict[str, Any]]) -> None:
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if isinstance(item_id, str):
            target[item_id] = item
        _index_tree(item.get("children", []), target)


def _collect_tree_ids(items: Any, target: set[str]) -> None:
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id:
            target.add(item_id)
        _collect_tree_ids(item.get("children", []), target)
