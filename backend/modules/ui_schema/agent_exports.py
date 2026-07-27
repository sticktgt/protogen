from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable

from backend.modules.ui_schema.agent_assessments import assessment_maps
from backend.modules.ui_schema.files import read_json
from backend.modules.ui_schema.storage import list_pages, read_app, read_requirement_links


def build_requirements_ui_result(
    *,
    requirements_file: Path,
    ui_schema_root: Path,
    agent_report_file: Path,
    run: dict[str, Any],
) -> dict[str, Any]:
    requirements_data = read_json(requirements_file, {"requirements": []})
    requirements = requirements_data.get("requirements", [])
    if not isinstance(requirements, list):
        requirements = []

    links_by_requirement: dict[str, list[dict[str, Any]]] = {}
    for link in read_requirement_links(ui_schema_root).get("links", []):
        if isinstance(link, dict) and isinstance(link.get("requirement_id"), str):
            links_by_requirement.setdefault(link["requirement_id"], []).append(link)

    report = read_json(agent_report_file, {})
    assessments = assessment_maps(report)
    page_titles, elements = _ui_target_catalog(ui_schema_root)

    records: list[dict[str, Any]] = []
    counts = {
        "linked": 0,
        "cross_cutting_ui": 0,
        "no_ui": 0,
        "unclear": 0,
        "unclassified": 0,
    }
    for requirement in requirements:
        if not isinstance(requirement, dict) or not isinstance(requirement.get("id"), str):
            continue
        requirement_id = requirement["id"]
        targets = [
            _enrich_target(link, page_titles=page_titles, elements=elements)
            for link in links_by_requirement.get(requirement_id, [])
        ]
        result, comment, scope = _assessment(requirement_id, targets, assessments)
        counts[result] += 1
        records.append(
            {
                "requirement": requirement,
                "ui_result": result,
                "ui_targets": targets,
                "comment": comment,
                "scope": scope,
            }
        )

    traceability = _traceability(records)
    return {
        "format_version": "0.2",
        "run_id": run["run_id"],
        "workspace_id": run["workspace_id"],
        "requirements_source": {
            "file_name": run.get("requirements_file_name", requirements_file.name),
            "workspace_path": run.get("requirements_source_path"),
            "sha256": hashlib.sha256(requirements_file.read_bytes()).hexdigest(),
            "requirements_count": len(records),
        },
        "ui_schema": {
            "schema_version": read_json(ui_schema_root / "schema.json", {}).get(
                "schema_version", "0.1"
            )
        },
        "assessment_counts": counts,
        "assessment_details": _assessment_details(records),
        "traceability": traceability,
        "traceability_warnings": _traceability_warnings(traceability),
        "requirements": records,
    }


def _assessment(
    requirement_id: str,
    targets: list[dict[str, Any]],
    assessments: dict[str, dict[str, dict[str, str]]],
) -> tuple[str, str | None, str | None]:
    cross_cutting = assessments["cross_cutting_ui"].get(requirement_id)
    if cross_cutting:
        return (
            "cross_cutting_ui",
            cross_cutting.get("reason") or None,
            cross_cutting.get("scope") or "global",
        )
    no_ui = assessments["no_ui"].get(requirement_id)
    if no_ui:
        return "no_ui", no_ui.get("reason") or None, None
    unclear = assessments["unclear"].get(requirement_id)
    if unclear:
        return "unclear", unclear.get("reason") or None, None
    if targets:
        return "linked", None, None
    return "unclassified", "Агент не создал связь и не указал итоговую классификацию.", None


def _ui_target_catalog(root: Path) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    page_titles: dict[str, str] = {}
    elements: dict[str, dict[str, Any]] = {}
    _catalog_elements(read_app(root).get("root_elements", []), elements, page_id=None)
    for page_ref in list_pages(root):
        page = page_ref.get("details") or {}
        page_id = page_ref.get("id") or page.get("id")
        if page_id:
            page_titles[page_id] = page.get("title") or page_ref.get("title") or page_id
            _catalog_elements(page.get("elements", []), elements, page_id=page_id)
    return page_titles, elements


