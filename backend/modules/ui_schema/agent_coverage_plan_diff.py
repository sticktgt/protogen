from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.files import read_json, write_json
from backend.modules.ui_schema.agent_traceability_items import read_traceability_items


def write_coverage_plan_diff(run_path: Path) -> dict[str, Any]:
    plan = read_json(run_path / "result" / "coverage_plan.json", {})
    final_items = read_traceability_items(run_path / "result")

    planned: dict[str, dict[str, Any]] = {}
    for item in plan.get("items", []) if isinstance(plan, dict) else []:
        if not isinstance(item, dict):
            continue
        requirement_id = str(item.get("requirement_id") or "").strip()
        if not requirement_id:
            continue
        planned[requirement_id] = {
            "classification": str(item.get("classification") or ""),
            "ui_effect": str(item.get("ui_effect") or ""),
            "targets": sorted(
                str(target.get("target_id") or "").strip()
                for target in item.get("targets", [])
                if isinstance(target, dict) and str(target.get("target_id") or "").strip()
            ),
        }

    final: dict[str, dict[str, Any]] = {}
    for requirement_id, item in final_items.items():
        final[requirement_id] = {
            "classification": str(item.get("classification") or ""),
            "ui_effect": str(item.get("ui_effect") or ""),
            "targets": sorted(
                str(target.get("target_id") or "").strip()
                for target in item.get("targets", [])
                if isinstance(target, dict) and str(target.get("target_id") or "").strip()
            ),
        }

    changes: list[dict[str, Any]] = []
    for requirement_id in sorted(set(planned) | set(final)):
        before = planned.get(requirement_id)
        after = final.get(requirement_id)
        if before != after:
            changes.append(
                {
                    "requirement_id": requirement_id,
                    "planned": before,
                    "final": after,
                }
            )
    payload = {
        "planned_count": len(planned),
        "final_count": len(final),
        "changed_count": len(changes),
        "changes": changes,
    }
    write_json(run_path / "result" / "coverage_plan_diff.json", payload)
    return payload
