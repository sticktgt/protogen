from __future__ import annotations

import re
from typing import Any

from backend.modules.ui_schema.agent_structural_container_candidates import (
    collect_emptied_existing_candidates,
)
from backend.modules.ui_schema.element_types import type_definition


def collect_element_candidates(
    *,
    base_elements: dict[str, dict[str, Any]],
    elements: dict[str, dict[str, Any]],
    new_ids: set[str],
    decisions_by_target: dict[str, list[str]],
    extended_targets: dict[str, set[str]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    candidates.extend(
        _empty_candidates(
            elements=elements,
            new_ids=new_ids,
            decisions_by_target=decisions_by_target,
            extended_targets=extended_targets,
        )
    )
    candidates.extend(
        collect_emptied_existing_candidates(
            base_elements=base_elements,
            elements=elements,
            decisions_by_target=decisions_by_target,
        )
    )
    candidates.extend(
        _placement_candidates(
            elements=elements,
            new_ids=new_ids,
            decisions_by_target=decisions_by_target,
        )
    )
    candidates.extend(
        _duplicate_candidates(
            elements=elements,
            new_ids=new_ids,
            decisions_by_target=decisions_by_target,
        )
    )
    return candidates


def _empty_candidates(
    *,
    elements: dict[str, dict[str, Any]],
    new_ids: set[str],
    decisions_by_target: dict[str, list[str]],
    extended_targets: dict[str, set[str]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for element_id in sorted(new_ids):
        item = elements[element_id]
        definition = type_definition(item["type"]) or {}
        if definition.get("review_empty") is True and item["child_count"] == 0:
            result.append(
                _candidate(
                    candidate_id=f"empty:{element_id}",
                    kind="empty_new_container",
                    item=item,
                    element_ids=[element_id],
                    new_element_ids=[element_id],
                    existing_element_ids=[],
                    affected_element_ids=item["subtree_ids"],
                    facts={
                        "element_type": item["type"],
                        "label": item["label"],
                        "child_count": 0,
                    },
                    decisions_by_target=decisions_by_target,
                )
            )

    for element_id, requirement_ids in sorted(extended_targets.items()):
        if element_id in new_ids or element_id not in elements:
            continue
        item = elements[element_id]
        definition = type_definition(item["type"]) or {}
        if definition.get("review_empty") is not True or item["child_count"] != 0:
            continue
        result.append(
            _candidate(
                candidate_id=f"empty_extended:{element_id}",
                kind="empty_extended_container",
                item=item,
                element_ids=[element_id],
                new_element_ids=[],
                existing_element_ids=[element_id],
                affected_element_ids=item["subtree_ids"],
                facts={
                    "element_type": item["type"],
                    "label": item["label"],
                    "child_count": 0,
                    "extended_by_requirement_ids": sorted(requirement_ids),
                },
                decisions_by_target=decisions_by_target,
            )
        )
    return result


def _placement_candidates(
    *,
    elements: dict[str, dict[str, Any]],
    new_ids: set[str],
    decisions_by_target: dict[str, list[str]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for element_id in sorted(new_ids):
        item = elements[element_id]
        expected_ancestor = _longest_group_prefix(
            element_id,
            page_id=item["page_id"],
            elements=elements,
        )
        if not expected_ancestor or _is_inside(
            item["parent_id"],
            ancestor_id=expected_ancestor,
            elements=elements,
        ):
            continue
        ancestor = elements[expected_ancestor]
        allowed_parent_ids = [
            candidate_id
            for candidate_id in ancestor["subtree_ids"]
            if (type_definition(elements[candidate_id]["type"]) or {}).get("kind")
            == "group"
        ]
        result.append(
            _candidate(
                candidate_id=f"placement:{element_id}",
                kind="id_container_mismatch",
                item=item,
                element_ids=[element_id, expected_ancestor],
                new_element_ids=[element_id],
                existing_element_ids=(
                    [] if expected_ancestor in new_ids else [expected_ancestor]
                ),
                affected_element_ids=sorted(
                    set(item["subtree_ids"]) | set(ancestor["subtree_ids"])
                ),
                facts={
                    "element_type": item["type"],
                    "label": item["label"],
                    "actual_parent_id": item["parent_id"],
                    "expected_ancestor_id": expected_ancestor,
                    "allowed_parent_ids": allowed_parent_ids,
                },
                decisions_by_target=decisions_by_target,
            )
        )
    return result


def _duplicate_candidates(
    *,
    elements: dict[str, dict[str, Any]],
    new_ids: set[str],
    decisions_by_target: dict[str, list[str]],
) -> list[dict[str, Any]]:
    sibling_groups: dict[tuple[str, str, str, str], list[str]] = {}
    page_groups: dict[tuple[str, str, str], list[str]] = {}
    for element_id, item in elements.items():
        normalized_label = _normalize_label(item["label"])
        if not normalized_label:
            continue
        sibling_groups.setdefault(
            (item["page_id"], item["parent_id"], item["type"], normalized_label),
            [],
        ).append(element_id)
        page_groups.setdefault(
            (item["page_id"], item["type"], normalized_label), []
        ).append(element_id)

    result: list[dict[str, Any]] = []
    for (page_id, parent_id, type_id, normalized_label), element_ids in sorted(
        sibling_groups.items()
    ):
        new_elements = sorted(set(element_ids) & new_ids)
        if len(element_ids) < 2 or not new_elements:
            continue
        result.append(
            _duplicate_candidate(
                candidate_id="duplicate:" + ":".join(new_elements),
                kind="duplicate_siblings",
                page_id=page_id,
                parent_id=parent_id,
                type_id=type_id,
                normalized_label=normalized_label,
                element_ids=element_ids,
                new_ids=new_ids,
                elements=elements,
                decisions_by_target=decisions_by_target,
            )
        )

    for (page_id, type_id, normalized_label), element_ids in sorted(
        page_groups.items()
    ):
        parent_ids = {elements[element_id]["parent_id"] for element_id in element_ids}
        new_elements = sorted(set(element_ids) & new_ids)
        existing_elements = sorted(set(element_ids) - new_ids)
        if (
            len(element_ids) < 2
            or len(parent_ids) < 2
            or not new_elements
            or not existing_elements
        ):
            continue
        result.append(
            _duplicate_candidate(
                candidate_id="duplicate_page:" + ":".join(new_elements),
                kind="duplicate_page_elements",
                page_id=page_id,
                parent_id="",
                type_id=type_id,
                normalized_label=normalized_label,
                element_ids=element_ids,
                new_ids=new_ids,
                elements=elements,
                decisions_by_target=decisions_by_target,
            )
        )
    return result


def _duplicate_candidate(
    *,
    candidate_id: str,
    kind: str,
    page_id: str,
    parent_id: str,
    type_id: str,
    normalized_label: str,
    element_ids: list[str],
    new_ids: set[str],
    elements: dict[str, dict[str, Any]],
    decisions_by_target: dict[str, list[str]],
) -> dict[str, Any]:
    sorted_ids = sorted(element_ids)
    affected_ids = sorted(
        {
            affected_id
            for duplicate_id in element_ids
            for affected_id in elements[duplicate_id]["subtree_ids"]
        }
    )
    facts: dict[str, Any] = {
        "element_type": type_id,
        "normalized_label": normalized_label,
        "labels": {
            duplicate_id: elements[duplicate_id]["label"]
            for duplicate_id in sorted_ids
        },
    }
    if kind == "duplicate_page_elements":
        facts["parents"] = {
            duplicate_id: elements[duplicate_id]["parent_id"]
            for duplicate_id in sorted_ids
        }
    return {
        "candidate_id": candidate_id,
        "kind": kind,
        "page_id": page_id,
        "parent_id": parent_id,
        "element_ids": sorted_ids,
        "new_element_ids": sorted(set(element_ids) & new_ids),
        "existing_element_ids": sorted(set(element_ids) - new_ids),
        "affected_element_ids": affected_ids,
        "link_ids": [],
        "related_requirement_ids": _related_ids(
            affected_ids, decisions_by_target
        ),
        "facts": facts,
    }


def _candidate(
    *,
    candidate_id: str,
    kind: str,
    item: dict[str, Any],
    element_ids: list[str],
    new_element_ids: list[str],
    existing_element_ids: list[str],
    affected_element_ids: list[str],
    facts: dict[str, Any],
    decisions_by_target: dict[str, list[str]],
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "kind": kind,
        "page_id": item["page_id"],
        "parent_id": item["parent_id"],
        "element_ids": element_ids,
        "new_element_ids": new_element_ids,
        "existing_element_ids": existing_element_ids,
        "affected_element_ids": affected_element_ids,
        "link_ids": [],
        "related_requirement_ids": _related_ids(
            affected_element_ids, decisions_by_target
        ),
        "facts": facts,
    }


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


def _longest_group_prefix(
    element_id: str,
    *,
    page_id: str,
    elements: dict[str, dict[str, Any]],
) -> str:
    matches = []
    for candidate_id, candidate in elements.items():
        if candidate_id == element_id or candidate["page_id"] != page_id:
            continue
        if not element_id.startswith(candidate_id + "."):
            continue
        if (type_definition(candidate["type"]) or {}).get("kind") == "group":
            matches.append(candidate_id)
    return max(matches, key=len) if matches else ""


def _is_inside(
    parent_id: str,
    *,
    ancestor_id: str,
    elements: dict[str, dict[str, Any]],
) -> bool:
    current = parent_id
    visited: set[str] = set()
    while current and current not in visited:
        if current == ancestor_id:
            return True
        visited.add(current)
        current = str(elements.get(current, {}).get("parent_id") or "")
    return False


def _normalize_label(value: str) -> str:
    return re.sub(r"[^\w]+", " ", str(value or "").casefold()).strip()
