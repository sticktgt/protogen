from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.element_types import type_definition
from backend.modules.ui_schema.files import read_json
from backend.modules.ui_schema.storage import list_pages, read_app, read_requirement_links


def build_traceability_review_context(
    run_path: Path,
    *,
    max_target_children: int,
) -> dict[str, Any]:
    requirements = _requirements_by_id(run_path)
    report = read_json(run_path / "result" / "agent_report.json", {})
    links = read_requirement_links(run_path / "working" / "ui_schema").get("links", [])
    targets = _target_catalog(
        run_path / "working" / "ui_schema",
        max_target_children=max(0, int(max_target_children)),
    )

    assessments: dict[str, dict[str, Any]] = {}
    for group in ("no_ui", "cross_cutting_ui"):
        for item in report.get(group, []) if isinstance(report.get(group), list) else []:
            if not isinstance(item, dict):
                continue
            requirement_id = str(item.get("requirement_id") or "").strip()
            if requirement_id:
                assessments[requirement_id] = {
                    "classification": group,
                    "reason": str(item.get("reason") or "").strip(),
                    **(
                        {"scope": str(item.get("scope") or "global").strip()}
                        if group == "cross_cutting_ui"
                        else {}
                    ),
                }

    links_by_requirement: dict[str, list[dict[str, Any]]] = {}
    signals_by_requirement: dict[str, set[str]] = {}
    for source in links if isinstance(links, list) else []:
        if not isinstance(source, dict):
            continue
        requirement_id = str(source.get("requirement_id") or "").strip()
        if not requirement_id:
            continue
        target_type = str(source.get("target_type") or "").strip()
        target_id = str(source.get("target_id") or "").strip()
        target = targets.get((target_type, target_id))
        link = {
            key: source.get(key)
            for key in (
                "id",
                "target_type",
                "target_id",
                "relation",
                "implementation_status",
            )
            if source.get(key) not in (None, "")
        }
        link["target"] = target or {
            "id": target_id,
            "object_type": target_type,
            "missing": True,
        }
        links_by_requirement.setdefault(requirement_id, []).append(link)

        signals = signals_by_requirement.setdefault(requirement_id, set())
        if target_type == "page":
            signals.add("page_target")
        if source.get("implementation_status") == "implemented" and target:
            for signal in target.get("review_signals", []):
                signals.add(str(signal))

    candidate_ids = set(assessments)
    candidate_ids.update(
        requirement_id
        for requirement_id, signals in signals_by_requirement.items()
        if signals
    )

    candidates: list[dict[str, Any]] = []
    for requirement_id in sorted(candidate_ids):
        requirement = requirements.get(requirement_id, {"id": requirement_id})
        item: dict[str, Any] = {
            "requirement": requirement,
            "review_signals": sorted(signals_by_requirement.get(requirement_id, set())),
        }
        if requirement_id in assessments:
            item["assessment"] = assessments[requirement_id]
            item["review_signals"].append(
                f"classification:{assessments[requirement_id]['classification']}"
            )
        if requirement_id in links_by_requirement:
            item["links"] = links_by_requirement[requirement_id]
        candidates.append(item)

    return {
        "review_policy": {
            "semantic_decision_belongs_to_llm": True,
            "backend_only_selects_structural_review_candidates": True,
            "review_all_no_ui": True,
            "review_all_cross_cutting_ui": True,
            "review_page_targets": True,
            "review_implemented_shallow_containers": True,
        },
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def _requirements_by_id(run_path: Path) -> dict[str, dict[str, Any]]:
    data = read_json(
        run_path / "input" / "requirements.agent.json",
        read_json(run_path / "input" / "requirements.json", {"requirements": []}),
    )
    result: dict[str, dict[str, Any]] = {}
    for source in data.get("requirements", []) if isinstance(data, dict) else []:
        if not isinstance(source, dict):
            continue
        requirement_id = str(source.get("id") or "").strip()
        if not requirement_id:
            continue
        result[requirement_id] = {
            key: source.get(key)
            for key in ("id", "name", "description", "acceptanceCriteria")
            if source.get(key) not in (None, "", [])
        }
    return result


def _target_catalog(
    schema_root: Path,
    *,
    max_target_children: int,
) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    app = read_app(schema_root)
    _collect_elements(
        app.get("root_elements", []),
        result,
        page_id=None,
        parent_id=None,
        max_target_children=max_target_children,
    )
    for page_ref in list_pages(schema_root):
        page = page_ref.get("details") or {}
        page_id = str(page_ref.get("id") or page.get("id") or "").strip()
        if not page_id:
            continue
        elements = page.get("elements", []) if isinstance(page, dict) else []
        result[("page", page_id)] = {
            "object_type": "page",
            "id": page_id,
            "title": page.get("title") or page_ref.get("title") or page_id,
            "description": page.get("description") or "",
            "root_element_count": len(elements) if isinstance(elements, list) else 0,
            "element_count": _count_elements(elements),
            "review_signals": ["page_target"],
        }
        _collect_elements(
            elements,
            result,
            page_id=page_id,
            parent_id=None,
            max_target_children=max_target_children,
        )
    return result


def _collect_elements(
    items: Any,
    result: dict[tuple[str, str], dict[str, Any]],
    *,
    page_id: str | None,
    parent_id: str | None,
    max_target_children: int,
) -> None:
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        element_id = str(item.get("id") or "").strip()
        if not element_id:
            continue
        children = item.get("children", []) if isinstance(item.get("children"), list) else []
        definition = type_definition(str(item.get("type") or "")) or {}
        child_summaries = [
            {
                key: child.get(key)
                for key in ("id", "type", "label")
                if child.get(key) not in (None, "")
            }
            for child in children[:max_target_children]
            if isinstance(child, dict)
        ]
        signals: list[str] = []
        if definition.get("kind") == "group" and not children:
            signals.append("implemented_empty_container")
        elif definition.get("kind") == "group" and len(children) == 1:
            child_definition = type_definition(str(children[0].get("type") or "")) or {}
            if child_definition.get("kind") == "atomic":
                signals.append("implemented_shallow_container")
        result[("ui_element", element_id)] = {
            "object_type": "ui_element",
            "id": element_id,
            "page_id": page_id,
            "parent_id": parent_id,
            "type": item.get("type") or "",
            "kind": definition.get("kind") or "",
            "label": item.get("label") or "",
            "description": item.get("description") or "",
            "purpose": item.get("purpose") or "",
            "direct_child_count": len(children),
            "children": child_summaries,
            "children_truncated": max(0, len(children) - len(child_summaries)),
            "review_signals": signals,
        }
        _collect_elements(
            children,
            result,
            page_id=page_id,
            parent_id=element_id,
            max_target_children=max_target_children,
        )


def _count_elements(items: Any) -> int:
    total = 0
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        total += 1 + _count_elements(item.get("children", []))
    return total
