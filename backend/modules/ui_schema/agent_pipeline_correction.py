from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from backend.modules.ui_schema.agent_pipeline_context import common_context, fixed_batches
from backend.modules.ui_schema.agent_pipeline_models import (
    PipelineAuditIssue,
    PipelineCorrectionOutput,
    PipelineDecision,
)
from backend.modules.ui_schema.agent_pipeline_runtime import PipelineRuntime
from backend.modules.ui_schema.agent_pipeline_validation import validate_plan_decisions
from backend.modules.ui_schema.agent_pipeline_values import join_notes, unique_strings
from backend.modules.ui_schema.files import write_json


def run_correction_batches(
    *,
    runtime: PipelineRuntime,
    requirements: list[dict[str, Any]],
    decisions: list[PipelineDecision],
    audit_issues: list[PipelineAuditIssue],
    technical_errors: list[str],
    required_ids: set[str],
    batch_size: int,
    maximum_apply_repairs: int,
) -> tuple[list[PipelineDecision], list[str], list[str], int]:
    requirement_by_id = {str(item.get("id") or ""): item for item in requirements}
    merged = {item.requirement_id: item for item in decisions}
    issue_by_id = {item.requirement_id: item for item in audit_issues}
    ordered_ids = [
        str(item.get("id") or "")
        for item in requirements
        if str(item.get("id") or "") in required_ids
    ]
    batches = fixed_batches(ordered_ids, batch_size)
    notes: list[str] = []
    warnings: list[str] = []
    saved_batches: list[dict[str, Any]] = []
    for index, batch_ids in enumerate(batches, start=1):
        runtime.ensure_not_cancelled()
        batch_id_set = set(batch_ids)
        relevant_technical = [
            error
            for error in technical_errors
            if str(error).split(":", 1)[0].strip() in batch_id_set
        ]
        correction = _invoke_with_apply_repair(
            runtime=runtime,
            base_context={
                **common_context(runtime.run_path, include_schema=True),
                "batch": {"index": index, "total": len(batches)},
                "requirements": [requirement_by_id[item] for item in batch_ids],
                "current_decisions": [merged[item].model_dump() for item in batch_ids],
                "audit_issues": [
                    issue_by_id[item].model_dump()
                    for item in batch_ids
                    if item in issue_by_id
                ],
                "technical_errors": relevant_technical,
                "required_requirement_ids": batch_ids,
            },
            required_ids=batch_id_set,
            maximum_repairs=maximum_apply_repairs,
        )
        for item in correction.decisions:
            merged[item.requirement_id] = item
        notes.append(correction.agent_note)
        warnings.extend(correction.warnings)
        saved_batches.append(
            {
                "index": index,
                "requirement_ids": batch_ids,
                "output": correction.model_dump(),
            }
        )
        write_json(
            runtime.run_path / "result" / "correction.json",
            {
                "completed_batches": index,
                "total_batches": len(batches),
                "batches": saved_batches,
                "agent_note": join_notes(notes),
                "warnings": unique_strings(warnings),
            },
        )
    ordered = [merged[str(item.get("id") or "")] for item in requirements]
    return ordered, notes, warnings, len(batches)


def issue_requirement_ids(
    audit_issues: Iterable[PipelineAuditIssue],
    technical_errors: Iterable[str],
) -> set[str]:
    result = {item.requirement_id for item in audit_issues}
    result.update(technical_issue_ids(technical_errors))
    return result


def technical_issue_ids(errors: Iterable[str]) -> set[str]:
    result: set[str] = set()
    for error in errors:
        prefix = str(error).split(":", 1)[0].strip()
        if prefix:
            result.add(prefix)
    return result


def validate_correction_output(
    output: PipelineCorrectionOutput,
    required_ids: set[str],
    *,
    schema_root: Path,
) -> list[str]:
    return validate_plan_decisions(
        output.decisions,
        expected_requirement_ids=sorted(required_ids),
        schema_root=schema_root,
        validate_actions=True,
    )


def _invoke_with_apply_repair(
    *,
    runtime: PipelineRuntime,
    base_context: dict[str, Any],
    required_ids: set[str],
    maximum_repairs: int,
) -> PipelineCorrectionOutput:
    correction: PipelineCorrectionOutput | None = None
    apply_errors: list[str] = []
    for repair_index in range(maximum_repairs + 1):
        correction = runtime.invoke_validated(
            output_model=PipelineCorrectionOutput,
            stage="correction",
            base_context={
                **base_context,
                "correction_apply_errors": apply_errors,
                "rejected_correction": correction.model_dump() if correction else None,
            },
            validator=lambda value: validate_correction_output(
                value,
                required_ids,
                schema_root=runtime.run_path / "working" / "ui_schema",
            ),
        )
        try:
            runtime.apply_changes(correction.changes)
            return correction
        except (OSError, TypeError, ValueError) as exc:
            apply_errors = [str(exc)]
            if repair_index >= maximum_repairs:
                raise
            runtime.event(
                event_type="pipeline_correction_apply_rejected",
                level="warning",
                message=f"Точечный пакет отклонён: {str(exc)[:600]}",
                data={"repair_attempt": repair_index + 1},
            )
    raise RuntimeError("Correction stage produced no result")
