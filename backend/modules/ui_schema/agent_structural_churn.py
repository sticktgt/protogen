from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.files import read_json
from backend.modules.ui_schema.storage import list_pages, read_app


def build_structural_churn_report(
    base_root: Path,
    working_root: Path,
) -> dict[str, Any]:
    base = _snapshot(base_root)
    working = _snapshot(working_root)

    moved_elements: list[dict[str, Any]] = []
    emptied_containers: list[dict[str, Any]] = []
    for element_id in sorted(base["elements"].keys() & working["elements"].keys()):
        before = base["elements"][element_id]
        after = working["elements"][element_id]
        if (before["page_id"], before["parent_id"]) != (
            after["page_id"],
            after["parent_id"],
        ):
            moved_elements.append(
                {
                    "element_id": element_id,
                    "from_page_id": before["page_id"],
                    "from_parent_id": before["parent_id"],
                    "to_page_id": after["page_id"],
                    "to_parent_id": after["parent_id"],
                }
            )
        if before["child_count"] > 0 and after["child_count"] == 0:
            emptied_containers.append(
                {
                    "element_id": element_id,
                    "page_id": after["page_id"],
                    "parent_id": after["parent_id"],
                    "previous_child_count": before["child_count"],
                }
            )

    page_changes: list[dict[str, Any]] = []
    for page_id in sorted((base["pages"].keys() | working["pages"].keys()) - {"app"}):
        before = base["pages"].get(page_id, {"element_count": 0, "root_count": 0})
        after = working["pages"].get(page_id, {"element_count": 0, "root_count": 0})
        if before != after:
            page_changes.append(
                {
                    "page_id": page_id,
                    "element_count_before": before["element_count"],
                    "element_count_after": after["element_count"],
                    "element_count_delta": after["element_count"] - before["element_count"],
                    "root_count_before": before["root_count"],
                    "root_count_after": after["root_count"],
                    "root_count_delta": after["root_count"] - before["root_count"],
                }
            )

    app_before = base["pages"].get("app", {"element_count": 0, "root_count": 0})
    app_after = working["pages"].get("app", {"element_count": 0, "root_count": 0})
    return {
        "summary": {
            "moved_existing_elements": len(moved_elements),
            "emptied_existing_containers": len(emptied_containers),
            "pages_with_count_changes": len(page_changes),
        },
        "moved_elements": moved_elements,
        "emptied_containers": emptied_containers,
        "page_changes": page_changes,
        "app": {
            "element_count_before": app_before["element_count"],
            "element_count_after": app_after["element_count"],
            "root_count_before": app_before["root_count"],
            "root_count_after": app_after["root_count"],
        },
    }


def _snapshot(root: Path) -> dict[str, Any]:
    elements: dict[str, dict[str, Any]] = {}
    pages: dict[str, dict[str, int]] = {}

    app = read_app(root)
    app_roots = app.get("root_elements", []) if isinstance(app, dict) else []
    app_count = _collect_elements(
        app_roots,
        elements,
        page_id="app",
        parent_id="app",
    )
    pages["app"] = {
        "element_count": app_count,
        "root_count": len(app_roots) if isinstance(app_roots, list) else 0,
    }

    for page_ref in list_pages(root):
        if not isinstance(page_ref, dict):
            continue
        page = page_ref.get("details") or {}
        page_id = str(page_ref.get("id") or page.get("id") or "")
        if not page_id:
            continue
        page_elements = page.get("elements", []) if isinstance(page, dict) else []
        count = _collect_elements(
            page_elements,
            elements,
            page_id=page_id,
            parent_id=page_id,
        )
        pages[page_id] = {
            "element_count": count,
            "root_count": len(page_elements) if isinstance(page_elements, list) else 0,
        }

    return {"elements": elements, "pages": pages}


def _collect_elements(
    items: Any,
    target: dict[str, dict[str, Any]],
    *,
    page_id: str,
    parent_id: str,
) -> int:
    count = 0
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            continue
        children = item.get("children", [])
        child_count = len(children) if isinstance(children, list) else 0
        target[item_id] = {
            "page_id": page_id,
            "parent_id": parent_id,
            "child_count": child_count,
        }
        count += 1
        count += _collect_elements(
            children,
            target,
            page_id=page_id,
            parent_id=item_id,
        )
    return count
