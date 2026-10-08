from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.ui_schema.agent_json_arguments import parse_json_array

from backend.modules.ui_schema.agent_completion import validate_and_mark_completion
from backend.modules.ui_schema.agent_requirement_decisions import (
    TraceabilityItem,
    validate_decision_consistency,
)
from backend.modules.ui_schema.agent_requirement_scope import compact_requirements
from backend.modules.ui_schema.agent_review_batches import (
    build_review_batches,
    candidate_id,
    next_review_batch_id,
    public_review_batch_context,
    review_batch_by_id,
)
from backend.modules.ui_schema.agent_target_catalog import build_target_catalog, target_summary
from backend.modules.ui_schema.agent_traceability import write_traceability_chunk
from backend.modules.ui_schema.agent_traceability_models import traceability_items_to_storage
from backend.modules.ui_schema.agent_traceability_items import (
    read_traceability_items,
    write_traceability_items,
)
from backend.modules.ui_schema.agent_traceability_review_state import mark_traceability_review_complete
from backend.modules.ui_schema.agent_traceability_correction import build_traceability_correction_context
from backend.modules.ui_schema.files import read_json, write_json

_REVIEW_FILE = "traceability_review.json"
_STATE_FILE = "traceability_state.json"


class TraceabilityReviewArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[TraceabilityItem] = Field(
        min_length=1,
        description=(
            "Fresh complete final traceability decisions for any unresolved candidates in "
            "the current blind review group. The backend infers the group and keeps valid items."
        ),
    )
    agent_note: str = Field(default="")

    @field_validator("items", mode="before")
    @classmethod
    def _decode_json_arrays(cls, value: Any) -> Any:
        return parse_json_array(value)


