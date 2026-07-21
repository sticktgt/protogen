from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.index_builder import rebuild_index
from backend.modules.ui_schema.storage import (
    page_path,
    read_page,
    read_requirement_links,
    read_schema,
    read_ui_links,
    write_page,
    write_requirement_links,
    write_schema,
    write_ui_links,
)
from backend.modules.ui_schema.tree import collect_element_ids


def create_page(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    page_id = payload["id"]
    if read_page(root, page_id):
        raise ValueError("Page already exists")
    page = {
        "id": page_id,
        "title": payload.get("title") or page_id,
        "description": payload.get("description", ""),
        "elements": [],
    }
    write_page(root, page)
    schema = read_schema(root)
    schema.setdefault("pages", []).append({
        "id": page["id"],
        "title": page["title"],
        "file": f"pages/{page['id']}.json",
    })
    write_schema(root, schema)
    rebuild_index(root)
    return page


def update_page(root: Path, page_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    page = read_page(root, page_id)
    if not page:
        raise ValueError("Page not found")
    for field in ("title", "description"):
        if field in payload:
            page[field] = payload[field]
    write_page(root, page)
    schema = read_schema(root)
    for item in schema.get("pages", []):
        if item.get("id") == page_id:
            item["title"] = page.get("title", page_id)
            item["file"] = f"pages/{page_id}.json"
    write_schema(root, schema)
    rebuild_index(root)
    return page


def delete_page(root: Path, page_id: str) -> None:
    page = read_page(root, page_id)
    if not page:
        raise ValueError("Page not found")
    if page.get("elements"):
        raise ValueError("Page has nested elements. Delete elements first.")
    page_element_ids = set(collect_element_ids(page or {}))
    target = page_path(root, page_id)
    if target.exists():
        target.unlink()
    remove_page_from_schema(root, page_id)
    remove_page_links(root, page_id, page_element_ids)
    remove_page_ui_links(root, page_id, page_element_ids)
    rebuild_index(root)


def remove_page_from_schema(root: Path, page_id: str) -> None:
    schema = read_schema(root)
    schema["pages"] = [item for item in schema.get("pages", []) if item.get("id") != page_id]
    write_schema(root, schema)


def remove_page_links(root: Path, page_id: str, page_element_ids: set[str]) -> None:
    links = read_requirement_links(root)
    links["links"] = [
        link for link in links.get("links", [])
        if not (
            (link.get("target_type") == "page" and link.get("target_id") == page_id)
            or (link.get("target_type") == "ui_element" and link.get("target_id") in page_element_ids)
        )
    ]
    write_requirement_links(root, links)


def remove_page_ui_links(root: Path, page_id: str, page_element_ids: set[str]) -> None:
    links = read_ui_links(root)
    links["links"] = [
        link for link in links.get("links", [])
        if not (
            (link.get("source_type") == "page" and link.get("source_id") == page_id)
            or (link.get("target_type") == "page" and link.get("target_id") == page_id)
            or (link.get("source_type") == "ui_element" and link.get("source_id") in page_element_ids)
            or (link.get("target_type") == "ui_element" and link.get("target_id") in page_element_ids)
        )
    ]
    write_ui_links(root, links)
