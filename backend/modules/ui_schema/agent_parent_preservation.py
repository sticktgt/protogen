from __future__ import annotations

from typing import Any


def reject_implicit_parent_changes(
    *,
    page_id: str,
    current_elements: Any,
    incoming_elements: Any,
) -> None:
    """Reject whole-page payloads that relocate an existing ID implicitly."""
    current = _parent_map(current_elements, root_parent=page_id)
    incoming = _parent_map(incoming_elements, root_parent=page_id)
    moved = [
        (element_id, current[element_id], incoming[element_id])
        for element_id in sorted(current.keys() & incoming.keys())
        if current[element_id] != incoming[element_id]
    ]
    if not moved:
        return
    preview = ", ".join(
        f"{element_id}: {before} -> {after}"
        for element_id, before, after in moved[:8]
    )
    raise ValueError(
        "Page payload would move existing elements implicitly: "
        + preview
        + ". Existing IDs keep their current parent in page writes. Use "
        "move_elements in apply_ui_schema_changes for an explicit parent change, or use "
        "upsert_elements for targeted updates."
    )


def _parent_map(items: Any, *, root_parent: str) -> dict[str, str]:
    result: dict[str, str] = {}

    def walk(nodes: Any, parent_id: str) -> None:
        for item in nodes or []:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            if isinstance(item_id, str) and item_id:
                if item_id in result:
                    raise ValueError(f"Duplicate UI element ID in page payload: {item_id}")
                result[item_id] = parent_id
                walk(item.get("children", []), item_id)

    walk(items, root_parent)
    return result