def build_traceability_review_context(
    run_path: Path,
    *,
    agent_config: dict[str, Any] | None,
) -> dict[str, Any]:
    plan = read_json(run_path / "result" / "coverage_plan.json", {})
    planned = {
        str(item.get("requirement_id") or ""): dict(item)
        for item in plan.get("items", [])
        if isinstance(item, dict) and str(item.get("requirement_id") or "")
    }
    final_items = read_traceability_items(run_path / "result")
    final = {
        requirement_id: {
            "classification": str(item.get("classification") or ""),
            "ui_effect": str(item.get("ui_effect") or ""),
            "links": [dict(target) for target in item.get("targets", []) if isinstance(target, dict)],
            "reason": str(item.get("reason") or ""),
        }
        for requirement_id, item in final_items.items()
    }
    requirements = {
        str(item.get("id") or ""): item
        for item in compact_requirements(run_path, fields=_requirement_fields(agent_config))
        if str(item.get("id") or "")
    }
    settings = _review_settings(agent_config)
    execution = read_json(run_path / "result" / "coverage_plan_execution.json", {})
    execution_observation_ids = {
        str(item.get("requirement_id") or "").strip()
        for item in execution.get("observations", [])
        if isinstance(item, dict) and str(item.get("requirement_id") or "").strip()
    }
    catalog = build_target_catalog(run_path / "working" / "ui_schema")
    target_counts = Counter(
        (str(link.get("target_type") or ""), str(link.get("target_id") or ""))
        for entry in final.values()
        for link in entry.get("links", [])
        if isinstance(link, dict) and str(link.get("target_id") or "")
    )

    candidates: list[dict[str, Any]] = []
    included_classes = set(settings["include_classifications"])
    shared_minimum = int(settings["shared_target_min_requirements"])
    for requirement_id, entry in final.items():
        signals: list[str] = []
        classification = str(entry.get("classification") or "")
        entry_links = [dict(link) for link in entry.get("links", []) if isinstance(link, dict)]
        summaries = [
            target_summary(
                catalog,
                target_type=str(link.get("target_type") or ""),
                target_id=str(link.get("target_id") or ""),
            )
            for link in entry_links
        ]
        if classification in included_classes:
            signals.append("model_selected_configured_review_class")
        if settings["include_page_targets"] and any(
            str(link.get("target_type") or "") == "page" for link in entry_links
        ):
            signals.append("model_selected_page_target")
        if settings["include_implemented_empty_groups"]:
            for link, summary in zip(entry_links, summaries):
                if str(link.get("implementation_status") or "") != "implemented":
                    continue
                if not bool(summary.get("exists")):
                    signals.append("implemented_target_missing")
                    break
                if summary.get("element_kind") == "group" and int(summary.get("child_count", 0)) == 0:
                    signals.append("implemented_target_is_empty_group")
                    break
        if settings["include_plan_changes"] and _plan_signature(planned.get(requirement_id)) != _final_signature(entry):
            signals.append("final_differs_from_reviewed_plan")
        if settings["include_execution_observations"] and requirement_id in execution_observation_ids:
            signals.append("coverage_execution_observation")
        if shared_minimum > 1 and any(
            target_counts[(str(link.get("target_type") or ""), str(link.get("target_id") or ""))]
            >= shared_minimum
            for link in entry_links
        ):
            signals.append("model_selected_highly_shared_target")
        if not signals:
            continue
        candidates.append(
            {
                "requirement": requirements.get(requirement_id, {}),
                "selection_signals": signals,
                "target_facts": summaries,
            }
        )

    return {
        "policy": {
            "selection_is_structural_only": True,
            "backend_does_not_judge_requirement_meaning": True,
            "original_final_decision_is_hidden": True,
            "review_returns_fresh_complete_items": True,
        },
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def review_traceability(
    run_path: Path,
    *,
    working_root: Path,
    result_root: Path,
    agent_config: dict[str, Any] | None,
    items: list[TraceabilityItem | dict[str, Any]],
    agent_note: str = "",
) -> dict[str, Any]:
    pending_path = result_root / "traceability_review_pending.json"
    context = read_json(pending_path, {})
    if not isinstance(context, dict) or not isinstance(context.get("candidates"), list):
        context = build_traceability_review_context(run_path, agent_config=agent_config)
    batches = build_review_batches(context, agent_config=agent_config, prefix="traceability_review")
    state_path = result_root / _STATE_FILE
    state = read_json(state_path, {})
    completed = {
        str(item)
        for item in state.get("review_completed_batch_ids", [])
        if str(item).strip()
    }
    expected_id = next_review_batch_id(batches, completed_batch_ids=completed)
    if expected_id is None:
        raise ValueError("Traceability review is already complete")
    current_batch = review_batch_by_id(batches, review_batch_id=expected_id)
    candidate_ids = {
        candidate_id(item)
        for item in current_batch.get("candidates", [])
        if candidate_id(item)
    }

    existing_review = read_json(result_root / _REVIEW_FILE, {})
    reviewed_by_batch = {
        str(key): {str(item) for item in value if str(item).strip()}
        for key, value in (existing_review.get("reviewed_candidate_ids_by_batch", {}) or {}).items()
        if isinstance(value, list)
    }
    already_reviewed = reviewed_by_batch.get(expected_id, set())

    before = read_traceability_items(result_root)
    accepted: list[TraceabilityItem] = []
    item_errors: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in items:
        item = raw if isinstance(raw, TraceabilityItem) else TraceabilityItem.model_validate(raw)
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
        accepted.append(item)

    write_result: dict[str, Any] = {"ok": not item_errors}
    if accepted:
        requirement_ui_links, agent_report = traceability_items_to_storage(
            accepted,
            agent_note=agent_note,
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
            reset=False,
        )

    after = read_traceability_items(result_root)
    accepted_ids = {item.requirement_id for item in accepted}
    reviewed_now = already_reviewed | accepted_ids
    remaining_after = candidate_ids - reviewed_now
    changed_ids = sorted(
        requirement_id
        for requirement_id in accepted_ids
        if _entry_signature(before.get(requirement_id)) != _entry_signature(after.get(requirement_id))
    )

    reviewed_by_batch[expected_id] = reviewed_now
    if not remaining_after:
        completed.add(expected_id)
    next_id = next_review_batch_id(batches, completed_batch_ids=completed)
    reviewed_items = [
        *[dict(item) for item in existing_review.get("reviewed_items", []) if isinstance(item, dict)],
        *[item.model_dump(exclude_none=True) for item in accepted],
    ]
    all_changed = sorted(
        set(str(item) for item in existing_review.get("changed_requirement_ids", []))
        | set(changed_ids)
    )
    write_json(
        result_root / _REVIEW_FILE,
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
    write_json(state_path, {**state, "review_completed_batch_ids": sorted(completed)})

    result: dict[str, Any] = {
        **write_result,
        "ok": True,
        "partial": bool(item_errors),
        "review_batch_id": expected_id,
        "accepted_in_call": len(accepted),
        "reviewed_in_batch": len(reviewed_now),
        "remaining_in_batch": len(remaining_after),
        "changed_requirements": len(changed_ids),
        "item_errors": item_errors,
        "review_complete": False,
        "completed": False,
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
                "next_action": "review_remaining_traceability_candidates",
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
                "next_action": "review_next_traceability_batch",
            }
        )
        return result

    mark_traceability_review_complete(
        run_path,
        candidate_count=sum(len(batch.get("candidates", [])) for batch in batches),
    )
    pending_path.unlink(missing_ok=True)
    validation = validate_and_mark_completion(
        run_path,
        completed_by="review_ui_schema_traceability",
    )
    correction_context = (
        {}
        if validation.get("valid")
        else build_traceability_correction_context(
            run_path,
            agent_config=agent_config,
            validation=validation,
        )
    )
    result.update(
        {
            **validation,
            "review_complete": True,
            "traceability_correction_context": correction_context or None,
            "completed": bool(validation.get("valid")),
            "next_action": (
                "stop"
                if validation.get("valid")
                else "rewrite_invalid_traceability_items"
                if correction_context
                else "fix_errors_and_continue"
            ),
        }
    )
    return result


def mark_empty_traceability_review_complete(run_path: Path) -> None:
    result_root = run_path / "result"
    context = {"policy": {}, "candidate_count": 0, "candidates": []}
    write_json(
        result_root / _REVIEW_FILE,
        {**context, "reviewed_items": [], "changed_requirement_ids": []},
    )
    mark_traceability_review_complete(run_path, candidate_count=0)


def _plan_signature(item: Any) -> tuple[str, str, tuple[str, ...]]:
    if not isinstance(item, dict):
        return "", "", ()
    return (
        str(item.get("classification") or ""),
        str(item.get("ui_effect") or ""),
        tuple(
            sorted(
                str(target.get("target_id") or "")
                for target in item.get("targets", [])
                if isinstance(target, dict) and str(target.get("target_id") or "")
            )
        ),
    )


def _final_signature(entry: dict[str, Any]) -> tuple[str, str, tuple[str, ...]]:
    return (
        str(entry.get("classification") or ""),
        str(entry.get("ui_effect") or ""),
        tuple(
            sorted(
                str(link.get("target_id") or "")
                for link in entry.get("links", [])
                if isinstance(link, dict) and str(link.get("target_id") or "")
            )
        ),
    )


def _entry_signature(entry: Any) -> str:
    import json

    return json.dumps(entry or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _requirement_fields(agent_config: dict[str, Any] | None) -> list[str] | None:
    config = agent_config if isinstance(agent_config, dict) else {}
    context = config.get("context", {})
    fields = context.get("requirement_fields") if isinstance(context, dict) else None
    if not isinstance(fields, list):
        return None
    return [str(item) for item in fields if str(item).strip()]


def _review_settings(agent_config: dict[str, Any] | None) -> dict[str, Any]:
    config = agent_config if isinstance(agent_config, dict) else {}
    analysis = config.get("requirement_analysis", {})
    review = analysis.get("traceability_review", {}) if isinstance(analysis, dict) else {}
    included = review.get("include_classifications", [])
    return {
        "include_classifications": [str(item) for item in included if str(item).strip()]
        if isinstance(included, list)
        else [],
        "include_page_targets": bool(review.get("include_page_targets", True)),
        "include_implemented_empty_groups": bool(
            review.get("include_implemented_empty_groups", True)
        ),
        "include_plan_changes": bool(review.get("include_plan_changes", True)),
        "include_execution_observations": bool(
            review.get("include_execution_observations", True)
        ),
        "shared_target_min_requirements": _positive_int(
            review.get("shared_target_min_requirements"), 0
        ),
    }


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
