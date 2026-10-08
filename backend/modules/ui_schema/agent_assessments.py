from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.files import read_json
from backend.modules.ui_schema.storage import read_requirement_links

ASSESSMENT_GROUPS = ("cross_cutting_ui", "no_ui", "unclear")
CROSS_CUTTING_SCOPES = {"global", "targeted"}


def validate_requirement_assessments(
    *,
    run_path: Path,
    requirements_data: dict[str, Any],
) -> dict[str, Any]:
    """Validate factual consistency of requirement classification.

    This deliberately does not infer requirement semantics. The model decides
    whether a requirement is direct UI, cross-cutting UI, no-UI or unclear;
    Python only checks that the decision is complete and internally consistent.
    """
    errors: list[str] = []
    warnings: list[str] = []
    report = read_json(run_path / "result" / "agent_report.json", {})
    links = read_requirement_links(run_path / "working" / "ui_schema").get("links", [])

    requirement_ids = _requirement_ids(requirements_data)
    links_by_requirement = _links_by_requirement(links)
    groups = {
        name: _assessment_map(report.get(name), group=name, errors=errors)
        for name in ASSESSMENT_GROUPS
    }

    _validate_known_ids(groups, requirement_ids, errors)
    _validate_exclusive_groups(groups, errors)
    _validate_link_compatibility(groups, links_by_requirement, errors)

    classified = set().union(*(set(group) for group in groups.values()))
    direct_linked = set(links_by_requirement) - classified
    unclassified = requirement_ids - classified - direct_linked
    for requirement_id in sorted(unclassified):
        errors.append(
            f"Requirement {requirement_id} has no final UI assessment: create direct UI links "
            "or classify it as cross_cutting_ui, no_ui or unclear"
        )

    unknown_linked = set(links_by_requirement) - requirement_ids
    if unknown_linked:
        warnings.append(
            "Связи с требованиями содержат ID, отсутствующие в текущем входном файле: "
            + ", ".join(sorted(unknown_linked)[:20])
        )

    counts = {
        "linked": len(direct_linked & requirement_ids),
        "cross_cutting_ui": len(set(groups["cross_cutting_ui"]) & requirement_ids),
        "no_ui": len(set(groups["no_ui"]) & requirement_ids),
        "unclear": len(set(groups["unclear"]) & requirement_ids),
        "unclassified": len(unclassified),
    }
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": counts,
    }


def assessment_maps(report: dict[str, Any]) -> dict[str, dict[str, dict[str, str]]]:
    """Return normalized maps used by export/rendering code."""
    result: dict[str, dict[str, dict[str, str]]] = {}
    for group in ASSESSMENT_GROUPS:
        result[group] = _assessment_map(report.get(group), group=group, errors=[])
    return result


def _requirement_ids(requirements_data: dict[str, Any]) -> set[str]:
    items = requirements_data.get("requirements", [])
    if not isinstance(items, list):
        return set()
    return {
        item["id"]
        for item in items
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]
    }


def _links_by_requirement(value: Any) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(value, list):
        return result
    for link in value:
        if not isinstance(link, dict):
            continue
        requirement_id = link.get("requirement_id")
        if isinstance(requirement_id, str) and requirement_id:
            result.setdefault(requirement_id, []).append(link)
    return result


def _assessment_map(
    value: Any,
    *,
    group: str,
    errors: list[str],
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    if value is None:
        return result
    if not isinstance(value, list):
        errors.append(f"agent_report.{group} must be a list")
        return result
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"agent_report.{group}[{index}] must be an object")
            continue
        requirement_id = item.get("requirement_id")
        reason = item.get("reason")
        if not isinstance(requirement_id, str) or not requirement_id.strip():
            errors.append(f"agent_report.{group}[{index}] has no requirement_id")
            continue
        requirement_id = requirement_id.strip()
        if requirement_id in result:
            errors.append(f"Requirement {requirement_id} is duplicated in agent_report.{group}")
            continue
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"Requirement {requirement_id} in agent_report.{group} needs a reason")
        entry = {
            "requirement_id": requirement_id,
            "reason": str(reason or "").strip(),
        }
        if group == "cross_cutting_ui":
            scope = str(item.get("scope") or "global").strip()
            if scope not in CROSS_CUTTING_SCOPES:
                errors.append(
                    f"Requirement {requirement_id} has unsupported cross_cutting_ui scope: {scope}"
                )
            entry["scope"] = scope
        result[requirement_id] = entry
    return result


def _validate_known_ids(
    groups: dict[str, dict[str, dict[str, str]]],
    requirement_ids: set[str],
    errors: list[str],
) -> None:
    for group, items in groups.items():
        for requirement_id in sorted(set(items) - requirement_ids):
            errors.append(
                f"agent_report.{group} references an unknown requirement: {requirement_id}"
            )


def _validate_exclusive_groups(
    groups: dict[str, dict[str, dict[str, str]]],
    errors: list[str],
) -> None:
    memberships: dict[str, list[str]] = {}
    for group, items in groups.items():
        for requirement_id in items:
            memberships.setdefault(requirement_id, []).append(group)
    for requirement_id, names in sorted(memberships.items()):
        if len(names) > 1:
            errors.append(
                f"Requirement {requirement_id} has multiple final UI assessments: "
                + ", ".join(names)
            )


def _validate_link_compatibility(
    groups: dict[str, dict[str, dict[str, str]]],
    links_by_requirement: dict[str, list[dict[str, Any]]],
    errors: list[str],
) -> None:
    for group in ("no_ui", "unclear"):
        for requirement_id in sorted(groups[group]):
            if requirement_id in links_by_requirement:
                errors.append(
                    f"Requirement {requirement_id} is classified as {group} but also has UI links"
                )
    for requirement_id, assessment in sorted(groups["cross_cutting_ui"].items()):
        if assessment.get("scope") == "targeted" and requirement_id not in links_by_requirement:
            errors.append(
                f"Requirement {requirement_id} is cross_cutting_ui with targeted scope but has no UI links"
            )
