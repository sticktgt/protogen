from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.modules.ui_schema.element_types import (
    allowed_child_types,
    ensure_type_allowed,
    is_group_type,
    root_type_ids,
    type_definition,
)
from backend.modules.ui_schema.index_builder import rebuild_index
from backend.modules.ui_schema.storage import (
    read_app,
    read_requirement_links,
    read_ui_links,
    write_app,
    write_requirement_links,
    write_ui_links,
)
from backend.modules.ui_schema.tree import collect_element_ids, element_exists, find_element, remove_element


def update_app(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    app = read_app(root)
    for field in ("title", "description"):
        if field in payload:
            value = payload[field]
            if value == "" and field == "description":
                app.pop(field, None)
            else:
                app[field] = value
    write_app(root, app)
    rebuild_index(root)
    return app


def add_app_element(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    app = read_app(root)
    element_id = payload.get("id") or f"app.{uuid4().hex[:8]}"
    if element_exists({"elements": app.get("root_elements", [])}, element_id):
        raise ValueError("Element already exists")
    element = build_app_element(element_id, payload)
    parent_id = payload.get("parent_id")
    if parent_id:
        append_to_app_parent(app, parent_id, element)
    else:
        element_type = element["type"]
        if element_type not in root_type_ids(scope="app"):
            raise ValueError(f"Element type {element_type} cannot be added as an application root")
        definition = type_definition(element_type) or {}
        if definition.get("unique_root") and any(
            current.get("type") == element_type for current in app.get("root_elements", [])
        ):
            raise ValueError(f"Only one root element of type {element_type} is allowed")
        app.setdefault("root_elements", []).append(element)
    write_app(root, app)
    rebuild_index(root)
    return element


def build_app_element(element_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    element_type = payload.get("type", "menu_item")
    ensure_type_allowed(element_type, scope="app")
    element = {
        "id": element_id,
        "type": element_type,
        "label": payload.get("label") or element_id,
    }
    if payload.get("description"):
        element["description"] = payload["description"]
    if payload.get("purpose"):
        element["purpose"] = payload["purpose"]
    if is_group_type(element_type, scope="app"):
        element["children"] = []
    return element


def append_to_app_parent(app: dict[str, Any], parent_id: str, element: dict[str, Any]) -> None:
    parent = find_element(app.get("root_elements", []), parent_id)
    if not parent:
        raise ValueError("Parent element not found")
    parent_type = parent.get("type", "")
    child_type = element.get("type", "")
    if child_type not in allowed_child_types(parent_type, scope="app"):
        raise ValueError(f"Element type {parent_type} cannot contain {child_type}")
    parent.setdefault("children", []).append(element)


def update_app_element(root: Path, element_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    app = read_app(root)
    element = find_element(app.get("root_elements", []), element_id)
    if not element:
        raise ValueError("Element not found")
    for field in ("label", "description", "purpose"):
        if field in payload:
            value = payload[field]
            if value == "" and field in ("description", "purpose"):
                element.pop(field, None)
            else:
                element[field] = value
    if "type" in payload and payload["type"] != element.get("type"):
        ensure_type_allowed(payload["type"], scope="app")
        raise ValueError("Changing app element type is not supported")
    write_app(root, app)
    rebuild_index(root)
    return element


def delete_app_element(root: Path, element_id: str) -> None:
    app = read_app(root)
    element = find_element(app.get("root_elements", []), element_id)
    if not element:
        raise ValueError("Element not found")
    if element.get("children"):
        raise ValueError("Element has nested elements. Delete nested elements first.")
    removed_ids = set(collect_element_ids({"elements": [element]}))
    app["root_elements"] = remove_element(app.get("root_elements", []), element_id)
    write_app(root, app)
    remove_app_element_links(root, removed_ids)
    rebuild_index(root)


def remove_app_element_links(root: Path, removed_ids: set[str]) -> None:
    requirement_links = read_requirement_links(root)
    requirement_links["links"] = [
        link
        for link in requirement_links.get("links", [])
        if not (link.get("target_type") == "ui_element" and link.get("target_id") in removed_ids)
    ]
    write_requirement_links(root, requirement_links)

    ui_links = read_ui_links(root)
    ui_links["links"] = [
        link
        for link in ui_links.get("links", [])
        if link.get("source_id") not in removed_ids and link.get("target_id") not in removed_ids
    ]
    write_ui_links(root, ui_links)
