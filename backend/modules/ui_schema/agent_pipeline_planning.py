from __future__ import annotations

from typing import Any

from backend.modules.ui_schema.agent_change_preflight import (
    ChangePreflightError,
    validate_plan_preflight,
)
from backend.modules.ui_schema.agent_pipeline_context import common_context, fixed_batches
from backend.modules.ui_schema.agent_pipeline_models import (
    PipelineDecision,
    PipelinePlanOutput,
    RequirementAnalysisItem,
)
from backend.modules.ui_schema.agent_pipeline_repair_context import (
    build_planning_repair_context,
)
from backend.modules.ui_schema.agent_pipeline_runtime import PipelineRuntime
from backend.modules.ui_schema.agent_pipeline_validation import validate_plan_decisions
from backend.modules.ui_schema.agent_pipeline_values import join_notes, unique_strings
from backend.modules.ui_schema.agent_target_catalog import build_technical_index
from backend.modules.ui_schema.files import read_json, write_json


def run_planning_batches(
    *,
    runtime: PipelineRuntime,
    requirements: list[dict[str, Any]],
    analyses: list[RequirementAnalysisItem],
    batch_size: int,
    maximum_repairs: int,
) -> tuple[list[PipelineDecision], list[str], list[str], int]:
    runtime.phase(
        "planning",
        "Проектирование и применение управляемых пакетов изменений",
    )
    analysis_by_id = {item.requirement_id: item for item in analyses}
    compact_global_analysis = _compact_global_analysis(analyses)
    decisions: list[PipelineDecision] = []
    warnings: list[str] = []
    notes: list[str] = []
    saved_batches: list[dict[str, Any]] = []
    batches = fixed_batches(requirements, batch_size)
    for index, requirement_batch in enumerate(batches, start=1):
        runtime.ensure_not_cancelled()
        expected_ids = [str(item.get("id") or "") for item in requirement_batch]
        batch_analysis = [analysis_by_id[item] for item in expected_ids]
        context = {
            **common_context(runtime.run_path, include_schema=True),
            "batch": {
                "index": index,
                "total": len(batches),
                "requirements": requirement_batch,
                "analysis": [item.model_dump() for item in batch_analysis],
            },
            "all_requirement_analysis": compact_global_analysis,
            "technical_index": build_technical_index(
                runtime.run_path / "working" / "ui_schema"
            ),
            "already_completed_requirement_ids": [
                item.requirement_id for item in decisions
            ],
        }
        plan = runtime.invoke_validated(
            output_model=PipelinePlanOutput,
            stage="planning",
            base_context=context,
            validator=lambda value, ids=expected_ids: validate_plan_decisions(
                value.decisions,
                expected_requirement_ids=ids,
                schema_root=runtime.run_path / "working" / "ui_schema",
                validate_actions=False,
            ),
        )
        plan = _apply_plan_with_repair(
            runtime=runtime,
            plan=plan,
            requirement_batch=requirement_batch,
            batch_analysis=batch_analysis,
            batch_index=index,
            batch_total=len(batches),
            maximum_repairs=maximum_repairs,
            expected_requirement_ids=expected_ids,
        )
        decisions.extend(plan.decisions)
        warnings.extend(plan.warnings)
        notes.append(plan.agent_note)
        saved_batches.append(
            {
                "index": index,
                "requirement_ids": expected_ids,
                "output": plan.model_dump(),
            }
        )
        write_json(
            runtime.run_path / "result" / "plan.json",
            {
                "completed_batches": index,
                "total_batches": len(batches),
                "decisions": [item.model_dump() for item in decisions],
                "batches": saved_batches,
                "warnings": unique_strings(warnings),
                "agent_note": join_notes(notes),
            },
        )
    write_json(
        runtime.run_path / "result" / "applied_plan.json",
        read_json(runtime.run_path / "result" / "plan.json", {}),
    )
    return decisions, warnings, notes, len(batches)


def _apply_plan_with_repair(
    *,
    runtime: PipelineRuntime,
    plan: PipelinePlanOutput,
    requirement_batch: list[dict[str, Any]],
    batch_analysis: list[RequirementAnalysisItem],
    batch_index: int,
    batch_total: int,
    maximum_repairs: int,
    expected_requirement_ids: list[str],
) -> PipelinePlanOutput:
    current = plan
    schema_root = runtime.run_path / "working" / "ui_schema"
    for repair_index in range(maximum_repairs + 1):
        try:
            issues = validate_plan_preflight(
                schema_root=schema_root,
                decisions=current.decisions,
                changes=current.changes,
            )
            if issues:
                raise ChangePreflightError(issues)
            runtime.apply_changes(current.changes)
            return current
        except (OSError, TypeError, ValueError) as exc:
            if repair_index >= maximum_repairs:
                raise
            technical_issues = (
                list(exc.issues)
                if isinstance(exc, ChangePreflightError)
                else [{"code": "apply_error", "message": str(exc)}]
            )
            technical_errors = [
                str(item.get("message") or item.get("code") or "")
                for item in technical_issues
            ]
            runtime.event(
                event_type="pipeline_apply_rejected",
                level="warning",
                message=(
                    f"Пакет изменений отклонён: ошибок {len(technical_issues)}; "
                    f"{technical_errors[0][:500] if technical_errors else str(exc)[:500]}"
                ),
                data={
                    "repair_attempt": repair_index + 1,
                    "batch": batch_index,
                    "technical_errors": technical_errors[:30],
                    "technical_issues": technical_issues[:30],
                },
            )
            rejected_plan = current.model_dump()
            current = runtime.invoke_validated(
                output_model=PipelinePlanOutput,
                stage="repair",
                base_context=build_planning_repair_context(
                    run_path=runtime.run_path,
                    requirement_batch=requirement_batch,
                    batch_analysis=[item.model_dump() for item in batch_analysis],
                    rejected_plan=rejected_plan,
                    technical_issues=technical_issues,
                    batch_index=batch_index,
                    batch_total=batch_total,
                ),
                validator=lambda value, ids=expected_requirement_ids: validate_plan_decisions(
                    value.decisions,
                    expected_requirement_ids=ids,
                    schema_root=schema_root,
                    validate_actions=False,
                ),
            )
    return current


def _compact_global_analysis(
    analyses: list[RequirementAnalysisItem],
) -> list[dict[str, str]]:
    """Keep cross-batch orientation without repeating full analysis text."""
    return [
        {
            "requirement_id": item.requirement_id,
            "ui_effect": item.ui_effect,
            "classification": item.classification,
        }
        for item in analyses
    ]
