from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.files import write_json
from backend.modules.ui_schema.storage import index_path, read_app, read_page, read_requirement_links, read_schema, read_ui_links
from backend.modules.ui_schema.tree import collect_element_ids


def rebuild_index(root: Path) -> dict[str, Any]:
    schema = read_schema(root)
    app = read_app(root)
    requirement_links = read_requirement_links(root).get("links", [])
    ui_links = read_ui_links(root).get("links", [])
    pages_index = []
    for item in schema.get("pages", []):
        page_id = item.get("id")
        page = read_page(root, page_id) or {}
        requirement_ids = sorted({
            link.get("requirement_id") for link in requirement_links
            if link.get("target_id") == page_id or link.get("target_id") in collect_element_ids(page)
        })
        pages_index.append({
            "id": page_id,
            "title": page.get("title") or item.get("title") or page_id,
            "summary": page.get("description", ""),
            "requirement_ids": [value for value in requirement_ids if value],
            "main_elements": summarize_elements(page.get("elements", []), limit=8),
            "incoming_links": [link for link in ui_links if link.get("target_type") == "page" and link.get("target_id") == page_id],
        })
    index = {
        "pages": pages_index,
        "root_elements": summarize_elements(app.get("root_elements", []), limit=20),
    }
    write_json(index_path(root), index)
    return index


def summarize_elements(elements: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    result = []
    for element in elements:
        result.append({
            "id": element.get("id"),
            "type": element.get("type"),
            "label": element.get("label") or element.get("title") or element.get("id"),
        })
        if len(result) >= limit:
            break
    return result
