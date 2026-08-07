from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_coverage_plan import schema_change_plan_context
from backend.modules.ui_schema.agent_target_catalog import build_target_catalog
from backend.modules.ui_schema.agent_requirement_scope import compact_requirements
from backend.modules.ui_schema.files import read_json, write_json

_RESULT_FILE = "coverage_plan_targets.json"


def build_coverage_plan_target_report(run_path: Path) -> dict[str, Any]:
    """Validate only technical target references selected by the model.

    Reuse/extend targets must already exist under the exact target type before
    schema mutation starts. Create targets may be absent. The backend does not
    decide whether the selected target is semantically suitable.
    """
    plan = schema_change_plan_context(run_path)
    catalog = build_target_catalog(run_path / "working" / "ui_schema")
    requirements = {
        str(item.get("id") or ""): item
        for item in compact_requirements(
            run_path, fields=["id", "name", "description", "acceptanceCriteria"]
        )
        if str(item.get("id") or "")
    }
    by_id: dict[str, list[dict[str, Any]]] = {}
    for (target_type, target_id), facts in catalog.items():
        by_id.setdefault(target_id, []).append(
            {
                "target_type": target_type,
                "target_id": target_id,
                **{key: value for key, value in facts.items() if key not in {"target_type", "target_id"}},
            }
        )

    gaps: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    checked = 0
    for item in plan.get("items", []):
        if not isinstance(item, dict):
            continue
        requirement_id = str(item.get("requirement_id") or "").strip()
        for target in item.get("targets", []) if isinstance(item.get("targets"), list) else []:
            if not isinstance(target, dict):
                continue
            action = str(target.get("action") or "").strip()
            target_type = str(target.get("target_type") or "").strip()
            target_id = str(target.get("target_id") or "").strip()
            if not target_type or not target_id:
                continue
            checked += 1
            exact = catalog.get((target_type, target_id))
            alternatives = by_id.get(target_id, [])
            if action in {"reuse", "extend"} and exact is None:
                gaps.append(
                    {
                        "requirement_id": requirement_id,
                        "target_type": target_type,
                        "target_id": target_id,
                        "planned_action": action,
                        "signal": (
                            "existing_target_type_mismatch"
                            if alternatives
                            else "planned_existing_target_missing"
                        ),
                        "available_targets_with_same_id": alternatives,
                        "requirement": requirements.get(requirement_id, {}),
                        "current_plan_item": dict(item),
                    }
                )
            elif action == "create" and exact is not None:
                observations.append(
                    {
                        "requirement_id": requirement_id,
                        "target_type": target_type,
                        "target_id": target_id,
                        "planned_action": action,
                        "signal": "planned_create_target_already_exists",
                        "target_facts": dict(exact),
                    }
                )

    payload = {
        "policy": {
            "validation_is_structural_only": True,
            "backend_does_not_choose_targets": True,
            "reuse_and_extend_require_existing_exact_target": True,
            "create_may_reference_a_new_target": True,
        },
        "checked_target_count": checked,
        "gap_count": len(gaps),
        "observation_count": len(observations),
        "gaps": gaps,
        "observations": observations,
        "complete": not gaps,
    }
    write_json(run_path / "result" / _RESULT_FILE, payload)
    return payload


def coverage_plan_target_errors(run_path: Path) -> list[str]:
    report = read_json(run_path / "result" / _RESULT_FILE, {})
    if not report:
        return [
            "Coverage plan target references are not validated: complete coverage review first"
        ]
    if bool(report.get("complete")):
        return []
    return [
        "Coverage plan contains reuse/extend targets that do not exist under the selected target_type; revise only the listed plan items before changing the schema"
    ]


def require_coverage_plan_targets_valid(run_path: Path) -> None:
    errors = coverage_plan_target_errors(run_path)
    if errors:
        raise ValueError(" | ".join(errors))
