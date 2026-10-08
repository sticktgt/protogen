from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from backend.modules.ui_schema.files import read_json, write_json


def remove_schema_objects(
    *,
    run_path: Path,
    removals: list[dict[str, Any]],
) -> dict[str, Any]:
    if not removals:
        raise ValueError("removals must contain at least one explicit deletion")
    if len(removals) > 30:
        raise ValueError("At most 30 objects can be removed in one call")

    working_root = run_path / "working" / "ui_schema"
    base_root = run_path / "base" / "ui_schema"
    base_pages, base_elements = _catalog(base_root)
    current_pages, current_elements = _catalog(working_root)

    page_ids: set[str] = set()
    element_ids: set[str] = set()
    decisions: list[dict[str, Any]] = []
    for index, raw in enumerate(removals):
        if not isinstance(raw, dict):
            raise ValueError(f"removals[{index}] must be an object")
        target_type = str(raw.get("target_type") or "").strip()
        target_id = str(raw.get("target_id") or "").strip()
        reason = str(raw.get("reason") or "").strip()
        requirement_ids = _string_list(raw.get("requirement_ids"))
        if target_type not in {"page", "ui_element"}:
            raise ValueError(f"removals[{index}].target_type must be page or ui_element")
        if not target_id:
            raise ValueError(f"removals[{index}].target_id is required")
        if len(reason) < 20:
            raise ValueError(f"removals[{index}].reason must clearly explain the deletion")
        if target_type == "page":
            if target_id not in current_pages:
                raise ValueError(f"Page does not exist: {target_id}")
            page_ids.add(target_id)
        else:
            if target_id not in current_elements:
                raise ValueError(f"UI element does not exist: {target_id}")
            element_ids.add(target_id)
        decisions.append({
            "target_type": target_type,
            "target_id": target_id,
            "reason": reason,
            "requirement_ids": requirement_ids,
            "existed_in_base": target_id in (base_pages if target_type == "page" else base_elements),
        })

    removed_pages, page_element_ids = _remove_pages(working_root, page_ids)
    removed_elements = [*page_element_ids, *_remove_elements(working_root, element_ids)]
    removed_target_ids = set(removed_pages) | set(removed_elements)
    removed_links = _remove_references(working_root, removed_target_ids)

    record_path = run_path / "result" / "explicit_deletions.json"
    previous = read_json(record_path, {"decisions": []})
    previous_decisions = previous.get("decisions", []) if isinstance(previous, dict) else []
    record = {
        "decisions": [*previous_decisions, *decisions],
        "removed_page_ids": sorted(set(previous.get("removed_page_ids", [])) | set(removed_pages)),
        "removed_element_ids": sorted(set(previous.get("removed_element_ids", [])) | set(removed_elements)),
        "removed_ui_link_ids": sorted(set(previous.get("removed_ui_link_ids", [])) | set(removed_links["ui_links"])),
        "removed_requirement_link_ids": sorted(set(previous.get("removed_requirement_link_ids", [])) | set(removed_links["requirement_links"])),
    }
    write_json(record_path, record)
    return {"ok": True, **record}


def approved_deletions(run_path: Path) -> tuple[set[str], set[str]]:
    record = read_json(run_path / "result" / "explicit_deletions.json", {})
    return set(record.get("removed_page_ids", [])), set(record.get("removed_element_ids", []))


def _remove_pages(root: Path, page_ids: set[str]) -> tuple[list[str], list[str]]:
    if not page_ids:
        return [], []
    schema_path = root / "schema.json"
    schema = read_json(schema_path, {})
    schema["pages"] = [item for item in schema.get("pages", []) if item.get("id") not in page_ids]
    write_json(schema_path, schema)
    removed_pages: list[str] = []
    removed_elements: list[str] = []
    for page_id in page_ids:
        path = root / "pages" / f"{page_id}.json"
        if path.exists():
            page = read_json(path, {})
            removed_elements.extend(_tree_ids(page.get("elements", [])))
            path.unlink()
        removed_pages.append(page_id)
    return removed_pages, removed_elements


def _remove_elements(root: Path, element_ids: set[str]) -> list[str]:
    if not element_ids:
        return []
    removed: list[str] = []
    app_path = root / "app.json"
    app = read_json(app_path, {})
    app["root_elements"], found = _remove_tree(app.get("root_elements", []), element_ids)
    if found:
        write_json(app_path, app)
        removed.extend(found)
    for path in sorted((root / "pages").glob("*.json")):
        page = read_json(path, {})
        page["elements"], found = _remove_tree(page.get("elements", []), element_ids)
        if found:
            write_json(path, page)
            removed.extend(found)
    return removed


def _remove_references(root: Path, removed_ids: set[str]) -> dict[str, list[str]]:
    ui_path = root / "links.json"
    ui_doc = read_json(ui_path, {"links": []})
    kept_ui, removed_ui = [], []
    for link in ui_doc.get("links", []):
        if link.get("source_id") in removed_ids or link.get("target_id") in removed_ids:
            removed_ui.append(str(link.get("id") or ""))
        else:
            kept_ui.append(link)
    ui_doc["links"] = kept_ui
    write_json(ui_path, ui_doc)

    req_path = root / "mappings" / "requirement_ui_links.json"
    req_doc = read_json(req_path, {"links": []})
    kept_req, removed_req = [], []
    for link in req_doc.get("links", []):
        if link.get("target_id") in removed_ids:
            removed_req.append(str(link.get("id") or ""))
        else:
            kept_req.append(link)
    req_doc["links"] = kept_req
    write_json(req_path, req_doc)
    return {"ui_links": [x for x in removed_ui if x], "requirement_links": [x for x in removed_req if x]}


def _catalog(root: Path) -> tuple[set[str], set[str]]:
    pages: set[str] = set()
    elements: set[str] = set(_tree_ids(read_json(root / "app.json", {}).get("root_elements", [])))
    for path in sorted((root / "pages").glob("*.json")):
        page = read_json(path, {})
        if page.get("id"):
            pages.add(str(page["id"]))
        elements.update(_tree_ids(page.get("elements", [])))
    return pages, elements


def _tree_ids(items: Any) -> list[str]:
    result: list[str] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if item.get("id"):
            result.append(str(item["id"]))
        result.extend(_tree_ids(item.get("children", [])))
    return result


def _remove_tree(items: Any, targets: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    kept: list[dict[str, Any]] = []
    removed: list[str] = []
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        item = deepcopy(raw)
        if item.get("id") in targets:
            removed.extend(_tree_ids([item]))
            continue
        children, child_removed = _remove_tree(item.get("children", []), targets)
        if "children" in item:
            item["children"] = children
        kept.append(item)
        removed.extend(child_removed)
    return kept, removed


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("requirement_ids must be a list")
    return [str(item).strip() for item in value if str(item).strip()]
