from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_assessments import validate_requirement_assessments
from backend.modules.ui_schema.agent_preservation import preservation_validation
from backend.modules.ui_schema.agent_object_cleanup import approved_deletions
from backend.modules.ui_schema.agent_repair_hints import build_repair_hints
from backend.modules.ui_schema.agent_validation import validate_ui_schema
from backend.modules.ui_schema.agent_validation_history import record_validation_attempt
from backend.modules.ui_schema.files import read_json, write_json


def validate_agent_working_schema(run_path: Path) -> dict[str, Any]:
    requirements_data = read_json(
        run_path / "input" / "requirements.json", {"requirements": []}
    )
    validation = validate_ui_schema(
        run_path / "working" / "ui_schema",
        rebuild=True,
        requirements_data=requirements_data,
    )
    approved_pages, approved_elements = approved_deletions(run_path)
    validation = preservation_validation(
        run_path / "base" / "ui_schema",
        run_path / "working" / "ui_schema",
        validation,
        approved_page_ids=approved_pages,
        approved_element_ids=approved_elements,
    )
    pipeline_state = read_json(run_path / "result" / "pipeline_state.json", {})
    pipeline_finished = pipeline_state.get("version") == 2 and pipeline_state.get(
        "status"
    ) in {"generated", "completed"}
    if pipeline_finished:
        assessments = validate_requirement_assessments(
            run_path=run_path, requirements_data=requirements_data
        )
        workflow_errors: list[str] = []
    else:
        assessments = {
            "errors": [],
            "warnings": [],
            "counts": {
                "linked": 0,
                "cross_cutting_ui": 0,
                "no_ui": 0,
                "unclear": 0,
                "unclassified": 0,
            },
        }
        workflow_errors = [
            "Управляемая синхронизация UI-схемы не завершена; текущий этап: "
            + str(pipeline_state.get("phase") or "unknown")
        ]
    validation["errors"] = [
        *validation.get("errors", []),
        *assessments.get("errors", []),
        *workflow_errors,
    ]
    validation["valid"] = not validation["errors"]
    validation["assessment_counts"] = assessments.get("counts", {})
    warnings = [
        *validation.get("warnings", []),
        *assessments.get("warnings", []),
    ]
    validation["warnings"] = list(dict.fromkeys(str(item) for item in warnings if str(item)))
    validation["repair_hints"] = build_repair_hints(run_path) if validation["errors"] else []
    return validation


def validate_and_mark_completion(
    run_path: Path,
    *,
    completed_by: str = "validate_ui_schema_state",
) -> dict[str, Any]:
    validation = validate_agent_working_schema(run_path)
    record_validation_attempt(run_path, validation, source="agent_tool")
    write_json(run_path / "result" / "validation_preview.json", validation)
    if validation.get("valid"):
        report = read_json(run_path / "result" / "agent_report.json", {})
        report_ready = isinstance(report, dict)
        write_json(
            run_path / "result" / "agent_completion.json",
            {
                "finished": True,
                "valid": True,
                "errors": [],
                "warnings": validation.get("warnings", []),
                "agent_report_ready": report_ready,
                "completed_by": completed_by,
            },
        )
    else:
        (run_path / "result" / "agent_completion.json").unlink(missing_ok=True)
    return validation


def completion_ready(run_path: Path) -> bool:
    completion = read_json(run_path / "result" / "agent_completion.json", {})
    return bool(completion.get("finished") and completion.get("valid"))
