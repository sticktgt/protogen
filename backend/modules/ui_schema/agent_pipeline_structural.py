from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_pipeline_models import (
    PipelineDecision,
    PipelineStructuralReviewOutput,
)
from backend.modules.ui_schema.agent_pipeline_runtime import PipelineRuntime
from backend.modules.ui_schema.agent_pipeline_validation import validate_plan_decisions
from backend.modules.ui_schema.agent_pipeline_values import unique_strings
from backend.modules.ui_schema.agent_structural_candidates import (
    collect_structural_candidates,
)
from backend.modules.ui_schema.agent_structural_navigation_validation import (
    validate_structural_navigation_changes,
)
from backend.modules.ui_schema.agent_target_catalog import build_target_catalog
from backend.modules.ui_schema.files import write_json


def run_structural_review(
    *,
    runtime: PipelineRuntime,
    requirements: list[dict[str, Any]],
    decisions: list[PipelineDecision],
    maximum_candidates: int,
    maximum_apply_repairs: int,
) -> tuple[list[PipelineDecision], list[str], list[str], int]:
    candidates, structural_context = collect_structural_candidates(
        base_root=runtime.run_path / "base" / "ui_schema",
        working_root=runtime.run_path / "working" / "ui_schema",
        decisions=[item.model_dump() for item in decisions],
        maximum_candidates=maximum_candidates,
    )
    if not candidates:
        write_json(
            runtime.run_path / "result" / "structural_review.json",
            {
                "candidate_count": 0,
                "total_candidate_count": 0,
                "status": "not_needed",
                "warnings": [],
            },
        )
        return decisions, [], [], 0

    required_ids = {
        requirement_id
        for candidate in candidates
        for requirement_id in candidate.get("related_requirement_ids", [])
    }
    requirement_by_id = {
        str(item.get("id") or ""): item for item in requirements
    }
    decision_by_id = {item.requirement_id: item for item in decisions}
    review = _invoke_with_apply_repair(
        runtime=runtime,
        base_context={
            "candidates": candidates,
            "structural_context": structural_context,
            "requirements": [
                requirement_by_id[item]
                for item in sorted(required_ids)
                if item in requirement_by_id
            ],
            "current_decisions": [
                decision_by_id[item].model_dump()
                for item in sorted(required_ids)
                if item in decision_by_id
            ],
            "required_requirement_ids": sorted(required_ids),
        },
        candidates=candidates,
        required_ids=required_ids,
        maximum_repairs=maximum_apply_repairs,
    )

    merged = dict(decision_by_id)
    for item in review.decisions:
        merged[item.requirement_id] = item
    ordered = [merged[str(item.get("id") or "")] for item in requirements]
    warnings = list(review.warnings)
    if structural_context.get("truncated"):
        warnings.append(
            "Структурная доводка обработала ограниченное число кандидатов; "
            "оставшиеся изменения можно проверить вручную."
        )
    write_json(
        runtime.run_path / "result" / "structural_review.json",
        {
            "candidate_count": len(candidates),
            "total_candidate_count": structural_context.get(
                "total_candidate_count", len(candidates)
            ),
            "status": "completed",
            "candidates": candidates,
            "output": review.model_dump(),
            "warnings": unique_strings(warnings),
        },
    )
    notes = [review.agent_note] if review.agent_note.strip() else []
    return ordered, notes, unique_strings(warnings), len(candidates)


