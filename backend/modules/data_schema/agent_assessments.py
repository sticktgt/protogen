from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.files import read_json

ASSESSMENT_GROUPS = ("cross_cutting_data", "no_data", "unclear")


def validate_requirement_assessments(
    *,
    run_path: Path,
    requirements_data: dict[str, Any],
    inherited_ids: set[str] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    requirement_ids = {
        str(item.get("id"))
        for item in requirements_data.get("requirements", [])
        if isinstance(item, dict) and item.get("id")
    }
    links_doc = read_json(
        run_path / "working" / "data_schema" / "mappings" / "requirement_data_links.json",
        {"links": []},
    )
    links_by_requirement: dict[str, list[dict[str, Any]]] = {}
    for link in links_doc.get("links", []):
        if not isinstance(link, dict):
            continue
        requirement_id = str(link.get("requirement_id") or "")
        if requirement_id:
            links_by_requirement.setdefault(requirement_id, []).append(link)

    report = read_json(run_path / "result" / "agent_report.json", {})
    assessed: dict[str, str] = {}
    counts = {
        "linked": 0,
        "cross_cutting_data": 0,
        "no_data": 0,
        "unclear": 0,
        "unclassified": 0,
    }
    for group in ASSESSMENT_GROUPS:
        records = report.get(group, []) if isinstance(report, dict) else []
        if not isinstance(records, list):
            errors.append(f"agent_report.json: {group} must be an array")
            continue
        for index, item in enumerate(records):
            if not isinstance(item, dict):
                errors.append(f"agent_report.json:{group}[{index}] must be an object")
                continue
            requirement_id = str(item.get("requirement_id") or "")
            if requirement_id not in requirement_ids:
                errors.append(f"agent_report.json:{group}[{index}] has unknown requirement_id {requirement_id}")
                continue
            if requirement_id in assessed:
                errors.append(f"Requirement {requirement_id} has multiple final assessments")
                continue
            if links_by_requirement.get(requirement_id):
                errors.append(
                    f"Requirement {requirement_id} has direct data links and must not be in {group}"
                )
            reason = str(item.get("reason") or "").strip()
            if group == "unclear" and not reason:
                errors.append(f"agent_report.json:{group}[{index}] reason is required")
            assessed[requirement_id] = group
            counts[group] += 1

    for requirement_id in sorted(requirement_ids):
        if links_by_requirement.get(requirement_id):
            if requirement_id not in assessed:
                counts["linked"] += 1
            continue
        if requirement_id not in assessed:
            counts["unclassified"] += 1
            errors.append(f"Requirement {requirement_id} has no data link or final assessment")

    allowed_link_ids = requirement_ids | set(inherited_ids or set())
    unknown_link_ids = sorted(set(links_by_requirement) - allowed_link_ids)
    if unknown_link_ids:
        errors.append("Requirement links contain unknown IDs: " + ", ".join(unknown_link_ids[:20]))
    return {"valid": not errors, "errors": errors, "warnings": warnings, "counts": counts}


def assessment_maps(report: dict[str, Any]) -> dict[str, dict[str, dict[str, str]]]:
    result: dict[str, dict[str, dict[str, str]]] = {}
    for group in ASSESSMENT_GROUPS:
        result[group] = {}
        records = report.get(group, []) if isinstance(report, dict) else []
        if not isinstance(records, list):
            continue
        for item in records:
            if isinstance(item, dict) and item.get("requirement_id"):
                result[group][str(item["requirement_id"])] = {
                    "reason": str(item.get("reason") or "")
                }
    return result
