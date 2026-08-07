from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_coverage_plan import schema_change_plan_context
from backend.modules.ui_schema.agent_coverage_plan_execution import build_coverage_plan_execution_report
from backend.modules.ui_schema.agent_coverage_plan_targets import build_coverage_plan_target_report
from backend.modules.ui_schema.agent_requirement_batches import (
    batch_by_id,
    configured_requirement_fields,
    next_batch_id,
    requirement_subset_context,
)
from backend.modules.ui_schema.agent_review_batches import (
    build_review_batches,
    next_review_batch_id,
    public_review_batch_context,
)
from backend.modules.ui_schema.agent_traceability_correction import build_traceability_correction_context
from backend.modules.ui_schema.agent_traceability_items import read_traceability_items
from backend.modules.ui_schema.files import read_json


def build_current_workflow_context(
    run_path: Path,
    *,
    agent_config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return the exact current technical workflow step and its bounded context.

    This function reads only persisted workflow state and exact IDs. It does not inspect
    requirement meaning or choose classifications, targets, actions or statuses.
    """

    result_root = run_path / "result"
    coverage_state = read_json(result_root / "coverage_plan_state.json", {})
    coverage_completed = {
        str(item)
        for item in coverage_state.get("completed_batch_ids", [])
        if str(item).strip()
    }
    coverage_next = next_batch_id(
        run_path,
        agent_config=agent_config,
        completed_batch_ids=coverage_completed,
    )
    if coverage_next is not None:
        batch = batch_by_id(run_path, agent_config=agent_config, batch_id=coverage_next)
        plan = read_json(result_root / "coverage_plan.json", {})
        accepted = {
            str(item.get("requirement_id") or "")
            for item in plan.get("items", [])
            if isinstance(item, dict)
        }
        remaining = set(batch["requirement_ids"]) - accepted
        return {
            "stage": "coverage_plan",
            "next_action": "write_ui_schema_coverage_plan_batch",
            "current_requirement_batch_context": requirement_subset_context(
                run_path,
                agent_config=agent_config,
                batch_id=coverage_next,
                requirement_ids=remaining or set(batch["requirement_ids"]),
                fields=configured_requirement_fields(agent_config),
            ),
        }

    if not bool(coverage_state.get("review_complete")):
        pending = read_json(result_root / "coverage_plan_review_pending.json", {})
        batches = build_review_batches(pending, agent_config=agent_config, prefix="coverage_review")
        completed = {
            str(item)
            for item in coverage_state.get("review_completed_batch_ids", [])
            if str(item).strip()
        }
        current_id = next_review_batch_id(batches, completed_batch_ids=completed)
        review = read_json(result_root / "coverage_plan_review.json", {})
        reviewed = {
            str(item)
            for item in (review.get("reviewed_candidate_ids_by_batch", {}) or {}).get(
                str(current_id), []
            )
            if str(item).strip()
        }
        return {
            "stage": "coverage_plan_review",
            "next_action": "review_ui_schema_coverage_plan",
            "quality_review_context": public_review_batch_context(
                pending,
                batches=batches,
                review_batch_id=str(current_id),
                completed_batch_ids=completed,
                reviewed_candidate_ids=reviewed,
            ),
        }

    target_report = build_coverage_plan_target_report(run_path)
    if not bool(target_report.get("complete")):
        return {
            "stage": "coverage_plan_target_correction",
            "next_action": "revise_ui_schema_coverage_plan",
            "coverage_plan_target_validation": target_report,
        }

    execution = build_coverage_plan_execution_report(run_path, agent_config=agent_config)
    if not bool(execution.get("complete")):
        return {
            "stage": "schema_changes",
            "next_action": "apply_ui_schema_changes_or_finalize_ui_schema_changes",
            "schema_change_plan": schema_change_plan_context(run_path),
            "coverage_plan_execution": {
                "gap_count": int(execution.get("gap_count", 0)),
                "gaps": list(execution.get("gaps", [])),
                "observation_count": int(execution.get("observation_count", 0)),
                "observations": list(execution.get("observations", [])),
            },
        }

    trace_state = read_json(result_root / "traceability_state.json", {})
    trace_completed = {
        str(item)
        for item in trace_state.get("completed_batch_ids", [])
        if str(item).strip()
    }
    if not bool(trace_state.get("initial_batches_complete")):
        trace_next = next_batch_id(
            run_path,
            agent_config=agent_config,
            completed_batch_ids=trace_completed,
        )
        batch = batch_by_id(run_path, agent_config=agent_config, batch_id=str(trace_next))
        accepted = set(read_traceability_items(result_root))
        remaining = set(batch["requirement_ids"]) - accepted
        return {
            "stage": "traceability",
            "next_action": "write_ui_schema_traceability_batch",
            "current_requirement_batch_context": requirement_subset_context(
                run_path,
                agent_config=agent_config,
                batch_id=str(trace_next),
                requirement_ids=remaining or set(batch["requirement_ids"]),
                fields=configured_requirement_fields(agent_config),
            ),
        }

    if not bool(trace_state.get("review_complete")):
        pending = read_json(result_root / "traceability_review_pending.json", {})
        batches = build_review_batches(pending, agent_config=agent_config, prefix="traceability_review")
        completed = {
            str(item)
            for item in trace_state.get("review_completed_batch_ids", [])
            if str(item).strip()
        }
        current_id = next_review_batch_id(batches, completed_batch_ids=completed)
        review = read_json(result_root / "traceability_review.json", {})
        reviewed = {
            str(item)
            for item in (review.get("reviewed_candidate_ids_by_batch", {}) or {}).get(
                str(current_id), []
            )
            if str(item).strip()
        }
        return {
            "stage": "traceability_review",
            "next_action": "review_ui_schema_traceability",
            "quality_review_context": public_review_batch_context(
                pending,
                batches=batches,
                review_batch_id=str(current_id),
                completed_batch_ids=completed,
                reviewed_candidate_ids=reviewed,
            ),
        }

    validation = read_json(result_root / "validation_preview.json", {})
    if isinstance(validation, dict) and not bool(validation.get("valid")):
        correction = build_traceability_correction_context(
            run_path,
            agent_config=agent_config,
            validation=validation,
        )
        if correction:
            return {
                "stage": "traceability_correction",
                "next_action": "write_ui_schema_traceability_batch",
                "traceability_correction_context": correction,
            }
        return {
            "stage": "technical_correction",
            "next_action": "fix_validation_errors",
            "validation": validation,
        }

    return {"stage": "complete", "next_action": "stop"}
