from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_llm import create_chat_model
from backend.modules.ui_schema.agent_pipeline_analysis import run_analysis_batches
from backend.modules.ui_schema.agent_pipeline_audit import run_audit_batches
from backend.modules.ui_schema.agent_pipeline_context import requirement_records
from backend.modules.ui_schema.agent_pipeline_correction import (
    issue_requirement_ids,
    run_correction_batches,
    technical_issue_ids,
)
from backend.modules.ui_schema.agent_pipeline_planning import run_planning_batches
from backend.modules.ui_schema.agent_pipeline_results import write_pipeline_results
from backend.modules.ui_schema.agent_pipeline_runtime import PipelineRuntime
from backend.modules.ui_schema.agent_pipeline_settings import pipeline_settings
from backend.modules.ui_schema.agent_structural_warnings import collect_structural_warnings
from backend.modules.ui_schema.agent_pipeline_validation import (
    validate_final_targets,
    validate_plan_decisions,
)
from backend.modules.ui_schema.agent_pipeline_values import join_notes, unique_strings
from backend.modules.ui_schema.files import read_json, write_json


def run_managed_pipeline(
    *,
    module_root: Path,
    run_id: str,
    run_path: Path,
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
    callback: Any,
) -> dict[str, Any]:
    """Run pipeline v2 with backend-owned stage order and model-owned decisions."""
    settings = pipeline_settings(agent_config)
    run = read_json(run_path / "run.json", {})
    runtime = PipelineRuntime(
        module_root=module_root,
        run_id=run_id,
        run_path=run_path,
        model=create_chat_model(llm_settings, agent_config),
        agent_config=agent_config,
        callback=callback,
        metadata={"workspace_id": run.get("workspace_id"), "run_id": run_id},
    )
    write_json(
        run_path / "result" / "pipeline_state.json",
        {"version": 2, "status": "running", "phase": "preparing"},
    )

    requirements = requirement_records(run_path, agent_config=agent_config)
    requirement_ids = _requirement_ids(requirements)

    analyses, analysis_warnings, analysis_batch_count = run_analysis_batches(
        runtime=runtime,
        requirements=requirements,
        batch_size=int(settings["analysis_batch_size"]),
    )
    decisions, planning_warnings, planning_notes, planning_batch_count = (
        run_planning_batches(
            runtime=runtime,
            requirements=requirements,
            analyses=analyses,
            batch_size=int(settings["planning_batch_size"]),
            maximum_repairs=int(settings["apply_repair_attempts"]),
        )
    )

    final_decisions = list(decisions)
    technical_errors = validate_final_targets(
        final_decisions,
        schema_root=run_path / "working" / "ui_schema",
    )
    runtime.phase("auditing", "Независимый аудит фактической схемы")
    audit_issues, audit_warnings, audit_batch_count = run_audit_batches(
        runtime=runtime,
        requirements=requirements,
        decisions=decisions,
        batch_size=int(settings["audit_batch_size"]),
    )

    correction_notes: list[str] = []
    correction_warnings: list[str] = []
    correction_batch_count = 0
    correction_review_batch_count = 0

    initial_correction_ids = issue_requirement_ids(audit_issues, technical_errors)
    if initial_correction_ids:
        correction_scope_ids = set(initial_correction_ids)
        pending_ids = set(initial_correction_ids)
        pending_audit_issues = list(audit_issues)
        pending_technical_errors = list(technical_errors)
        correction_rounds = int(settings["correction_rounds"])
        for correction_round in range(1, correction_rounds + 1):
            runtime.phase(
                "correcting",
                f"Точечное исправление результатов аудита, раунд {correction_round}",
            )
            final_decisions, notes, warnings, batch_count = run_correction_batches(
                runtime=runtime,
                requirements=requirements,
                decisions=final_decisions,
                audit_issues=pending_audit_issues,
                technical_errors=pending_technical_errors,
                required_ids=pending_ids,
                batch_size=int(settings["correction_batch_size"]),
                maximum_apply_repairs=int(settings["apply_repair_attempts"]),
            )
            correction_notes.extend(notes)
            correction_warnings.extend(warnings)
            correction_batch_count += batch_count

            runtime.phase(
                "auditing",
                f"Проверка результата исправления, раунд {correction_round}",
            )
            review_requirements = [
                item
                for item in requirements
                if str(item.get("id") or "") in correction_scope_ids
            ]
            remaining_audit_issues, review_warnings, review_batch_count = (
                run_audit_batches(
                    runtime=runtime,
                    requirements=review_requirements,
                    decisions=final_decisions,
                    batch_size=int(settings["audit_batch_size"]),
                    result_file_name=(
                        f"correction_review_{correction_round}.json"
                    ),
                    context_overrides={
                        "audit_mode": "correction_verification",
                        "correction_round": correction_round,
                        "previous_issues": [
                            item.model_dump() for item in pending_audit_issues
                        ],
                        "previous_technical_errors": pending_technical_errors,
                    },
                )
            )
            correction_warnings.extend(review_warnings)
            correction_review_batch_count += review_batch_count

            current_target_errors = validate_final_targets(
                final_decisions,
                schema_root=run_path / "working" / "ui_schema",
            )
            remaining_technical_errors = [
                error
                for error in current_target_errors
                if str(error).split(":", 1)[0].strip() in correction_scope_ids
            ]
            pending_ids = issue_requirement_ids(
                remaining_audit_issues,
                remaining_technical_errors,
            ) & correction_scope_ids
            if not pending_ids:
                break
            pending_audit_issues = [
                item
                for item in remaining_audit_issues
                if item.requirement_id in pending_ids
            ]
            pending_technical_errors = [
                error
                for error in remaining_technical_errors
                if str(error).split(":", 1)[0].strip() in pending_ids
            ]
            if correction_round >= correction_rounds:
                unresolved_audit_ids = sorted(
                    {item.requirement_id for item in pending_audit_issues}
                )
                if unresolved_audit_ids:
                    correction_warnings.append(
                        "После повторной коррекции остались смысловые замечания для "
                        "требований: "
                        + ", ".join(unresolved_audit_ids)
                        + ". Результат можно проверить вручную."
                    )

    for _ in range(int(settings["validation_repair_attempts"])):
        remaining_errors = validate_final_targets(
            final_decisions,
            schema_root=run_path / "working" / "ui_schema",
        )
        remaining_ids = technical_issue_ids(remaining_errors)
        if not remaining_ids:
            break
        runtime.phase("correcting", "Исправление отсутствующих итоговых целей")
        final_decisions, notes, warnings, batch_count = run_correction_batches(
            runtime=runtime,
            requirements=requirements,
            decisions=final_decisions,
            audit_issues=[],
            technical_errors=remaining_errors,
            required_ids=remaining_ids,
            batch_size=int(settings["correction_batch_size"]),
            maximum_apply_repairs=int(settings["apply_repair_attempts"]),
        )
        correction_notes.extend(notes)
        correction_warnings.extend(warnings)
        correction_batch_count += batch_count

    runtime.phase("structural_check", "Проверка структурных кандидатов")
    structural_warnings, structural_candidate_count = collect_structural_warnings(
        runtime=runtime,
        decisions=final_decisions,
        maximum_candidates=int(settings["structural_review_candidate_limit"]),
    )
    structural_notes: list[str] = []

    _validate_final_decisions(
        decisions=final_decisions,
        requirement_ids=requirement_ids,
        schema_root=run_path / "working" / "ui_schema",
    )

    runtime.phase("writing_traceability", "Запись итоговой трассировки")
    final_note = join_notes(
        [*planning_notes, *correction_notes, *structural_notes]
    )
    final_warnings = unique_strings(
        [
            *analysis_warnings,
            *planning_warnings,
            *audit_warnings,
            *correction_warnings,
            *structural_warnings,
        ]
    )
    write_pipeline_results(
        run_path=run_path,
        decisions=final_decisions,
        agent_note=final_note,
        warnings=final_warnings,
    )
    write_json(
        run_path / "result" / "pipeline_decisions.json",
        {"items": [item.model_dump() for item in final_decisions]},
    )
    summary = {
        "version": 2,
        "analysis_batches": analysis_batch_count,
        "planning_batches": planning_batch_count,
        "audit_batches": audit_batch_count,
        "correction_batches": correction_batch_count,
        "correction_review_batches": correction_review_batch_count,
        "audit_issue_count": len(audit_issues),
        "structural_candidate_count": structural_candidate_count,
        "requirement_count": len(requirements),
    }
    write_json(run_path / "result" / "pipeline.json", summary)
    write_json(
        run_path / "result" / "pipeline_state.json",
        {**summary, "status": "generated", "phase": "generated"},
    )
    return {
        "decisions": final_decisions,
        "agent_note": final_note,
        "warnings": final_warnings,
    }


def _requirement_ids(requirements: list[dict[str, Any]]) -> list[str]:
    requirement_ids = [str(item.get("id") or "").strip() for item in requirements]
    if not requirement_ids or any(not item for item in requirement_ids):
        raise ValueError("Входной файл не содержит полного набора требований с ID")
    if len(requirement_ids) != len(set(requirement_ids)):
        raise ValueError("Входной файл содержит повторяющиеся ID требований")
    return requirement_ids


def _validate_final_decisions(
    *,
    decisions: list[Any],
    requirement_ids: list[str],
    schema_root: Path,
) -> None:
    errors = validate_plan_decisions(
        decisions,
        expected_requirement_ids=requirement_ids,
        schema_root=schema_root,
        validate_actions=False,
    )
    errors.extend(validate_final_targets(decisions, schema_root=schema_root))
    if errors:
        raise ValueError(
            "Финальные решения pipeline технически некорректны: "
            + "; ".join(errors[:20])
        )
