from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_schema_io import write_requirement_links
from backend.modules.data_schema.files import read_json, write_json
from backend.modules.data_schema.agent_target_references import materialize_traceability_update


def write_complete_requirement_results(
    *,
    run_path: Path,
    updates: list[dict[str, Any]],
    agent_note: str | None,
    warnings: list[str] | None,
) -> dict[str, Any]:
    """Write one complete LLM-selected result for every input requirement.

    Completeness is a technical contract only: backend compares exact requirement IDs
    and materializes the targets and classifications selected by the model unchanged.
    """

    requirements = read_json(run_path / "input" / "requirements.json", {})
    expected_ids = [
        str(item.get("id") or "").strip()
        for item in requirements.get("requirements", [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    expected = set(expected_ids)
    actual_ids = [str(item.get("requirement_id") or "").strip() for item in updates]
    actual = set(actual_ids)

    if len(actual_ids) != len(actual):
        raise ValueError("Complete traceability write contains duplicate requirement_id values")
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown or len(actual_ids) != len(expected_ids):
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing[:20]))
        if unknown:
            details.append("unknown=" + ",".join(unknown[:20]))
        raise ValueError(
            "Complete traceability write must contain every input requirement exactly once"
            + (": " + "; ".join(details) if details else "")
        )

    return patch_requirement_results(
        working_root=run_path / "working" / "data_schema",
        result_root=run_path / "result",
        updates=updates,
        agent_note=agent_note,
        warnings=warnings,
    )


def patch_requirement_results(
    *,
    working_root: Path,
    result_root: Path,
    updates: list[dict[str, Any]],
    agent_note: str | None,
    warnings: list[str] | None,
) -> dict[str, Any]:
    """Apply complete LLM-selected results for explicit requirement IDs.

    This function performs no semantic resolution. It materializes only the exact
    structured targets supplied by the model, then updates links and assessments
    for the same requirement IDs.
    """

    materialized = [
        materialize_traceability_update(
            working_root=working_root,
            payload={
                "requirement_id": item["requirement_id"],
                "links": item.get("links", []),
            },
        )
        for item in updates
    ]
    link_result = patch_requirement_links(
        working_root=working_root,
        updates=materialized,
    )
    assessment_result = patch_requirement_assessments(
        result_root=result_root,
        updates=[
            {
                "requirement_id": item["requirement_id"],
                "classification": item["classification"],
                "reason": item.get("reason", ""),
                "warnings": item.get("warnings", []),
            }
            for item in updates
        ],
        agent_note=agent_note,
        warnings=warnings,
    )
    return {
        "patched_requirement_count": len(updates),
        "requirement_link_count": link_result.get("requirement_link_count", 0),
        "covered_requirement_count": link_result.get("covered_requirement_count", 0),
        "assessment_count": assessment_result.get("assessment_count", 0),
    }


def patch_requirement_links(
    *,
    working_root: Path,
    updates: list[dict[str, Any]],
) -> dict[str, Any]:
    path = working_root / "mappings" / "requirement_data_links.json"
    current = read_json(path, {"links": []})
    touched = {
        str(item.get("requirement_id") or "").strip()
        for item in updates
        if isinstance(item, dict)
    }
    if "" in touched:
        raise ValueError("Each traceability update requires requirement_id")
    combined = [
        item for item in current.get("links", [])
        if isinstance(item, dict) and str(item.get("requirement_id") or "") not in touched
    ]
    for update in updates:
        requirement_id = str(update.get("requirement_id") or "").strip()
        links = update.get("links", [])
        if not isinstance(links, list):
            raise ValueError(f"Traceability links for {requirement_id} must be an array")
        for link in links:
            if not isinstance(link, dict):
                raise ValueError(f"Each traceability link for {requirement_id} must be an object")
            combined.append({"requirement_id": requirement_id, **link})
    result = write_requirement_links(working_root=working_root, links=combined)
    return {
        **result,
        "patched_requirement_count": len(touched),
    }


def patch_requirement_assessments(
    *,
    result_root: Path,
    updates: list[dict[str, Any]],
    agent_note: str | None,
    warnings: list[str] | None,
) -> dict[str, Any]:
    path = result_root / "agent_report.json"
    report = read_json(
        path,
        {
            "summary": "",
            "agent_note": "",
            "cross_cutting_data": [],
            "no_data": [],
            "unclear": [],
            "warnings": [],
            "requirement_warnings": [],
        },
    )
    touched = {
        str(item.get("requirement_id") or "").strip()
        for item in updates
        if isinstance(item, dict)
    }
    if "" in touched:
        raise ValueError("Each assessment update requires requirement_id")
    categories = ("cross_cutting_data", "no_data", "unclear")
    for category in categories:
        report[category] = [
            item for item in report.get(category, [])
            if isinstance(item, dict) and str(item.get("requirement_id") or "") not in touched
        ]
    existing_requirement_warnings = report.get("requirement_warnings", [])
    if not isinstance(existing_requirement_warnings, list):
        existing_requirement_warnings = []
    report["requirement_warnings"] = [
        item
        for item in existing_requirement_warnings
        if isinstance(item, dict)
        and str(item.get("requirement_id") or "") not in touched
    ]
    for update in updates:
        requirement_id = str(update.get("requirement_id") or "").strip()
        classification = str(update.get("classification") or "").strip()
        if classification != "direct":
            if classification not in categories:
                raise ValueError(f"Unsupported requirement assessment: {classification}")
            reason = str(update.get("reason") or "").strip()
            if classification == "unclear" and not reason:
                raise ValueError(f"Assessment reason is required for {requirement_id}")
            report[classification].append(
                {"requirement_id": requirement_id, "reason": reason}
            )
        messages = [
            str(item).strip()
            for item in update.get("warnings", [])
            if str(item).strip()
        ]
        if messages:
            report["requirement_warnings"].append(
                {"requirement_id": requirement_id, "messages": messages}
            )
    if agent_note is not None:
        report["agent_note"] = str(agent_note)
    if warnings is not None:
        report["warnings"] = [str(item) for item in warnings]
    report.setdefault("summary", "")
    write_json(path, report)
    return {
        "patched_requirement_count": len(touched),
        "assessment_count": sum(len(report.get(key, [])) for key in categories),
    }
