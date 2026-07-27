from __future__ import annotations

from typing import Any

from backend.modules.ui_schema.element_types import (
    allowed_child_types,
    ensure_type_allowed,
    root_type_ids,
    type_definition,
)


def validate_element(
    element: Any,
    *,
    scope: str,
    parent_type: str | None,
    object_ids: set[str],
    element_ids: set[str],
    element_types: dict[str, str],
    errors: list[str],
    path: str,
) -> None:
    if not isinstance(element, dict):
        errors.append(f"{path} contains a non-object element")
        return

    element_id = element.get("id")
    type_id = element.get("type")
    label = element.get("label")
    if not isinstance(element_id, str) or not element_id.strip():
        errors.append(f"Element without a valid id in {path}")
        return
    if element_id in object_ids:
        errors.append(f"Duplicate UI object id: {element_id}")
        return
    object_ids.add(element_id)
    element_ids.add(element_id)

    try:
        definition = ensure_type_allowed(str(type_id), scope=scope)
    except ValueError as exc:
        errors.append(f"Element {element_id}: {exc}")
        definition = None
    if not isinstance(label, str) or not label.strip():
        errors.append(f"Element {element_id} must have a non-empty label")

    if parent_type is None and scope == "app" and type_id not in root_type_ids(scope="app"):
        errors.append(f"App root element {element_id} has unsupported root type: {type_id}")
    if parent_type is not None:
        try:
            if type_id not in allowed_child_types(parent_type, scope=scope):
                errors.append(f"Element {element_id} type {type_id} is not allowed inside {parent_type}")
        except ValueError as exc:
            errors.append(f"Element {element_id}: {exc}")

    children = element.get("children")
    if definition and definition.get("kind") == "atomic":
        if isinstance(children, list) and children:
            errors.append(f"Atomic element {element_id} cannot contain children")
        elif children not in (None, []):
            errors.append(f"Atomic element {element_id} has invalid children value")
    elif definition and definition.get("kind") == "group":
        if children is None:
            children = []
        if not isinstance(children, list):
            errors.append(f"Group element {element_id} children must be a list")
            children = []
        for child in children:
            validate_element(
                child,
                scope=scope,
                parent_type=str(type_id),
                object_ids=object_ids,
                element_ids=element_ids,
                element_types=element_types,
                errors=errors,
                path=f"{path}.{element_id}.children",
            )
    if isinstance(type_id, str):
        element_types[element_id] = type_id


def validate_ui_links(
    data: dict[str, Any],
    *,
    page_ids: set[str],
    element_ids: set[str],
    element_types: dict[str, str],
    errors: list[str],
) -> None:
    links = data.get("links")
    if not isinstance(links, list):
        errors.append("links.json links must be a list")
        return
    seen: set[str] = set()
    for index, link in enumerate(links):
        if not isinstance(link, dict):
            errors.append(f"links[{index}] must be an object")
            continue
        link_id = link.get("id")
        if not isinstance(link_id, str) or not link_id:
            errors.append(f"UI link at index {index} has no id")
        elif link_id in seen:
            errors.append(f"Duplicate UI link id: {link_id}")
        else:
            seen.add(link_id)

        source_type, source_id = link.get("source_type"), link.get("source_id")
        target_type, target_id = link.get("target_type"), link.get("target_id")
        relation = link.get("relation")
        if not target_exists(source_type, source_id, page_ids, element_ids):
            errors.append(f"UI link {link_id or index} has missing source: {source_type}:{source_id}")
        if not target_exists(target_type, target_id, page_ids, element_ids):
            errors.append(f"UI link {link_id or index} has missing target: {target_type}:{target_id}")
        if source_type == "ui_element" and source_id in element_types:
            definition = type_definition(element_types[source_id])
            if not definition or definition.get("link_source") is not True:
                errors.append(f"Element {source_id} cannot be a UI link source")
        if relation not in {"navigates_to", "opens_modal"}:
            errors.append(f"UI link {link_id or index} has unsupported relation: {relation}")
        if relation == "opens_modal" and target_type == "ui_element":
            if element_types.get(str(target_id)) != "modal":
                errors.append(f"UI link {link_id or index} opens_modal target must be a modal")


def validate_requirement_links(
    data: dict[str, Any],
    *,
    requirement_ids: set[str],
    page_ids: set[str],
    element_ids: set[str],
    errors: list[str],
    warnings: list[str],
) -> None:
    links = data.get("links")
    if not isinstance(links, list):
        errors.append("requirement_ui_links.json links must be a list")
        return
    seen: set[str] = set()
    seen_pairs: set[tuple[str, str, str, str]] = set()
    for index, link in enumerate(links):
        if not isinstance(link, dict):
            errors.append(f"requirement links[{index}] must be an object")
            continue
        link_id = link.get("id")
        if not isinstance(link_id, str) or not link_id:
            errors.append(f"Requirement link at index {index} has no id")
        elif link_id in seen:
            errors.append(f"Duplicate requirement link id: {link_id}")
        else:
            seen.add(link_id)

        requirement_id = link.get("requirement_id")
        target_type, target_id = link.get("target_type"), link.get("target_id")
        relation = link.get("relation")
        if requirement_id not in requirement_ids:
            warnings.append(f"Requirement link {link_id or index} references an unknown requirement: {requirement_id}")
        if not target_exists(target_type, target_id, page_ids, element_ids):
            errors.append(f"Requirement link {link_id or index} has missing target: {target_type}:{target_id}")
        if relation not in {"implemented_by", "supports", "triggers", "starts_flow"}:
            errors.append(f"Requirement link {link_id or index} has unsupported relation: {relation}")
        pair = (str(requirement_id), str(target_type), str(target_id), str(relation))
        if pair in seen_pairs:
            errors.append(f"Duplicate requirement mapping: {requirement_id} -> {target_type}:{target_id} ({relation})")
        seen_pairs.add(pair)


def target_exists(target_type: Any, target_id: Any, page_ids: set[str], element_ids: set[str]) -> bool:
    if target_type == "page":
        return target_id in page_ids
    if target_type == "ui_element":
        return target_id in element_ids
    return False
