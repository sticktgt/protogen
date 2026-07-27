from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_assessments import validate_requirement_assessments
from backend.modules.ui_schema.agent_generated_normalization import (
    normalize_generated_schema,
    stored_normalization_warnings,
)
from backend.modules.ui_schema.agent_preservation import preservation_validation
from backend.modules.ui_schema.agent_validation import validate_ui_schema
from backend.modules.ui_schema.files import read_json, write_json


def validate_agent_working_schema(run_path: Path) -> dict[str, Any]:
    normalization_warnings = normalize_generated_schema(run_path)
    requirements_data = read_json(
        run_path / "input" / "requirements.json", {"requirements": []}
    )
    validation = validate_ui_schema(
        run_path / "working" / "ui_schema",
        rebuild=True,
        requirements_data=requirements_data,
    )
    validation = preservation_validation(
        run_path / "base" / "ui_schema",
        run_path / "working" / "ui_schema",
        validation,
    )
    assessments = validate_requirement_assessments(
        run_path=run_path, requirements_data=requirements_data
    )
    validation["errors"] = [
        *validation.get("errors", []),
        *assessments.get("errors", []),
    ]
    validation["valid"] = not validation["errors"]
    validation["assessment_counts"] = assessments.get("counts", {})
    warnings = [
        *stored_normalization_warnings(run_path),
        *normalization_warnings,
        *validation.get("warnings", []),
        *assessments.get("warnings", []),
    ]
    validation["warnings"] = list(dict.fromkeys(str(item) for item in warnings if str(item)))
    return validation


def validate_and_mark_completion(run_path: Path) -> dict[str, Any]:
    validation = validate_agent_working_schema(run_path)
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
                "completed_by": "validate_ui_schema_state",
            },
        )
    else:
        (run_path / "result" / "agent_completion.json").unlink(missing_ok=True)
    return validation


def completion_ready(run_path: Path) -> bool:
    completion = read_json(run_path / "result" / "agent_completion.json", {})
    return bool(completion.get("finished") and completion.get("valid"))