def validate_structural_review_output(
    output: PipelineStructuralReviewOutput,
    *,
    candidates: list[dict[str, Any]],
    required_ids: set[str],
    schema_root: Path,
) -> list[str]:
    candidate_ids = [str(item.get("candidate_id") or "") for item in candidates]
    resolution_ids = [item.candidate_id for item in output.resolutions]
    errors = _exact_ids(resolution_ids, candidate_ids, label="resolutions")
    errors.extend(
        _exact_ids(
            [item.requirement_id for item in output.decisions],
            sorted(required_ids),
            label="decisions",
        )
    )
    errors.extend(
        validate_plan_decisions(
            output.decisions,
            expected_requirement_ids=sorted(required_ids),
            schema_root=schema_root,
            validate_actions=False,
        )
    )

    candidate_by_id = {
        str(item.get("candidate_id") or ""): item for item in candidates
    }
    allowed_removals = {
        element_id
        for candidate in candidates
        for element_id in candidate.get("new_element_ids", [])
    }
    catalog = build_target_catalog(schema_root)
    existing_element_ids = {
        target_id
        for (target_type, target_id) in catalog
        if target_type == "ui_element"
    }
    allowed_existing_changes = {
        element_id
        for candidate in candidates
        for element_id in candidate.get("affected_element_ids", [])
    }
    allowed_new_parent_ids = {
        str(parent_id)
        for candidate in candidates
        for parent_id in candidate.get("facts", {}).get(
            "allowed_navigation_parent_ids", []
        )
        if str(parent_id)
    }
    upsert_ids = {
        str(change.element.get("id") or "").strip()
        for change in output.changes.upsert_elements
    }
    for change in output.changes.upsert_elements:
        element_id = str(change.element.get("id") or "").strip()
        if element_id in existing_element_ids:
            if element_id not in allowed_existing_changes:
                errors.append(
                    "Структурный upsert_elements изменяет элемент вне кандидатов: "
                    + element_id
                )
            continue
        parent_id = str(change.parent_id or "").strip()
        allowed_new_parents = allowed_existing_changes | allowed_new_parent_ids | upsert_ids
        if not parent_id or parent_id not in allowed_new_parents:
            errors.append(
                f"Новый структурный элемент {element_id} должен иметь родителя "
                "внутри проверяемых кандидатов"
            )

    allowed_move_parents: dict[str, set[str]] = {}
    move_pages: dict[str, str] = {}
    for candidate in candidates:
        kind = candidate.get("kind")
        if kind == "id_container_mismatch":
            allowed_parents = {
                str(item)
                for item in candidate.get("facts", {}).get("allowed_parent_ids", [])
                if str(item)
            }
            for element_id in candidate.get("new_element_ids", []):
                allowed_move_parents[str(element_id)] = allowed_parents
                move_pages[str(element_id)] = str(candidate.get("page_id") or "")
        elif kind == "emptied_existing_container":
            container_id = str(candidate.get("element_ids", [""])[0] or "")
            for element_id in candidate.get("facts", {}).get("moved_out_child_ids", []):
                if container_id and str(element_id):
                    allowed_move_parents[str(element_id)] = {container_id}
                    move_pages[str(element_id)] = str(candidate.get("page_id") or "")
    move_ids: set[str] = set()
    for move in output.changes.move_elements:
        element_id = str(move.element_id or "").strip()
        move_ids.add(element_id)
        if element_id not in allowed_move_parents:
            errors.append(
                "move_elements содержит элемент вне кандидатов размещения: "
                + element_id
            )
            continue
        if move.page_id != move_pages[element_id]:
            errors.append(
                f"Для move_elements элемента {element_id} требуется page_id={move_pages[element_id]}"
            )
        if move.new_parent_id not in allowed_move_parents[element_id]:
            allowed = ", ".join(sorted(allowed_move_parents[element_id]))
            errors.append(
                f"Для move_elements элемента {element_id} требуется родитель внутри "
                f"ожидаемого контейнера: {allowed}"
            )

    changed_link_ids, removed_link_ids, linked_inaccessible_pages = (
        validate_structural_navigation_changes(
            output=output,
            candidates=candidates,
            errors=errors,
        )
    )

    for resolution in output.resolutions:
        candidate = candidate_by_id.get(resolution.candidate_id, {})
        candidate_links = set(candidate.get("link_ids", []))
        candidate_new_links = set(candidate.get("new_link_ids", []))
        if resolution.action == "keep" and (candidate_links & removed_link_ids):
            errors.append(
                f"{resolution.candidate_id}: action=keep противоречит remove_ui_links"
            )
        if resolution.action == "remove":
            if candidate.get("kind") == "self_navigation":
                if not candidate_new_links or not (candidate_new_links & removed_link_ids):
                    errors.append(
                        f"{resolution.candidate_id}: action=remove допустим только для новой UI-связи и требует changes.remove_ui_links"
                    )
            elif candidate.get("kind") == "multiple_navigation_targets":
                errors.append(
                    f"{resolution.candidate_id}: для группы навигационных связей используй action=modify, а лишние новые связи укажи в remove_ui_links"
                )

    removals = set(output.changes.remove_elements)
    outside = sorted(removals - allowed_removals)
    if outside:
        errors.append(
            "remove_elements содержит ID вне структурных кандидатов: "
            + ", ".join(outside)
        )
    for resolution in output.resolutions:
        candidate = candidate_by_id.get(resolution.candidate_id, {})
        candidate_new_ids = set(candidate.get("new_element_ids", []))
        if (
            resolution.action == "remove"
            and candidate_new_ids
            and not (candidate_new_ids & removals)
        ):
            errors.append(
                f"{resolution.candidate_id}: action=remove требует явный ID кандидата "
                "в changes.remove_elements"
            )
        if resolution.action == "keep" and (
            set(candidate.get("element_ids", [])) & removals
        ):
            errors.append(
                f"{resolution.candidate_id}: action=keep противоречит remove_elements"
            )
        if (
            resolution.action == "modify"
            and candidate.get("kind") == "id_container_mismatch"
            and not (candidate_new_ids & move_ids)
        ):
            errors.append(
                f"{resolution.candidate_id}: action=modify требует move_elements"
            )
        if (
            resolution.action == "modify"
            and candidate.get("kind") == "self_navigation"
            and not (set(candidate.get("link_ids", [])) & (changed_link_ids | removed_link_ids))
        ):
            errors.append(
                f"{resolution.candidate_id}: action=modify требует ui_links или remove_ui_links"
            )
        if (
            resolution.action == "modify"
            and candidate.get("kind") == "multiple_navigation_targets"
            and not (set(candidate.get("link_ids", [])) & (changed_link_ids | removed_link_ids))
        ):
            errors.append(
                f"{resolution.candidate_id}: action=modify требует локального изменения ui_links или remove_ui_links"
            )
        if (
            resolution.action == "modify"
            and candidate.get("kind") == "new_page_without_incoming_navigation"
            and str(candidate.get("page_id") or "") not in linked_inaccessible_pages
        ):
            errors.append(
                f"{resolution.candidate_id}: action=modify требует входящую ui_links на новую страницу"
            )
        if (
            resolution.action == "modify"
            and candidate.get("kind") == "emptied_existing_container"
        ):
            container_id = str(candidate.get("element_ids", [""])[0] or "")
            has_container_upsert = container_id in upsert_ids
            has_restoring_move = any(
                str(move.element_id or "") in set(candidate.get("facts", {}).get("moved_out_child_ids", []))
                for move in output.changes.move_elements
            )
            has_new_child = any(
                str(change.parent_id or "") == container_id
                and str(change.element.get("id") or "") not in existing_element_ids
                for change in output.changes.upsert_elements
            )
            if not (has_container_upsert or has_restoring_move or has_new_child):
                errors.append(
                    f"{resolution.candidate_id}: action=modify требует локального изменения опустевшего контейнера"
                )
    return errors


