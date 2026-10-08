from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from backend.modules.ui_schema.storage import list_pages, read_app


def build_audit_target_context(
    schema_root: Path,
    *,
    target_keys: Iterable[tuple[str, str]],
) -> tuple[dict[str, dict[str, Any]], set[tuple[str, str]]]:
    """Return deduplicated local outlines of declared targets and descendants.

    Canonical UI-schema storage remains hierarchical. Audit receives a compact view
    grouped by page/app so several targets from the same document do not duplicate
    the same UI tree in the model context.
    """
    keys = {(str(kind), str(target_id)) for kind, target_id in target_keys}
    app = read_app(schema_root)
    pages = {
        str(item.get("id") or item.get("details", {}).get("id") or ""): item.get(
            "details", {}
        )
        for item in list_pages(schema_root)
    }
    requested_pages = {
        target_id for target_type, target_id in keys if target_type == "page"
    }
    outline_rows: dict[str, dict[str, dict[str, Any]]] = {}
    metadata: dict[str, dict[str, Any]] = {}
    related_keys: set[tuple[str, str]] = set(keys)

    for page_id in sorted(requested_pages):
        page = pages.get(page_id)
        if not isinstance(page, dict):
            continue
        metadata[page_id] = {
            "page_id": page_id,
            "title": str(page.get("title") or ""),
            "description": str(page.get("description") or ""),
        }
        _merge_rows(
            outline_rows,
            page_id=page_id,
            rows=_flatten_elements(page.get("elements", []), parent_id=page_id),
        )

    for target_type, target_id in sorted(keys):
        if target_type != "ui_element":
            continue

        found = _find_element_with_parent(
            app.get("root_elements", []),
            target_id,
            parent_id="app",
        )
        page_id = "app"
        if found is None:
            for candidate_page_id, page in pages.items():
                found = _find_element_with_parent(
                    page.get("elements", []),
                    target_id,
                    parent_id=candidate_page_id,
                )
                if found is not None:
                    page_id = candidate_page_id
                    break
        if found is None:
            continue

        element, parent_id = found
        if page_id not in metadata:
            if page_id == "app":
                metadata[page_id] = {
                    "page_id": "app",
                    "title": str(app.get("title") or ""),
                    "description": str(app.get("description") or ""),
                }
            else:
                page = pages.get(page_id, {})
                metadata[page_id] = {
                    "page_id": page_id,
                    "title": str(page.get("title") or ""),
                    "description": str(page.get("description") or ""),
                }
        if page_id not in requested_pages:
            _merge_rows(
                outline_rows,
                page_id=page_id,
                rows=_flatten_elements([element], parent_id=parent_id),
            )

    outlines: dict[str, dict[str, Any]] = {}
    for page_id in sorted(metadata):
        rows = list(outline_rows.get(page_id, {}).values())
        outlines[page_id] = {
            **metadata[page_id],
            "elements": rows,
        }
        related_keys.update(
            ("ui_element", str(item.get("id") or ""))
            for item in rows
            if str(item.get("id") or "")
        )
    return outlines, related_keys


def _merge_rows(
    outline_rows: dict[str, dict[str, dict[str, Any]]],
    *,
    page_id: str,
    rows: list[dict[str, Any]],
) -> None:
    page_rows = outline_rows.setdefault(page_id, {})
    for row in rows:
        element_id = str(row.get("id") or "")
        if element_id and element_id not in page_rows:
            page_rows[element_id] = row


def _find_element_with_parent(
    items: Any,
    target_id: str,
    *,
    parent_id: str,
) -> tuple[dict[str, Any], str] | None:
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        if item_id == target_id:
            return item, parent_id
        nested = _find_element_with_parent(
            item.get("children", []),
            target_id,
            parent_id=item_id or parent_id,
        )
        if nested is not None:
            return nested
    return None


def _flatten_elements(items: Any, *, parent_id: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        children = item.get("children", [])
        compact = {
            key: item[key]
            for key in ("id", "type", "label", "description")
            if key in item and item[key] not in (None, "", [], {})
        }
        compact["parent_id"] = parent_id
        result.append(compact)
        result.extend(
            _flatten_elements(
                children,
                parent_id=item_id or parent_id,
            )
        )
    return result
