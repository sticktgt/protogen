from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_completion import validate_and_mark_completion
from backend.modules.ui_schema.agent_coverage_plan import require_coverage_plan
from backend.modules.ui_schema.agent_coverage_plan_diff import write_coverage_plan_diff
from backend.modules.ui_schema.agent_traceability import write_traceability_chunk


def write_traceability_with_optional_validation(
    *,
    run_path: Path,
    working_root: Path,
    result_root: Path,
    requirement_ui_links: dict[str, Any],
    agent_report: dict[str, Any],
    validate_after_write: bool,
) -> dict[str, Any]:
    """Write final/corrective traceability and run technical validation."""
    require_coverage_plan(run_path)
    result = write_traceability_chunk(
        run_path=run_path,
        working_root=working_root,
        result_root=result_root,
        requirement_ui_links=requirement_ui_links,
        agent_report=agent_report,
    )
    plan_diff = write_coverage_plan_diff(run_path)
    result["coverage_plan_changes"] = int(plan_diff.get("changed_count", 0))

    if not validate_after_write:
        return {
            **result,
            "completed": False,
            "next_action": "validate_ui_schema_state",
        }

    validation = validate_and_mark_completion(
        run_path,
        completed_by="write_ui_schema_traceability",
    )
    return {
        **result,
        **validation,
        "completed": bool(validation.get("valid")),
        "next_action": (
            "stop" if validation.get("valid") else "fix_errors_and_continue"
        ),
    }
