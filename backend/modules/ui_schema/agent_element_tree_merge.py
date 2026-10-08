from __future__ import annotations

from copy import deepcopy
from typing import Any


def merge_explicit_element_tree(
    *,
    document_elements: list[dict[str, Any]],
    current: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Merge only explicitly supplied descendants while preserving omitted children.

    Existing descendants must stay under the same direct parent. New descendants are appended.
    The function never moves or deletes an existing object.
    """
    global_parent = _parent_map(document_elements)
    incoming_ids = _all_ids([payload])
    if len(incoming_ids) != _count_ids([payload]):
        raise ValueError("Incoming element subtree contains duplicate IDs")
    return _merge_node(
        current=deepcopy(current),
        incoming=payload,
        global_parent=global_parent,
    )


def _merge_node(
    *,
    current: dict[str, Any],
    incoming: dict[str, Any],
    global_parent: dict[str, str],
) -> dict[str, Any]:
    current_id = str(current.get("id") or "")
    incoming_id = str(incoming.get("id") or "")
    if current_id != incoming_id:
        raise ValueError(f"Cannot merge element {incoming_id} into {current_id}")

    result = deepcopy(current)
    incoming_children = incoming.get("children") if "children" in incoming else None
    for key, value in incoming.items():
        if key != "children":
            result[key] = deepcopy(value)

    if incoming_children is None:
        return result
    if not isinstance(incoming_children, list):
        raise ValueError(f"Element {incoming_id}.children must be a list")

    existing_children = result.get("children")
    if existing_children is None:
        existing_children = []
        result["children"] = existing_children
    if not isinstance(existing_children, list):
        raise ValueError(f"Element {incoming_id}.children must be a list")

    by_id = {
        str(item.get("id") or ""): index
        for index, item in enumerate(existing_children)
        if isinstance(item, dict) and str(item.get("id") or "")
    }
    for child in incoming_children:
        if not isinstance(child, dict):
            raise ValueError(f"Element {incoming_id}.children contains a non-object")
        child_id = str(child.get("id") or "").strip()
        if not child_id:
            raise ValueError(f"Element {incoming_id}.children contains an item without id")
        if child_id in by_id:
            index = by_id[child_id]
            existing_children[index] = _merge_node(
                current=existing_children[index],
                incoming=child,
                global_parent=global_parent,
            )
            continue
        existing_parent = global_parent.get(child_id)
        if existing_parent is not None:
            raise ValueError(
                f"Element {child_id} already exists under {existing_parent}; nested upsert "
                f"cannot move it under {incoming_id}. Use move_elements explicitly."
            )
        existing_children.append(deepcopy(child))
        by_id[child_id] = len(existing_children) - 1
    return result


def _parent_map(elements: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}

    def visit(items: Any, parent_id: str) -> None:
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "").strip()
            if not item_id:
                continue
            result[item_id] = parent_id
            visit(item.get("children", []), item_id)

    visit(elements, "<root>")
    return result


def _all_ids(items: Any) -> set[str]:
    result: set[str] = set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        if item_id:
            result.add(item_id)
        result.update(_all_ids(item.get("children", [])))
    return result


def _count_ids(items: Any) -> int:
    count = 0
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "").strip():
            count += 1
        count += _count_ids(item.get("children", []))
    return count
