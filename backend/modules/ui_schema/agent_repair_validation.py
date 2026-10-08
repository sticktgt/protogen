from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from backend.modules.ui_schema.agent_completion import validate_and_mark_completion
from backend.modules.ui_schema.files import read_json


def run_mutation_with_optional_revalidation(
    *,
    run_path: Path,
    operation: Callable[[], dict[str, Any]],
    enabled: bool,
    completed_by: str,
) -> dict[str, Any]:
    """Run a technical mutation and revalidate only when repairing a known invalid state."""
    pending_before_write = _has_pending_validation(run_path)
    result = operation()
    if not enabled or not pending_before_write or not bool(result.get("ok", True)):
        return result

    validation = validate_and_mark_completion(run_path, completed_by=completed_by)
    preserved_next_action = (
        str(result.get("next_action") or "")
        if result.get("preserve_next_action_after_validation")
        else ""
    )
    return {
        **result,
        "repair_validation": validation,
        "completed": bool(validation.get("valid")),
        "next_action": (
            "stop"
            if validation.get("valid")
            else preserved_next_action or "fix_errors_and_continue"
        ),
    }


def _has_pending_validation(run_path: Path) -> bool:
    validation = read_json(run_path / "result" / "validation_preview.json", {})
    return validation.get("valid") is False and bool(validation.get("errors"))
