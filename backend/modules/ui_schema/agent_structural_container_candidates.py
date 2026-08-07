from __future__ import annotations

from typing import Any

from backend.modules.ui_schema.element_types import type_definition


def collect_emptied_existing_candidates(
    *,
    base_elements: dict[str, dict[str, Any]],
    elements: dict[str, dict[str, Any]],
    decisions_by_target: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Find base containers that became empty during the current run."""
    result: list[dict[str, Any]] = []
    for element_id, base_item in sorted(base_elements.items()):
        current = elements.get(element_id)
        if current is None:
            continue
        definition = type_definition(current["type"]) or {}
        if definition.get("review_empty") is not True:
            continue
        if base_item.get("child_count", 0) <= 0 or current.get("child_count", 0) != 0:
            continue
        original_child_ids = [
            child_id
            for child_id in base_item.get("child_ids", [])
            if child_id in elements
        ]
        moved_out_child_ids = [
            child_id
            for child_id in original_child_ids
            if elements[child_id].get("parent_id") != element_id
        ]
        affected_ids = sorted(
            {element_id}
            | {
                affected_id
                for child_id in original_child_ids
                for affected_id in elements[child_id].get("subtree_ids", [child_id])
            }
        )
        result.append(
            {
                "candidate_id": f"emptied:{element_id}",
                "kind": "emptied_existing_container",
                "page_id": current["page_id"],
                "parent_id": current["parent_id"],
                "element_ids": [element_id, *original_child_ids],
                "new_element_ids": [],
                "existing_element_ids": [element_id, *original_child_ids],
                "affected_element_ids": affected_ids,
                "link_ids": [],
                "related_requirement_ids": _related_ids(
                    affected_ids,
                    decisions_by_target,
                ),
                "facts": {
                    "element_type": current["type"],
                    "label": current["label"],
                    "base_child_count": base_item.get("child_count", 0),
                    "current_child_count": 0,
                    "original_child_ids": original_child_ids,
                    "moved_out_child_ids": moved_out_child_ids,
                },
            }
        )
    return result


def _related_ids(
    target_ids: list[str],
    decisions_by_target: dict[str, list[str]],
) -> list[str]:
    return sorted(
        {
            requirement_id
            for target_id in target_ids
            for requirement_id in decisions_by_target.get(target_id, [])
        }
    )
