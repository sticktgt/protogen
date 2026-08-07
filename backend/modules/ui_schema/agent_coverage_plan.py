from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.ui_schema.agent_json_arguments import parse_json_array

from backend.modules.ui_schema.agent_requirement_decisions import (
    CoveragePlanItem,
    validate_decision_consistency,
)
from backend.modules.ui_schema.agent_requirement_batches import (
    batch_by_id,
    build_requirement_batches,
    configured_requirement_fields,
    next_batch_id,
    requirement_subset_context,
)
from backend.modules.ui_schema.agent_requirement_scope import current_requirement_ids
from backend.modules.ui_schema.files import read_json, write_json

_PLAN_FILE = "coverage_plan.json"
_STATE_FILE = "coverage_plan_state.json"
_ALLOWED_CLASSIFICATIONS = {"direct_ui", "cross_cutting_ui", "no_ui", "unclear"}


class CoveragePlanBatchWriteArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CoveragePlanItem] = Field(
        min_length=1,
        description=(
            "Fresh planning items for the unresolved requirements in the current batch. "
            "The backend infers the batch and preserves valid submitted items if another item is invalid."
        ),
    )
    agent_note: str = Field(default="")

    @field_validator("items", mode="before")
    @classmethod
    def _decode_json_arrays(cls, value: Any) -> Any:
        return parse_json_array(value)


