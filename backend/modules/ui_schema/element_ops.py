from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.modules.ui_schema.element_types import allowed_child_types, ensure_type_allowed, is_group_type
from backend.modules.ui_schema.index_builder import rebuild_index
from backend.modules.ui_schema.storage import (
    read_page,
    read_requirement_links,
    read_ui_links,
    write_page,
    write_requirement_links,
    write_ui_links,
)
from backend.modules.ui_schema.tree import collect_element_ids, element_exists, find_element, remove_element


def add_element(root: Path, page_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    page = read_page(root, page_id)
    if not page:
        raise ValueError("Page not found")
    element_id = payload.get("id") or f"{page_id}.{uuid4().hex[:8]}"
    element = build_element(element_id, payload)
    if element_exists(page, element_id):
        raise ValueError("Element already exists")
    parent_id = payload.get("parent_id")
    if parent_id:
        append_to_parent(page, parent_id, element)
    else:
        page.setdefault("elements", []).append(element)
    write_page(root, page)
    rebuild_index(root)
    return element


def build_element(element_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    element_type = payload.get("type", "section")
    ensure_type_allowed(element_type, scope="page")
    element = {
        "id": element_id,
        "type": element_type,
        "label": payload.get("label") or payload.get("title") or element_id,
    }
    if payload.get("description"):
        element["description"] = payload["description"]
    if payload.get("purpose"):
        element["purpose"] = payload["purpose"]
    if is_group_type(element_type, scope="page"):
        element["children"] = []
    return element


def append_to_parent(page: dict[str, Any], parent_id: str, element: dict[str, Any]) -> None:
    parent = find_element(page.get("elements", []), parent_id)
    if not parent:
        raise ValueError("Parent element not found")
    parent_type = parent.get("type", "")
    child_type = element.get("type", "")
    if child_type not in allowed_child_types(parent_type, scope="page"):
        raise ValueError(f"Element type {parent_type} cannot contain {child_type}")
    parent.setdefault("children", []).append(element)


def update_element(root: Path, page_id: str, element_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    page = read_page(root, page_id)
    if not page:
        raise ValueError("Page not found")
    element = find_element(page.get("elements", []), element_id)
    if not element:
        raise ValueError("Element not found")

    if "type" in payload:
        new_type = payload["type"]
        ensure_type_allowed(new_type, scope="page")
        new_is_group = is_group_type(new_type, scope="page")
        if not new_is_group and element.get("children"):
            raise ValueError("Element has nested elements and cannot be changed to an atomic type")
        element["type"] = new_type
        if new_is_group:
            element.setdefault("children", [])
        else:
            element.pop("children", None)

    for field in ("label", "description", "purpose"):
        if field in payload:
            value = payload[field]
            if value == "" and field in ("description", "purpose"):
                element.pop(field, None)
            else:
                element[field] = value
    write_page(root, page)
    rebuild_index(root)
    return element


def delete_element(root: Path, page_id: str, element_id: str) -> None:
    page = read_page(root, page_id)
    if not page:
        raise ValueError("Page not found")
    element = find_element(page.get("elements", []), element_id)
    if not element:
        raise ValueError("Element not found")
    if element.get("children"):
        raise ValueError("Element has nested elements. Delete nested elements first.")
    removed_ids = set(collect_element_ids({"elements": [element]}))
    page["elements"] = remove_element(page.get("elements", []), element_id)
    write_page(root, page)
    remove_element_links(root, removed_ids)
    remove_element_ui_links(root, removed_ids)
    rebuild_index(root)


def remove_element_links(root: Path, removed_ids: set[str]) -> None:
    links = read_requirement_links(root)
    links["links"] = [
        link
        for link in links.get("links", [])
        if not (link.get("target_type") == "ui_element" and link.get("target_id") in removed_ids)
    ]
    write_requirement_links(root, links)


def remove_element_ui_links(root: Path, removed_ids: set[str]) -> None:
    links = read_ui_links(root)
    links["links"] = [
        link
        for link in links.get("links", [])
        if not (link.get("source_id") in removed_ids or link.get("target_id") in removed_ids)
    ]
    write_ui_links(root, links)
