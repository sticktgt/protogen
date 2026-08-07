from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from backend.modules.ui_schema.agent_structural_element_candidates import (
    collect_element_candidates,
)
from backend.modules.ui_schema.agent_structural_link_candidates import (
    collect_link_candidates,
)
from backend.modules.ui_schema.agent_structural_page_candidates import (
    collect_page_candidates,
)
from backend.modules.ui_schema.files import read_json


def collect_structural_candidates(
    *,
    base_root: Path,
    working_root: Path,
    decisions: Iterable[dict[str, Any]],
    maximum_candidates: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Collect bounded, objective candidates for lightweight model review."""
    decision_items = list(decisions)
    base = _snapshot(base_root)
    working = _snapshot(working_root)
    new_ids = set(working["elements"]) - set(base["elements"])
    decisions_by_target = _decisions_by_target(decision_items)

    candidates = collect_element_candidates(
        base_elements=base["elements"],
        elements=working["elements"],
        new_ids=new_ids,
        decisions_by_target=decisions_by_target,
        extended_targets=_extended_targets(decision_items),
    )
    candidates.extend(
        collect_link_candidates(
            base_links=base["links"],
            working_links=working["links"],
            elements=working["elements"],
            decisions_by_target=decisions_by_target,
        )
    )
    candidates.extend(
        collect_page_candidates(
            base_documents=base["documents"],
            working_documents=working["documents"],
            working_elements=working["elements"],
            working_links=working["links"],
            decisions_by_target=decisions_by_target,
        )
    )

    priority = {
        "id_container_mismatch": 0,
        "self_navigation": 1,
        "multiple_navigation_targets": 2,
        "new_page_without_incoming_navigation": 3,
        "emptied_existing_container": 4,
        "empty_extended_container": 5,
        "duplicate_siblings": 6,
        "empty_new_container": 7,
        "duplicate_page_elements": 8,
    }
    candidates.sort(
        key=lambda item: (
            priority.get(item["kind"], 99),
            item["page_id"],
            item["candidate_id"],
        )
    )
    selected = candidates[:maximum_candidates]
    page_ids = sorted(
        {
            page_id
            for item in selected
            for page_id in (item.get("context_page_ids") or [item.get("page_id")])
            if page_id
        }
    )
    selected_link_ids = {
        link_id for item in selected for link_id in item.get("link_ids", [])
    }
    context = {
        "candidate_count": len(selected),
        "total_candidate_count": len(candidates),
        "truncated": len(candidates) > len(selected),
        "new_element_ids": sorted(new_ids),
        "documents": {
            page_id: working["documents"].get(page_id, {}) for page_id in page_ids
        },
        "ui_links": [
            link
            for link in working["links"]
            if str(link.get("id") or "") in selected_link_ids
        ],
    }
    return selected, context


def _snapshot(root: Path) -> dict[str, Any]:
    elements: dict[str, dict[str, Any]] = {}
    documents: dict[str, dict[str, Any]] = {}
    app = read_json(root / "app.json", {"root_elements": []})
    documents["app"] = app
    _collect_elements(
        app.get("root_elements", []),
        elements,
        page_id="app",
        parent_id="app",
    )
    pages_root = root / "pages"
    if pages_root.is_dir():
        for path in sorted(pages_root.glob("*.json")):
            page = read_json(path, {})
            page_id = str(page.get("id") or path.stem).strip()
            if not page_id:
                continue
            documents[page_id] = page
            _collect_elements(
                page.get("elements", []),
                elements,
                page_id=page_id,
                parent_id=page_id,
            )
    links_document = read_json(root / "links.json", {"links": []})
    links = links_document.get("links", []) if isinstance(links_document, dict) else []
    return {
        "elements": elements,
        "documents": documents,
        "links": links if isinstance(links, list) else [],
    }


def _collect_elements(
    items: Any,
    target: dict[str, dict[str, Any]],
    *,
    page_id: str,
    parent_id: str,
) -> list[str]:
    collected: list[str] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        element_id = str(item.get("id") or "").strip()
        if not element_id:
            continue
        children = item.get("children", [])
        child_items = children if isinstance(children, list) else []
        child_ids = _collect_elements(
            child_items,
            target,
            page_id=page_id,
            parent_id=element_id,
        )
        subtree_ids = [element_id, *child_ids]
        target[element_id] = {
            "page_id": page_id,
            "parent_id": parent_id,
            "type": str(item.get("type") or ""),
            "label": str(item.get("label") or ""),
            "child_count": len(child_items),
            "child_ids": [
                str(child.get("id") or "")
                for child in child_items
                if isinstance(child, dict) and str(child.get("id") or "")
            ],
            "subtree_ids": subtree_ids,
        }
        collected.extend(subtree_ids)
    return collected


def _decisions_by_target(
    decisions: Iterable[dict[str, Any]],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        requirement_id = str(decision.get("requirement_id") or "").strip()
        if not requirement_id:
            continue
        for target in decision.get("targets", []):
            if not isinstance(target, dict):
                continue
            target_id = str(target.get("target_id") or "").strip()
            if target_id:
                result.setdefault(target_id, []).append(requirement_id)
    return result


def _extended_targets(
    decisions: Iterable[dict[str, Any]],
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        requirement_id = str(decision.get("requirement_id") or "").strip()
        for target in decision.get("targets", []):
            if not isinstance(target, dict) or target.get("action") != "extend":
                continue
            target_id = str(target.get("target_id") or "").strip()
            if requirement_id and target_id:
                result.setdefault(target_id, set()).add(requirement_id)
    return result