def write_coverage_plan_batch(
    run_path: Path,
    *,
    agent_config: dict[str, Any] | None,
    items: list[CoveragePlanItem | dict[str, Any]],
    agent_note: str = "",
) -> dict[str, Any]:
    state_path = run_path / "result" / _STATE_FILE
    state = read_json(state_path, {})
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
        raise ValueError("Coverage plan batches are already complete")
    batch = batch_by_id(
        run_path,
        agent_config=agent_config,
        batch_id=expected_batch_id,
    )
    expected_ids = set(batch["requirement_ids"])

    plan_path = run_path / "result" / _PLAN_FILE
    plan = read_json(plan_path, {"items": [], "agent_note": ""})
    by_id = {
        str(item.get("requirement_id") or ""): dict(item)
        for item in plan.get("items", [])
        if isinstance(item, dict) and str(item.get("requirement_id") or "")
    }
    already_accepted = expected_ids & set(by_id)

    normalized: list[CoveragePlanItem] = []
    item_errors: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in items:
        item = raw if isinstance(raw, CoveragePlanItem) else CoveragePlanItem.model_validate(raw)
        requirement_id = item.requirement_id.strip()
        if requirement_id in seen:
            item_errors.append(
                {"requirement_id": requirement_id, "error": "duplicate requirement ID in submission"}
            )
            continue
        seen.add(requirement_id)
        if requirement_id not in expected_ids:
            item_errors.append(
                {"requirement_id": requirement_id, "error": "requirement ID is outside the current batch"}
            )
            continue
        if requirement_id in already_accepted:
            item_errors.append(
                {"requirement_id": requirement_id, "error": "requirement was already accepted in the current batch"}
            )
            continue
        try:
            validate_decision_consistency(item)
        except ValueError as exc:
            item_errors.append({"requirement_id": requirement_id, "error": str(exc)})
            continue
        normalized.append(item)

    for item in normalized:
        by_id[item.requirement_id] = item.model_dump(exclude_none=True)

    order = _requirement_order(run_path)
    current_items = sorted(
        by_id.values(),
        key=lambda item: order.get(str(item.get("requirement_id") or ""), 10**9),
    )
    write_json(
        plan_path,
        {
            "items": current_items,
            "agent_note": str(agent_note or plan.get("agent_note") or ""),
        },
    )

    accepted_ids = expected_ids & set(by_id)
    remaining_ids = expected_ids - accepted_ids
    counts, target_actions = _plan_counts(current_items)
    result: dict[str, Any] = {
        "ok": not item_errors,
        "batch_id": expected_batch_id,
        "accepted_in_call": len(normalized),
        "accepted_in_batch": len(accepted_ids),
        "remaining_in_batch": len(remaining_ids),
        "item_errors": item_errors,
        "planned_requirements": len(current_items),
        "classification_counts": counts,
        "target_action_counts": target_actions,
        "batches_complete": False,
    }

    if remaining_ids:
        result.update(
            {
                "next_action": "write_remaining_coverage_plan_items",
                "current_requirement_batch_context": requirement_subset_context(
                    run_path,
                    agent_config=agent_config,
                    batch_id=expected_batch_id,
                    requirement_ids=remaining_ids,
                    fields=configured_requirement_fields(agent_config),
                ),
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
    write_json(
        state_path,
        {
            **state,
            "completed_batch_ids": sorted(completed),
            "batch_count": len(build_requirement_batches(run_path, agent_config=agent_config)),
            "batches_complete": next_id is None,
            "review_complete": False if next_id is None else bool(state.get("review_complete", False)),
        },
    )
    result["batches_complete"] = next_id is None
    result["next_batch_id"] = next_id
    result["next_action"] = (
        "review_coverage_plan" if next_id is None else "write_next_coverage_plan_batch"
    )
    if next_id is not None:
        result["next_requirement_batch_context"] = requirement_subset_context(
            run_path,
            agent_config=agent_config,
            batch_id=next_id,
            requirement_ids=set(
                batch_by_id(run_path, agent_config=agent_config, batch_id=next_id)["requirement_ids"]
            ),
            fields=configured_requirement_fields(agent_config),
        )
    return result


def coverage_plan_errors(
    run_path: Path,
    *,
    agent_config: dict[str, Any] | None = None,
) -> list[str]:
    expected = current_requirement_ids(run_path)
    if not expected:
        return []
    data = read_json(run_path / "result" / _PLAN_FILE, {})
    items = data.get("items", []) if isinstance(data, dict) else []
    ids = {
        str(item.get("requirement_id") or "").strip()
        for item in items
        if isinstance(item, dict) and str(item.get("requirement_id") or "").strip()
    }
    if not items:
        return [
            "Coverage plan is missing: write every configured requirement batch before changing the schema"
        ]
    missing = sorted(expected - ids)
    unknown = sorted(ids - expected)
    errors: list[str] = []
    if missing:
        errors.append("Coverage plan is missing requirement IDs: " + ", ".join(missing[:30]))
    if unknown:
        errors.append("Coverage plan contains unknown requirement IDs: " + ", ".join(unknown[:30]))

    state = read_json(run_path / "result" / _STATE_FILE, {})
    batches = build_requirement_batches(run_path, agent_config=agent_config)
    completed = {
        str(item)
        for item in state.get("completed_batch_ids", [])
        if str(item).strip()
    }
    missing_batches = [batch["batch_id"] for batch in batches if batch["batch_id"] not in completed]
    if missing_batches:
        errors.append("Coverage plan batches are incomplete: " + ", ".join(missing_batches))
    if batches and not bool(state.get("review_complete")):
        errors.append(
            "Coverage plan quality review is not completed: review the formal candidates returned after the last batch"
        )
    elif batches:
        from backend.modules.ui_schema.agent_coverage_plan_targets import (
            build_coverage_plan_target_report,
            coverage_plan_target_errors,
        )

        if not read_json(run_path / "result" / "coverage_plan_targets.json", {}):
            build_coverage_plan_target_report(run_path)
        errors.extend(coverage_plan_target_errors(run_path))
    return errors


def schema_change_plan_context(run_path: Path) -> dict[str, Any]:
    plan = read_json(run_path / "result" / _PLAN_FILE, {})
    items = [dict(item) for item in plan.get("items", []) if isinstance(item, dict)]
    return {
        "item_count": len(items),
        "items": items,
        "agent_note": str(plan.get("agent_note") or ""),
    }


def require_coverage_plan(
    run_path: Path,
    *,
    agent_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors = coverage_plan_errors(run_path, agent_config=agent_config)
    if errors:
        raise ValueError(" | ".join(errors))
    return read_json(run_path / "result" / _PLAN_FILE, {})


def coverage_plan_exists(
    run_path: Path,
    *,
    agent_config: dict[str, Any] | None = None,
) -> bool:
    return not coverage_plan_errors(run_path, agent_config=agent_config)


def mark_coverage_plan_review_complete(run_path: Path, *, candidate_count: int) -> None:
    path = run_path / "result" / _STATE_FILE
    state = read_json(path, {})
    write_json(
        path,
        {
            **state,
            "review_complete": True,
            "review_candidate_count": max(0, int(candidate_count)),
        },
    )


def _requirement_order(run_path: Path) -> dict[str, int]:
    from backend.modules.ui_schema.agent_requirement_scope import compact_requirements

    return {
        str(item.get("id") or ""): index
        for index, item in enumerate(compact_requirements(run_path, fields=["id"]))
    }


def _plan_counts(items: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, int]]:
    counts = {key: 0 for key in sorted(_ALLOWED_CLASSIFICATIONS)}
    target_actions: dict[str, int] = {"reuse": 0, "extend": 0, "create": 0}
    for raw in items:
        classification = str(raw.get("classification") or "")
        if classification in counts:
            counts[classification] += 1
        for target in raw.get("targets", []) if isinstance(raw.get("targets"), list) else []:
            if not isinstance(target, dict):
                continue
            action = str(target.get("action") or "")
            if action in target_actions:
                target_actions[action] += 1
    return counts, target_actions


class CoveragePlanRevisionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CoveragePlanItem] = Field(
        min_length=1,
        description="Complete replacement plan items for only the explicitly revised requirement IDs",
    )
    reason: str = Field(min_length=1, description="Why the reviewed plan must be revised")


def revise_coverage_plan_items(
    run_path: Path,
    *,
    items: list[CoveragePlanItem | dict[str, Any]],
    reason: str,
) -> dict[str, Any]:
    state = read_json(run_path / "result" / _STATE_FILE, {})
    if not bool(state.get("review_complete")):
        raise ValueError("Coverage plan can be revised only after its quality review is complete")
    normalized = [
        item if isinstance(item, CoveragePlanItem) else CoveragePlanItem.model_validate(item)
        for item in items
    ]
    for item in normalized:
        validate_decision_consistency(item)
    current_ids = current_requirement_ids(run_path)
    ids = [item.requirement_id.strip() for item in normalized]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    unknown = sorted(set(ids) - current_ids)
    if duplicates or unknown:
        parts: list[str] = []
        if duplicates:
            parts.append("duplicate requirement IDs: " + ", ".join(duplicates[:20]))
        if unknown:
            parts.append("unknown requirement IDs: " + ", ".join(unknown[:20]))
        raise ValueError("Invalid coverage-plan revision; " + " | ".join(parts))

    plan_path = run_path / "result" / _PLAN_FILE
    plan = read_json(plan_path, {})
    items_by_id = {
        str(item.get("requirement_id") or ""): dict(item)
        for item in plan.get("items", [])
        if isinstance(item, dict)
    }
    for item in normalized:
        items_by_id[item.requirement_id] = item.model_dump(exclude_none=True)
    order = _requirement_order(run_path)
    updated = sorted(
        items_by_id.values(),
        key=lambda item: order.get(str(item.get("requirement_id") or ""), 10**9),
    )
    write_json(
        plan_path,
        {
            "items": updated,
            "agent_note": str(plan.get("agent_note") or ""),
        },
    )
    from backend.modules.ui_schema.agent_coverage_plan_execution import invalidate_coverage_plan_execution
    from backend.modules.ui_schema.files import write_json as _write_json

    invalidate_coverage_plan_execution(run_path)
    _write_json(run_path / "result" / "coverage_plan_targets.json", {})
    return {
        "ok": True,
        "revised_requirement_ids": ids,
        "revised_count": len(ids),
        "reason": str(reason),
        "next_action": "apply_schema_changes_or_finalize_again",
    }
