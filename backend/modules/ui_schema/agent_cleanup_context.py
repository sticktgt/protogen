from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_changes import build_change_report
from backend.modules.ui_schema.agent_requirement_scope import compact_requirements
from backend.modules.ui_schema.storage import (
    list_pages,
    read_app,
    read_requirement_links,
    read_ui_links,
)


def build_cleanup_review_context(run_path: Path, *, max_bytes: int) -> dict[str, Any]:
    base_root = run_path / "base" / "ui_schema"
    working_root = run_path / "working" / "ui_schema"
    base_catalog = build_schema_catalog(base_root)
    context = {
        "review_policy": {
            "non_blocking": True,
            "manual_only": True,
            "current_requirements_may_be_partial": True,
            "absence_from_current_input_is_not_proof_of_obsolescence": True,
        },
        "requirements": compact_requirements(run_path),
        "base_objects": base_catalog["objects"],
        "allowed_targets": base_catalog["target_ids"],
        "candidate_changes": _compact_changes(build_change_report(base_root, working_root)),
        "working_requirement_links": read_requirement_links(working_root).get("links", []),
    }
    encoded = json.dumps(context, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > max_bytes:
        raise ValueError(
            f"Контекст ручной проверки слишком велик: {len(encoded)} байт при лимите {max_bytes}"
        )
    return context


def build_schema_catalog(schema_root: Path) -> dict[str, Any]:
    objects: list[dict[str, Any]] = []
    targets: list[str] = []

    app = read_app(schema_root)
    _collect_elements(
        app.get("root_elements", []),
        objects,
        targets,
        page_id=None,
        parent_id=None,
    )
    for page_ref in list_pages(schema_root):
        page = page_ref.get("details") or {}
        page_id = str(page_ref.get("id") or page.get("id") or "").strip()
        if not page_id:
            continue
        objects.append(
            {
                "target": f"page:{page_id}",
                "object_type": "page",
                "id": page_id,
                "title": page.get("title") or page_ref.get("title") or page_id,
                "description": page.get("description") or "",
            }
        )
        targets.append(f"page:{page_id}")
        _collect_elements(
            page.get("elements", []),
            objects,
            targets,
            page_id=page_id,
            parent_id=None,
        )

    for link in read_ui_links(schema_root).get("links", []):
        if not isinstance(link, dict):
            continue
        link_id = str(link.get("id") or "").strip()
        if not link_id:
            continue
        target = f"ui_link:{link_id}"
        objects.append(
            {
                "target": target,
                "object_type": "ui_link",
                "id": link_id,
                "source": f"{link.get('source_type')}:{link.get('source_id')}",
                "destination": f"{link.get('target_type')}:{link.get('target_id')}",
                "relation": link.get("relation") or "",
            }
        )
        targets.append(target)

    for link in read_requirement_links(schema_root).get("links", []):
        if not isinstance(link, dict):
            continue
        link_id = str(link.get("id") or "").strip()
        if not link_id:
            continue
        target = f"requirement_link:{link_id}"
        objects.append(
            {
                "target": target,
                "object_type": "requirement_link",
                "id": link_id,
                "requirement_id": link.get("requirement_id") or "",
                "destination": f"{link.get('target_type')}:{link.get('target_id')}",
                "relation": link.get("relation") or "",
            }
        )
        targets.append(target)

    return {"objects": objects, "target_ids": sorted(set(targets))}


def _collect_elements(
    elements: Any,
    objects: list[dict[str, Any]],
    targets: list[str],
    *,
    page_id: str | None,
    parent_id: str | None,
) -> None:
    for element in elements if isinstance(elements, list) else []:
        if not isinstance(element, dict):
            continue
        element_id = str(element.get("id") or "").strip()
        if not element_id:
            continue
        target = f"ui_element:{element_id}"
        objects.append(
            {
                "target": target,
                "object_type": "ui_element",
                "id": element_id,
                "page_id": page_id,
                "parent_id": parent_id,
                "type": element.get("type") or "",
                "label": element.get("label") or "",
                "description": element.get("description") or "",
            }
        )
        targets.append(target)
        _collect_elements(
            element.get("children", []),
            objects,
            targets,
            page_id=page_id,
            parent_id=element_id,
        )


def _compact_changes(changes: dict[str, Any]) -> dict[str, Any]:
    return {
        "statistics": changes.get("statistics", {}),
        "objects": [
            {
                key: item.get(key)
                for key in ("action", "object_type", "object_id", "title", "page_id")
                if item.get(key) not in (None, "")
            }
            for item in changes.get("changes", [])
            if isinstance(item, dict)
        ],
    }
