from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_assessments import validate_requirement_assessments
from backend.modules.data_schema.agent_preservation import preservation_validation
from backend.modules.data_schema.agent_requirement_scope import (
    allowed_requirement_ids,
    inherited_requirement_ids,
)
from backend.modules.data_schema.agent_validation import validate_data_schema
from backend.modules.data_schema.files import read_json, write_json


def validate_agent_working_schema(run_path: Path) -> dict[str, Any]:
    requirements_data = read_json(run_path / "input" / "requirements.json", {"requirements": []})
    run = read_json(run_path / "run.json", {})
    domain = run.get("config", {}).get("domain", {}) if isinstance(run.get("config"), dict) else {}
    logical_types = _required_domain_values(domain, "logical_types")
    cardinalities = _required_domain_values(domain, "cardinalities")
    validation = validate_data_schema(
        run_path / "working" / "data_schema",
        rebuild=True,
        known_requirement_ids=allowed_requirement_ids(run_path),
        logical_types=logical_types,
        cardinalities=cardinalities,
    )
    validation = preservation_validation(
        run_path / "base" / "data_schema",
        run_path / "working" / "data_schema",
        validation,
    )
    assessments = validate_requirement_assessments(
        run_path=run_path,
        requirements_data=requirements_data,
        inherited_ids=inherited_requirement_ids(run_path),
    )
    validation["errors"] = [*validation.get("errors", []), *assessments.get("errors", [])]
    validation["warnings"] = [
        *validation.get("warnings", []),
        *assessments.get("warnings", []),
    ]
    validation["assessment_counts"] = assessments.get("counts", {})
    validation["valid"] = not validation["errors"]
    return validation




def validate_and_mark_completion(run_path: Path) -> dict[str, Any]:
    validation = validate_agent_working_schema(run_path)
    write_json(run_path / "result" / "validation_preview.json", validation)
    if validation.get("valid"):
        report = read_json(run_path / "result" / "agent_report.json", {})
        write_json(
            run_path / "result" / "agent_completion.json",
            {
                "finished": True,
                "valid": True,
                "errors": [],
                "warnings": validation.get("warnings", []),
                "agent_report_ready": isinstance(report, dict),
                "completed_by": "validate_data_schema_state",
            },
        )
    else:
        (run_path / "result" / "agent_completion.json").unlink(missing_ok=True)
    return validation


def _required_domain_values(domain: Any, name: str) -> list[str]:
    values = domain.get(name) if isinstance(domain, dict) else None
    if not isinstance(values, list) or not values or not all(isinstance(item, str) and item for item in values):
        raise ValueError(f"agent.domain.{name} must be configured as a non-empty string list")
    return values
