from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.ui_schema.agent_json_arguments import parse_json_array

from backend.modules.ui_schema.agent_coverage_plan import (
    mark_coverage_plan_review_complete,
    schema_change_plan_context,
)
from backend.modules.ui_schema.agent_requirement_decisions import (
    CoveragePlanItem,
    validate_decision_consistency,
)
from backend.modules.ui_schema.agent_requirement_scope import compact_requirements
from backend.modules.ui_schema.agent_coverage_plan_targets import build_coverage_plan_target_report
from backend.modules.ui_schema.agent_review_batches import (
    build_review_batches,
    candidate_id,
    next_review_batch_id,
    public_review_batch_context,
    review_batch_by_id,
)
from backend.modules.ui_schema.files import read_json, write_json

_REVIEW_FILE = "coverage_plan_review.json"


class CoveragePlanReviewArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CoveragePlanItem] = Field(
        min_length=1,
        description=(
            "Fresh complete coverage-plan decisions for any unresolved candidates in the "
            "current blind review group. The backend infers the group and keeps valid items."
        ),
    )
    agent_note: str = Field(default="")

    @field_validator("items", mode="before")
    @classmethod
    def _decode_json_arrays(cls, value: Any) -> Any:
        return parse_json_array(value)


def build_coverage_plan_review_context(
    run_path: Path,
    *,
    agent_config: dict[str, Any] | None,
) -> dict[str, Any]:
    plan = read_json(run_path / "result" / "coverage_plan.json", {})
    plan_items = [dict(item) for item in plan.get("items", []) if isinstance(item, dict)]
    settings = _review_settings(agent_config)
    requirements = {
        str(item.get("id") or ""): item
        for item in compact_requirements(run_path, fields=_requirement_fields(agent_config))
        if str(item.get("id") or "")
    }
    target_counts = Counter(
        (str(target.get("target_type") or ""), str(target.get("target_id") or ""))
        for item in plan_items
        if str(item.get("classification") or "") == "direct_ui"
        for target in item.get("targets", [])
        if isinstance(target, dict) and str(target.get("target_id") or "")
    )
    included_classes = set(settings["include_classifications"])
    shared_minimum = int(settings["shared_target_min_requirements"])
    candidates: list[dict[str, Any]] = []

    for item in plan_items:
        signals: list[str] = []
        classification = str(item.get("classification") or "")
        targets = [dict(target) for target in item.get("targets", []) if isinstance(target, dict)]
        if classification in included_classes:
            signals.append("model_selected_non_direct_class")
        if settings["include_page_targets"] and any(
            str(target.get("target_type") or "") == "page" for target in targets
        ):
            signals.append("model_selected_page_target")
        if shared_minimum > 1 and any(
            target_counts[(str(target.get("target_type") or ""), str(target.get("target_id") or ""))]
            >= shared_minimum
            for target in targets
        ):
            signals.append("model_selected_highly_shared_target")
        if not signals:
            continue
        candidates.append(
            {
                "requirement": requirements.get(str(item.get("requirement_id") or ""), {}),
                "selection_signals": signals,
            }
        )

    return {
        "policy": {
            "selection_is_structural_only": True,
            "backend_does_not_judge_requirement_meaning": True,
            "original_decision_is_hidden": True,
            "review_returns_fresh_complete_items": True,
            "partial_submission_is_allowed": True,
        },
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def review_coverage_plan(
    run_path: Path,
    *,
    agent_config: dict[str, Any] | None,
    items: list[CoveragePlanItem | dict[str, Any]],
    agent_note: str = "",
) -> dict[str, Any]:
    pending_path = run_path / "result" / "coverage_plan_review_pending.json"
    context = read_json(pending_path, {})
    if not isinstance(context, dict) or not isinstance(context.get("candidates"), list):
        context = build_coverage_plan_review_context(run_path, agent_config=agent_config)
    batches = build_review_batches(context, agent_config=agent_config, prefix="coverage_review")
    state_path = run_path / "result" / "coverage_plan_state.json"
    state = read_json(state_path, {})
    completed = {
        str(item)
        for item in state.get("review_completed_batch_ids", [])
        if str(item).strip()
    }
    expected_id = next_review_batch_id(batches, completed_batch_ids=completed)
    if expected_id is None:
        raise ValueError("Coverage plan review is already complete")
    current_batch = review_batch_by_id(batches, review_batch_id=expected_id)
    candidate_ids = {
        candidate_id(item)
        for item in current_batch.get("candidates", [])
        if candidate_id(item)
    }

    existing_review = read_json(run_path / "result" / _REVIEW_FILE, {})
    reviewed_by_batch = {
        str(key): {str(item) for item in value if str(item).strip()}
        for key, value in (existing_review.get("reviewed_candidate_ids_by_batch", {}) or {}).items()
        if isinstance(value, list)
    }
    already_reviewed = reviewed_by_batch.get(expected_id, set())
    remaining_before = candidate_ids - already_reviewed

    plan_path = run_path / "result" / "coverage_plan.json"
    plan = read_json(plan_path, {})
    original_by_id = {
        str(item.get("requirement_id") or ""): dict(item)
        for item in plan.get("items", [])
        if isinstance(item, dict)
    }

    seen: set[str] = set()
    accepted: list[CoveragePlanItem] = []
    item_errors: list[dict[str, str]] = []
    changed_ids: list[str] = []
    for raw in items:
        item = raw if isinstance(raw, CoveragePlanItem) else CoveragePlanItem.model_validate(raw)
        requirement_id = item.requirement_id.strip()
        if requirement_id in seen:
            item_errors.append({"requirement_id": requirement_id, "error": "duplicate candidate ID"})
            continue
        seen.add(requirement_id)
        if requirement_id not in candidate_ids:
            item_errors.append({"requirement_id": requirement_id, "error": "ID is outside the current review group"})
            continue
        if requirement_id in already_reviewed:
            item_errors.append({"requirement_id": requirement_id, "error": "candidate was already accepted in this review group"})
            continue
        try:
            validate_decision_consistency(item)
        except ValueError as exc:
            item_errors.append({"requirement_id": requirement_id, "error": str(exc)})
            continue
        payload = item.model_dump(exclude_none=True)
        if original_by_id.get(requirement_id) != payload:
            changed_ids.append(requirement_id)
        original_by_id[requirement_id] = payload
        accepted.append(item)

    accepted_ids = {item.requirement_id for item in accepted}
    reviewed_now = already_reviewed | accepted_ids
    remaining_after = candidate_ids - reviewed_now

    if accepted:
        order = {
            str(item.get("id") or ""): index
            for index, item in enumerate(compact_requirements(run_path, fields=["id"]))
        }
        updated_items = sorted(
            original_by_id.values(),
            key=lambda item: order.get(str(item.get("requirement_id") or ""), 10**9),
        )
        write_json(
            plan_path,
            {
                "items": updated_items,
                "agent_note": str(agent_note or plan.get("agent_note") or ""),
            },
        )

    reviewed_by_batch[expected_id] = reviewed_now
    reviewed_items = [
        *[dict(item) for item in existing_review.get("reviewed_items", []) if isinstance(item, dict)],
        *[item.model_dump(exclude_none=True) for item in accepted],
    ]
    all_changed = sorted(
        set(str(item) for item in existing_review.get("changed_requirement_ids", []))
        | set(changed_ids)
    )

    if not remaining_after:
        completed.add(expected_id)
    next_id = next_review_batch_id(batches, completed_batch_ids=completed)
    write_json(
        run_path / "result" / _REVIEW_FILE,
        {
            **context,
            "review_batches": [
                {
                    "review_batch_id": str(batch.get("review_batch_id") or ""),
                    "candidate_count": len(batch.get("candidates", [])),
                }
                for batch in batches
            ],
            "completed_review_batch_ids": sorted(completed),
            "reviewed_candidate_ids_by_batch": {
                key: sorted(value) for key, value in reviewed_by_batch.items()
            },
            "reviewed_items": reviewed_items,
            "changed_requirement_ids": all_changed,
            "agent_note": str(agent_note or existing_review.get("agent_note") or ""),
        },
    )
    write_json(
        state_path,
        {**state, "review_completed_batch_ids": sorted(completed)},
    )

    result: dict[str, Any] = {
        "ok": True,
        "partial": bool(item_errors),
        "review_batch_id": expected_id,
        "accepted_in_call": len(accepted),
        "reviewed_in_batch": len(reviewed_now),
        "remaining_in_batch": len(remaining_after),
        "changed_requirements": len(changed_ids),
        "item_errors": item_errors,
        "review_complete": next_id is None and not remaining_after,
    }
    if remaining_after:
        result.update(
            {
                "quality_review_context": public_review_batch_context(
                    context,
                    batches=batches,
                    review_batch_id=expected_id,
                    completed_batch_ids=completed,
                    reviewed_candidate_ids=reviewed_now,
                ),
                "next_action": "review_remaining_coverage_plan_candidates",
            }
        )
        return result

    if item_errors:
        result["ignored_item_errors"] = item_errors
        result["item_errors"] = []
        result["ok"] = True

    if next_id is not None:
        result.update(
            {
                "quality_review_context": public_review_batch_context(
                    context,
                    batches=batches,
                    review_batch_id=next_id,
                    completed_batch_ids=completed,
                ),
                "next_action": "review_next_coverage_plan_batch",
            }
        )
        return result

    mark_coverage_plan_review_complete(
        run_path,
        candidate_count=sum(len(batch.get("candidates", [])) for batch in batches),
    )
    pending_path.unlink(missing_ok=True)
    target_report = build_coverage_plan_target_report(run_path)
    result.update(
        {
            "review_complete": True,
            "schema_change_plan": schema_change_plan_context(run_path),
            "coverage_plan_target_validation": target_report,
            "next_action": (
                "apply_schema_changes"
                if target_report.get("complete")
                else "revise_invalid_coverage_plan_targets"
            ),
        }
    )
    return result


def auto_complete_empty_coverage_review(
    run_path: Path,
    *,
    agent_config: dict[str, Any] | None = None,
) -> None:
    context = build_coverage_plan_review_context(run_path, agent_config=agent_config)
    write_json(
        run_path / "result" / _REVIEW_FILE,
        {**context, "reviewed_items": [], "changed_requirement_ids": []},
    )
    mark_coverage_plan_review_complete(run_path, candidate_count=0)
    build_coverage_plan_target_report(run_path)


def _review_settings(agent_config: dict[str, Any] | None) -> dict[str, Any]:
    config = agent_config if isinstance(agent_config, dict) else {}
    value = config.get("coverage_plan_review", {})
    value = value if isinstance(value, dict) else {}
    include = value.get("include_classifications", ["no_ui", "cross_cutting_ui", "unclear"])
    include = include if isinstance(include, list) else []
    try:
        shared = int(value.get("shared_target_min_requirements", 4))
    except (TypeError, ValueError):
        shared = 4
    return {
        "include_classifications": [str(item) for item in include],
        "include_page_targets": bool(value.get("include_page_targets", False)),
        "shared_target_min_requirements": max(0, shared),
    }


def _requirement_fields(agent_config: dict[str, Any] | None) -> list[str] | None:
    config = agent_config if isinstance(agent_config, dict) else {}
    context = config.get("context", {})
    fields = context.get("requirement_fields") if isinstance(context, dict) else None
    return [str(item) for item in fields] if isinstance(fields, list) else None
