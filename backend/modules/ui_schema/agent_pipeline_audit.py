from __future__ import annotations

from typing import Any

from backend.modules.ui_schema.agent_pipeline_context import audit_context, fixed_batches
from backend.modules.ui_schema.agent_pipeline_models import (
    PipelineAuditIssue,
    PipelineAuditOutput,
    PipelineDecision,
)
from backend.modules.ui_schema.agent_pipeline_runtime import PipelineRuntime
from backend.modules.ui_schema.agent_pipeline_values import unique_strings
from backend.modules.ui_schema.files import write_json


def run_audit_batches(
    *,
    runtime: PipelineRuntime,
    requirements: list[dict[str, Any]],
    decisions: list[PipelineDecision],
    batch_size: int,
    result_file_name: str = "audit.json",
    context_overrides: dict[str, Any] | None = None,
) -> tuple[list[PipelineAuditIssue], list[str], int]:
    issues: list[PipelineAuditIssue] = []
    warnings: list[str] = []
    decisions_by_id = {item.requirement_id: item for item in decisions}
    audit_requirements = [
        item
        for item in requirements
        if (
            (decision := decisions_by_id.get(str(item.get("id") or ""))) is not None
            and decision.classification == "direct_ui"
        )
    ]
    batches = fixed_batches(audit_requirements, batch_size)
    if not batches:
        write_json(
            runtime.run_path / "result" / result_file_name,
            {
                "completed_batches": 0,
                "total_batches": 0,
                "issues": [],
                "warnings": [],
            },
        )
        return [], [], 0
    for index, requirement_batch in enumerate(batches, start=1):
        runtime.ensure_not_cancelled()
        batch_ids = [str(item.get("id") or "") for item in requirement_batch]
        decision_batch = [decisions_by_id[item] for item in batch_ids]
        context = {
            **audit_context(
                run_path=runtime.run_path,
                requirements=requirement_batch,
                decisions=[item.model_dump() for item in decision_batch],
            ),
            "batch": {"index": index, "total": len(batches)},
        }
        if context_overrides:
            context.update(context_overrides)
        audit = runtime.invoke_validated(
            output_model=PipelineAuditOutput,
            stage="audit",
            base_context=context,
            validator=lambda value, ids=batch_ids: validate_audit_output(value, ids),
        )
        issues.extend(audit.issues)
        warnings.extend(audit.warnings)
        write_json(
            runtime.run_path / "result" / result_file_name,
            {
                "completed_batches": index,
                "total_batches": len(batches),
                "issues": [item.model_dump() for item in issues],
                "warnings": unique_strings(warnings),
            },
        )
    return issues, warnings, len(batches)


def validate_audit_output(
    output: PipelineAuditOutput,
    batch_ids: list[str],
) -> list[str]:
    allowed = set(batch_ids)
    errors: list[str] = []
    seen: set[str] = set()
    for issue in output.issues:
        requirement_id = issue.requirement_id
        if requirement_id not in allowed:
            errors.append(f"audit issue outside current batch: {requirement_id}")
        if requirement_id in seen:
            errors.append(f"duplicate audit issue: {requirement_id}")
        seen.add(requirement_id)
    return errors