def _invoke_with_apply_repair(
    *,
    runtime: PipelineRuntime,
    base_context: dict[str, Any],
    candidates: list[dict[str, Any]],
    required_ids: set[str],
    maximum_repairs: int,
) -> PipelineStructuralReviewOutput:
    review: PipelineStructuralReviewOutput | None = None
    apply_errors: list[str] = []
    for repair_index in range(maximum_repairs + 1):
        review = runtime.invoke_validated(
            output_model=PipelineStructuralReviewOutput,
            stage="structural_review",
            base_context={
                **base_context,
                "structural_apply_errors": apply_errors,
                "rejected_structural_review": (
                    review.model_dump() if review else None
                ),
            },
            validator=lambda value: validate_structural_review_output(
                value,
                candidates=candidates,
                required_ids=required_ids,
                schema_root=runtime.run_path / "working" / "ui_schema",
            ),
        )
        try:
            runtime.apply_changes(
                review.changes,
                allow_remove_new_elements=True,
                allow_remove_ui_links=True,
            )
            return review
        except (OSError, TypeError, ValueError) as exc:
            apply_errors = [str(exc)]
            if repair_index >= maximum_repairs:
                raise
            runtime.event(
                event_type="pipeline_structural_apply_rejected",
                level="warning",
                message=f"Пакет структурной доводки отклонён: {str(exc)[:600]}",
                data={"repair_attempt": repair_index + 1},
            )
    raise RuntimeError("Structural review stage produced no result")


def _exact_ids(actual: list[str], expected: list[str], *, label: str) -> list[str]:
    errors: list[str] = []
    actual_set = set(actual)
    expected_set = set(expected)
    duplicates = sorted({item for item in actual if actual.count(item) > 1})
    if duplicates:
        errors.append(f"{label}: повторяющиеся ID: {', '.join(duplicates)}")
    missing = [item for item in expected if item not in actual_set]
    outside = [item for item in actual if item not in expected_set]
    if missing:
        errors.append(f"{label}: отсутствуют ID: {', '.join(missing)}")
    if outside:
        errors.append(f"{label}: неизвестные ID: {', '.join(outside)}")
    return errors
