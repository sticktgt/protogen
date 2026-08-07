from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_completion import validate_and_mark_completion
from backend.modules.ui_schema.agent_coverage_plan import require_coverage_plan
from backend.modules.ui_schema.agent_coverage_plan_diff import write_coverage_plan_diff
from backend.modules.ui_schema.agent_coverage_plan_execution import require_coverage_plan_execution_complete
from backend.modules.ui_schema.agent_requirement_batches import (
    batch_by_id,
    build_requirement_batches,
    configured_requirement_fields,
    next_batch_id,
    requirement_subset_context,
)
from backend.modules.ui_schema.agent_requirement_decisions import (
    TraceabilityItem,
    validate_decision_consistency,
)
from backend.modules.ui_schema.agent_review_batches import (
    build_review_batches,
    next_review_batch_id,
    public_review_batch_context,
)
from backend.modules.ui_schema.agent_traceability import write_traceability_chunk
from backend.modules.ui_schema.agent_traceability_models import traceability_items_to_storage
from backend.modules.ui_schema.agent_traceability_items import (
    read_traceability_items,
    write_traceability_items,
)
from backend.modules.ui_schema.agent_traceability_review import (
    build_traceability_review_context,
    mark_empty_traceability_review_complete,
)
from backend.modules.ui_schema.files import read_json, write_json

_STATE_FILE = "traceability_state.json"


def write_traceability_batch(
    *,
    run_path: Path,
    working_root: Path,
    result_root: Path,
    agent_config: dict[str, Any] | None,
    items: list[TraceabilityItem | dict[str, Any]],
    agent_note: str,
    warnings: list[str],
    validate_after_write: bool,
) -> dict[str, Any]:
    require_coverage_plan(run_path, agent_config=agent_config)
    if not items:
        raise ValueError("Traceability items must not be empty")

    state_path = result_root / _STATE_FILE
    state = read_json(state_path, {})
    initial_complete = bool(state.get("initial_batches_complete"))
    if initial_complete and not bool(state.get("review_complete")):
        raise ValueError(
            "Initial traceability batches are complete, but traceability review is still pending. "
            "Use review_ui_schema_traceability for the current review candidates."
        )

    normalized: list[TraceabilityItem] = []
    item_errors: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in items:
        item = raw if isinstance(raw, TraceabilityItem) else TraceabilityItem.model_validate(raw)
        requirement_id = item.requirement_id.strip()
        if requirement_id in seen:
            item_errors.append({"requirement_id": requirement_id, "error": "duplicate requirement ID in submission"})
            continue
        seen.add(requirement_id)
        try:
            validate_decision_consistency(item)
        except ValueError as exc:
            item_errors.append({"requirement_id": requirement_id, "error": str(exc)})
            continue
        normalized.append(item)

    if initial_complete:
        return _write_correction_items(
            run_path=run_path,
            working_root=working_root,
            result_root=result_root,
            normalized=normalized,
            item_errors=item_errors,
            agent_note=agent_note,
            warnings=warnings,
            validate_after_write=validate_after_write,
        )

    require_coverage_plan_execution_complete(run_path)
    completed = {
        str(item)
        for item in state.get("completed_batch_ids", [])
        if str(item).strip()
    }
    expected_batch_id = next_batch_id(
        run_path,
        agent_config=agent_config,
        completed_batch_ids=completed,
    )
    if expected_batch_id is None:
        raise ValueError("Initial traceability batches are already complete")
    batch = batch_by_id(run_path, agent_config=agent_config, batch_id=expected_batch_id)
    expected_ids = set(batch["requirement_ids"])
    current_items = read_traceability_items(result_root)
    already_accepted = expected_ids & set(current_items)

    accepted: list[TraceabilityItem] = []
    for item in normalized:
        requirement_id = item.requirement_id.strip()
        if requirement_id not in expected_ids:
            item_errors.append({"requirement_id": requirement_id, "error": "requirement ID is outside the current batch"})
            continue
        if requirement_id in already_accepted:
            item_errors.append({"requirement_id": requirement_id, "error": "requirement was already accepted in the current batch"})
            continue
        accepted.append(item)

    write_result: dict[str, Any] = {"ok": not item_errors}
    if accepted:
        requirement_ui_links, agent_report = traceability_items_to_storage(
            accepted,
            agent_note=agent_note,
            warnings=warnings,
        )
        write_result = write_traceability_chunk(
            run_path=run_path,
            working_root=working_root,
            result_root=result_root,
            requirement_ui_links=requirement_ui_links,
            agent_report=agent_report,
        )
        write_traceability_items(
            result_root,
            run_path=run_path,
            items=accepted,
            reset=not bool(state.get("initialized")),
        )

    current_items = read_traceability_items(result_root)
    accepted_ids = expected_ids & set(current_items)
    remaining_ids = expected_ids - accepted_ids
    result: dict[str, Any] = {
        **write_result,
        "ok": not item_errors,
        "batch_id": expected_batch_id,
        "accepted_in_call": len(accepted),
        "accepted_in_batch": len(accepted_ids),
        "remaining_in_batch": len(remaining_ids),
        "item_errors": item_errors,
        "batches_complete": False,
        "completed": False,
    }
    if remaining_ids:
        result.update(
            {
                "current_requirement_batch_context": requirement_subset_context(
                    run_path,
                    agent_config=agent_config,
                    batch_id=expected_batch_id,
                    requirement_ids=remaining_ids,
                    fields=configured_requirement_fields(agent_config),
                ),
                "next_action": "write_remaining_traceability_items",
            }
        )
        return result

    if item_errors:
        result["ignored_item_errors"] = item_errors
        result["item_errors"] = []
        result["ok"] = True

    completed.add(expected_batch_id)
    next_id = next_batch_id(
        run_path,
        agent_config=agent_config,
        completed_batch_ids=completed,
    )
    latest_state = read_json(state_path, {})
    write_json(
        state_path,
        {
            **latest_state,
            "completed_batch_ids": sorted(completed),
            "batch_count": len(build_requirement_batches(run_path, agent_config=agent_config)),
            "initial_batches_complete": next_id is None,
            "review_complete": False,
        },
    )
    if next_id is not None:
        result.update(
            {
                "batches_complete": False,
                "next_batch_id": next_id,
                "next_requirement_batch_context": requirement_subset_context(
                    run_path,
                    agent_config=agent_config,
                    batch_id=next_id,
                    requirement_ids=set(
                        batch_by_id(run_path, agent_config=agent_config, batch_id=next_id)["requirement_ids"]
                    ),
                    fields=configured_requirement_fields(agent_config),
                ),
                "next_action": "write_next_traceability_batch",
            }
        )
        return result

    return _start_or_complete_traceability_review(
        run_path=run_path,
        result_root=result_root,
        agent_config=agent_config,
        write_result=result,
        validate_after_write=validate_after_write,
    )


