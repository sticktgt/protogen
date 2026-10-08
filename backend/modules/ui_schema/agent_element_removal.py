from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_preservation import collect_schema_ids
from backend.modules.ui_schema.files import read_json, write_json


def remove_new_elements_batch(
    *,
    base_root: Path,
    working_root: Path,
    element_ids: list[str],
    maximum_removals: int,
) -> dict[str, Any]:
    """Remove explicitly selected elements created during the current run.

    Existing base elements, including descendants of a selected new container, are
    protected. UI and requirement links that reference removed IDs are cleaned as a
    mechanical consequence of the explicit deletion.
    """
    normalized = _normalize_ids(element_ids, maximum=maximum_removals)
    _, base_element_ids = collect_schema_ids(base_root)
    documents = _read_documents(working_root)
    current = _element_catalog(documents)

    missing = sorted(set(normalized) - set(current))
    if missing:
        raise ValueError("Cannot remove missing UI elements: " + ", ".join(missing))

    protected = sorted(set(normalized) & base_element_ids)
    if protected:
        raise ValueError(
            "Existing base elements cannot be removed by structural review: "
            + ", ".join(protected)
        )

    selected_subtree_ids: set[str] = set()
    for element_id in normalized:
        selected_subtree_ids.update(_tree_ids([current[element_id]["element"]]))
    protected_descendants = sorted(selected_subtree_ids & base_element_ids)
    if protected_descendants:
        raise ValueError(
            "A selected new container contains protected base elements and cannot be removed: "
            + ", ".join(protected_descendants)
        )

    removed: list[str] = []
    for document_id, document in documents.items():
        key = "root_elements" if document_id == "app" else "elements"
        updated, deleted = _remove_tree(document.get(key, []), set(normalized))
        if deleted:
            document[key] = updated
            _write_document(working_root, document_id, document)
            removed.extend(deleted)

    removed_ids = set(removed)
    _remove_link_references(working_root, removed_ids)
    from backend.modules.ui_schema.index_builder import rebuild_index

    rebuild_index(working_root)
    return {
        "ok": True,
        "removed_element_ids": sorted(removed_ids),
        "removed_element_count": len(removed_ids),
    }


def _normalize_ids(values: list[str], *, maximum: int) -> list[str]:
    if len(values) > maximum:
        raise ValueError(
            f"remove_elements may contain at most {maximum} element IDs"
        )
    result: list[str] = []
    for index, raw in enumerate(values):
        value = str(raw or "").strip()
        if not value:
            raise ValueError(f"remove_elements[{index}] must be a non-empty ID")
        if value not in result:
            result.append(value)
    return result


def _read_documents(root: Path) -> dict[str, dict[str, Any]]:
    documents = {"app": read_json(root / "app.json", {"root_elements": []})}
    pages_root = root / "pages"
    if pages_root.is_dir():
        for path in sorted(pages_root.glob("*.json")):
            page = read_json(path, {})
            page_id = str(page.get("id") or path.stem).strip()
            if page_id:
                documents[page_id] = page
    return documents


def _write_document(root: Path, document_id: str, document: dict[str, Any]) -> None:
    path = root / "app.json" if document_id == "app" else root / "pages" / f"{document_id}.json"
    write_json(path, document)


def _element_catalog(
    documents: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for document_id, document in documents.items():
        key = "root_elements" if document_id == "app" else "elements"
        _collect(document.get(key, []), result, page_id=document_id)
    return result


def _collect(
    items: Any,
    result: dict[str, dict[str, Any]],
    *,
    page_id: str,
) -> None:
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        element_id = str(item.get("id") or "").strip()
        if element_id:
            result[element_id] = {"page_id": page_id, "element": item}
        _collect(item.get("children", []), result, page_id=page_id)


def _remove_tree(
    items: Any,
    targets: set[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    kept: list[dict[str, Any]] = []
    deleted: list[str] = []
    for raw in items if isinstance(items, list) else []:
        if not isinstance(raw, dict):
            continue
        item = deepcopy(raw)
        element_id = str(item.get("id") or "")
        if element_id in targets:
            deleted.extend(_tree_ids([item]))
            continue
        children, child_deleted = _remove_tree(item.get("children", []), targets)
        if "children" in item:
            item["children"] = children
        kept.append(item)
        deleted.extend(child_deleted)
    return kept, deleted


def _tree_ids(items: Any) -> list[str]:
    result: list[str] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        element_id = str(item.get("id") or "").strip()
        if element_id:
            result.append(element_id)
        result.extend(_tree_ids(item.get("children", [])))
    return result


def _remove_link_references(root: Path, removed_ids: set[str]) -> None:
    if not removed_ids:
        return
    ui_path = root / "links.json"
    ui_document = read_json(ui_path, {"links": []})
    ui_document["links"] = [
        link
        for link in ui_document.get("links", [])
        if isinstance(link, dict)
        and link.get("source_id") not in removed_ids
        and link.get("target_id") not in removed_ids
    ]
    write_json(ui_path, ui_document)

    mapping_path = root / "mappings" / "requirement_ui_links.json"
    mapping = read_json(mapping_path, {"links": []})
    mapping["links"] = [
        link
        for link in mapping.get("links", [])
        if isinstance(link, dict) and link.get("target_id") not in removed_ids
    ]
    write_json(mapping_path, mapping)
