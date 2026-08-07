from __future__ import annotations

from typing import Any

from backend.modules.ui_schema.element_types import type_definition


def collect_page_candidates(
    *,
    base_documents: dict[str, dict[str, Any]],
    working_documents: dict[str, dict[str, Any]],
    working_elements: dict[str, dict[str, Any]],
    working_links: list[dict[str, Any]],
    decisions_by_target: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Return new pages that have no incoming navigation from another page/app."""
    base_page_ids = {page_id for page_id in base_documents if page_id != "app"}
    working_page_ids = {page_id for page_id in working_documents if page_id != "app"}
    new_page_ids = sorted(working_page_ids - base_page_ids)
    if not new_page_ids:
        return []

    navigation_parents = _app_navigation_parent_ids(working_elements)
    navigation_sources = _app_navigation_source_ids(
        working_elements,
        navigation_parents=navigation_parents,
    )
    affected_navigation_ids = sorted(set(navigation_parents) | set(navigation_sources))

    result: list[dict[str, Any]] = []
    for page_id in new_page_ids:
        related_requirement_ids = sorted(set(decisions_by_target.get(page_id, [])))
        if not related_requirement_ids:
            continue
        incoming = [
            link
            for link in working_links
            if _is_external_page_navigation(
                link,
                target_page_id=page_id,
                elements=working_elements,
            )
        ]
        if incoming:
            continue
        page = working_documents.get(page_id, {})
        result.append(
            {
                "candidate_id": f"new_page_navigation:{page_id}",
                "kind": "new_page_without_incoming_navigation",
                "page_id": page_id,
                "parent_id": "",
                "element_ids": affected_navigation_ids,
                "new_element_ids": [],
                "existing_element_ids": affected_navigation_ids,
                "affected_element_ids": [],
                "link_ids": [],
                "related_requirement_ids": related_requirement_ids,
                "context_page_ids": ["app", page_id],
                "facts": {
                    "page_id": page_id,
                    "page_title": str(page.get("title") or ""),
                    "incoming_navigation_count": 0,
                    "allowed_navigation_parent_ids": navigation_parents,
                    "existing_navigation_source_ids": navigation_sources,
                },
            }
        )
    return result


def _app_navigation_parent_ids(
    elements: dict[str, dict[str, Any]],
) -> list[str]:
    result: list[str] = []
    for element_id, item in elements.items():
        if item.get("page_id") != "app":
            continue
        type_id = str(item.get("type") or "")
        if type_id in {"main_menu", "menu_group"}:
            result.append(element_id)
    return sorted(result)


def _app_navigation_source_ids(
    elements: dict[str, dict[str, Any]],
    *,
    navigation_parents: list[str],
) -> list[str]:
    result: list[str] = []
    allowed_ancestors = set(navigation_parents)
    for element_id, item in elements.items():
        if item.get("page_id") != "app":
            continue
        definition = type_definition(str(item.get("type") or "")) or {}
        if definition.get("link_source") is not True:
            continue
        if _is_inside_any(
            str(item.get("parent_id") or ""),
            ancestors=allowed_ancestors,
            elements=elements,
        ):
            result.append(element_id)
    return sorted(result)


def _is_inside_any(
    parent_id: str,
    *,
    ancestors: set[str],
    elements: dict[str, dict[str, Any]],
) -> bool:
    current = parent_id
    visited: set[str] = set()
    while current and current not in visited:
        if current in ancestors:
            return True
        visited.add(current)
        current = str(elements.get(current, {}).get("parent_id") or "")
    return False


def _is_external_page_navigation(
    link: Any,
    *,
    target_page_id: str,
    elements: dict[str, dict[str, Any]],
) -> bool:
    if not isinstance(link, dict):
        return False
    if link.get("relation") != "navigates_to":
        return False
    if link.get("target_type") != "page" or link.get("target_id") != target_page_id:
        return False
    source_type = str(link.get("source_type") or "")
    source_id = str(link.get("source_id") or "")
    if source_type == "page":
        return source_id != target_page_id
    if source_type == "ui_element":
        source_page_id = str(elements.get(source_id, {}).get("page_id") or "")
        return bool(source_page_id and source_page_id != target_page_id)
    return False