def _write_correction_items(
    *,
    run_path: Path,
    working_root: Path,
    result_root: Path,
    normalized: list[TraceabilityItem],
    item_errors: list[dict[str, str]],
    agent_note: str,
    warnings: list[str],
    validate_after_write: bool,
) -> dict[str, Any]:
    if not normalized:
        return {
            "ok": False,
            "accepted_in_call": 0,
            "item_errors": item_errors,
            "completed": False,
            "next_action": "rewrite_invalid_traceability_items",
        }
    requirement_ui_links, agent_report = traceability_items_to_storage(
        normalized,
        agent_note=agent_note,
        warnings=warnings,
    )
    result = write_traceability_chunk(
        run_path=run_path,
        working_root=working_root,
        result_root=result_root,
        requirement_ui_links=requirement_ui_links,
        agent_report=agent_report,
    )
    write_traceability_items(
        result_root,
        run_path=run_path,
        items=normalized,
        reset=False,
    )
    plan_diff = write_coverage_plan_diff(run_path)
    if item_errors or not validate_after_write:
        return {
            **result,
            "ok": not item_errors,
            "accepted_in_call": len(normalized),
            "item_errors": item_errors,
            "coverage_plan_changes": int(plan_diff.get("changed_count", 0)),
            "completed": False,
            "next_action": (
                "rewrite_invalid_traceability_items" if item_errors else "validate_ui_schema_state"
            ),
        }
    validation = validate_and_mark_completion(
        run_path,
        completed_by="write_ui_schema_traceability_batch:correction",
    )
    return {
        **result,
        **validation,
        "accepted_in_call": len(normalized),
        "item_errors": [],
        "coverage_plan_changes": int(plan_diff.get("changed_count", 0)),
        "completed": bool(validation.get("valid")),
        "next_action": "stop" if validation.get("valid") else "fix_errors_and_continue",
    }


def _start_or_complete_traceability_review(
    *,
    run_path: Path,
    result_root: Path,
    agent_config: dict[str, Any] | None,
    write_result: dict[str, Any],
    validate_after_write: bool,
) -> dict[str, Any]:
    plan_diff = write_coverage_plan_diff(run_path)
    review_context = build_traceability_review_context(run_path, agent_config=agent_config)
    if int(review_context.get("candidate_count", 0)) == 0:
        mark_empty_traceability_review_complete(run_path)
        if not validate_after_write:
            return {
                **write_result,
                "batches_complete": True,
                "coverage_plan_changes": int(plan_diff.get("changed_count", 0)),
                "completed": False,
                "next_action": "validate_ui_schema_state",
            }
        validation = validate_and_mark_completion(
            run_path,
            completed_by="write_ui_schema_traceability_batch",
        )
        return {
            **write_result,
            **validation,
            "batches_complete": True,
            "coverage_plan_changes": int(plan_diff.get("changed_count", 0)),
            "completed": bool(validation.get("valid")),
            "next_action": "stop" if validation.get("valid") else "fix_errors_and_continue",
        }
    review_batches = build_review_batches(
        review_context,
        agent_config=agent_config,
        prefix="traceability_review",
    )
    first_review_id = next_review_batch_id(review_batches, completed_batch_ids=set())
    write_json(result_root / "traceability_review_pending.json", review_context)
    return {
        **write_result,
        "batches_complete": True,
        "coverage_plan_changes": int(plan_diff.get("changed_count", 0)),
        "quality_review_context": public_review_batch_context(
            review_context,
            batches=review_batches,
            review_batch_id=str(first_review_id),
            completed_batch_ids=set(),
        ),
        "completed": False,
        "next_action": "review_traceability_candidates",
    }
