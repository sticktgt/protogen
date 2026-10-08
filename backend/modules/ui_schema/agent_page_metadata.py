from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_normalize_documents import canonicalize_schema_document
from backend.modules.ui_schema.files import read_json, write_json


def update_page_metadata(
    *,
    working_root: Path,
    page_id: str,
    title: str | None,
    description: str | None,
) -> dict[str, Any]:
    """Update only metadata of one existing page and its schema registry entry."""
    page_id = str(page_id or "").strip()
    if not page_id or "/" in page_id or "\\" in page_id or page_id in {".", ".."}:
        raise ValueError("page_id must be a dotted identifier without path separators")
    if title is not None:
        title = str(title).strip()
        if not title:
            raise ValueError("title must be non-empty when provided")
    if description is not None:
        description = str(description)

    page_path = working_root / "pages" / f"{page_id}.json"
    page = read_json(page_path, {})
    if not isinstance(page, dict) or str(page.get("id") or "") != page_id:
        raise ValueError(f"Page {page_id} does not exist and cannot be updated")

    changed_fields: list[str] = []
    if title is not None and page.get("title") != title:
        page["title"] = title
        changed_fields.append("title")
    if description is not None and page.get("description", "") != description:
        page["description"] = description
        changed_fields.append("description")
    write_json(page_path, page)

    schema_path = working_root / "schema.json"
    schema = canonicalize_schema_document(read_json(schema_path, {}))
    pages = schema.get("pages", [])
    found = False
    for item in pages if isinstance(pages, list) else []:
        if not isinstance(item, dict) or str(item.get("id") or "") != page_id:
            continue
        found = True
        if title is not None:
            item["title"] = title
        break
    if not found:
        raise ValueError(f"Page {page_id} is missing from schema.json")
    write_json(schema_path, schema)
    return {
        "page_id": page_id,
        "changed_fields": changed_fields,
        "changed": bool(changed_fields),
    }