def _catalog_elements(
    elements_list: Iterable[Any],
    target: dict[str, dict[str, Any]],
    *,
    page_id: str | None,
) -> None:
    for element in elements_list or []:
        if not isinstance(element, dict) or not isinstance(element.get("id"), str):
            continue
        target[element["id"]] = {
            "label": element.get("label") or element["id"],
            "element_type": element.get("type"),
            "page_id": page_id,
        }
        _catalog_elements(element.get("children", []), target, page_id=page_id)


def _enrich_target(
    link: dict[str, Any],
    *,
    page_titles: dict[str, str],
    elements: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    target_type, target_id = link.get("target_type"), link.get("target_id")
    result = {
        "target_type": target_type,
        "target_id": target_id,
        "relation": link.get("relation", "implemented_by"),
        "implementation_status": link.get("implementation_status", "planned"),
    }
    if target_type == "page":
        result["title"] = page_titles.get(str(target_id), str(target_id))
    elif target_type == "ui_element":
        result.update(elements.get(str(target_id), {}))
    return result


def _traceability(records: list[dict[str, Any]]) -> dict[str, Any]:
    with_targets = [record for record in records if record.get("ui_targets")]
    direct = [record for record in records if record.get("ui_result") == "linked"]
    cross_cutting = [
        record for record in records if record.get("ui_result") == "cross_cutting_ui"
    ]
    target_counts = [len(record.get("ui_targets") or []) for record in with_targets]
    page_only = 0
    with_elements = 0
    multiple = 0
    for record in with_targets:
        targets = record.get("ui_targets") or []
        if targets and all(target.get("target_type") == "page" for target in targets):
            page_only += 1
        if any(target.get("target_type") == "ui_element" for target in targets):
            with_elements += 1
        if len(targets) > 1:
            multiple += 1
    total_links = sum(target_counts)
    average = round(total_links / len(with_targets), 2) if with_targets else 0.0
    return {
        "requirements_total": len(records),
        "requirements_linked": len(direct),
        "requirements_cross_cutting_ui": len(cross_cutting),
        "cross_cutting_with_targets": sum(1 for record in cross_cutting if record.get("ui_targets")),
        "requirements_with_targets": len(with_targets),
        "links_total": total_links,
        "requirements_page_only": page_only,
        "requirements_with_elements": with_elements,
        "requirements_multi_target": multiple,
        "average_targets_per_traced_requirement": average,
        # Compatibility for old frontend/export consumers.
        "average_targets_per_linked_requirement": average,
    }


def _traceability_warnings(traceability: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    traced = int(traceability.get("requirements_with_targets") or 0)
    multi = int(traceability.get("requirements_multi_target") or 0)
    page_only = int(traceability.get("requirements_page_only") or 0)
    average = float(traceability.get("average_targets_per_traced_requirement") or 0)
    if traced >= 10 and multi == 0:
        warnings.append(
            "Все трассируемые требования имеют ровно одну цель. Проверьте детализацию many-to-many трассировки."
        )
    if traced >= 10 and average <= 1.05:
        warnings.append(
            "Среднее число UI-целей на трассируемое требование близко к одному; комплексные требования могут быть связаны слишком укрупнённо."
        )
    if traced and page_only / traced >= 0.25:
        warnings.append(
            "Значительная часть требований связана только со страницами, без конечных UI-элементов."
        )
    return warnings


def _assessment_details(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result = {
        "cross_cutting_ui": [],
        "no_ui": [],
        "unclear": [],
        "unclassified": [],
    }
    for record in records:
        status = record.get("ui_result")
        if status not in result:
            continue
        requirement = record.get("requirement") or {}
        result[status].append(
            {
                "requirement_id": requirement.get("id"),
                "name": requirement.get("name") or requirement.get("title") or "",
                "reason": record.get("comment") or "",
                "scope": record.get("scope"),
                "targets_count": len(record.get("ui_targets") or []),
            }
        )
    return result
