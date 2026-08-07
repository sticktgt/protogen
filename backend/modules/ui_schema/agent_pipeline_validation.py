from __future__ import annotations

from pathlib import Path
from typing import Iterable

from backend.modules.ui_schema.agent_pipeline_models import (
    PipelineDecision,
    RequirementAnalysisItem,
)
from backend.modules.ui_schema.agent_target_catalog import build_target_catalog


def validate_analysis_batch(
    items: Iterable[RequirementAnalysisItem],
    *,
    expected_requirement_ids: list[str],
) -> list[str]:
    records = list(items)
    errors = _exact_id_errors(
        [item.requirement_id for item in records],
        expected_requirement_ids,
        label="analysis",
    )
    for item in records:
        # Analysis does not choose concrete targets yet, so only effect/classification
        # combinations that are representable without a target are checked here.
        if item.classification == "direct_ui" and item.ui_effect in {"none", "unclear"}:
            errors.append(
                f"{item.requirement_id}: classification=direct_ui требует конкретный наблюдаемый ui_effect"
            )
        elif item.classification == "cross_cutting_ui" and item.ui_effect in {"none", "unclear"}:
            errors.append(
                f"{item.requirement_id}: classification=cross_cutting_ui требует конкретный наблюдаемый ui_effect"
            )
        elif item.classification == "no_ui" and item.ui_effect != "none":
            errors.append(f"{item.requirement_id}: classification=no_ui требует ui_effect=none")
        elif item.classification == "unclear" and item.ui_effect != "unclear":
            errors.append(f"{item.requirement_id}: classification=unclear требует ui_effect=unclear")
        if item.classification in {"direct_ui", "cross_cutting_ui"} and not item.ui_outcomes:
            errors.append(
                f"{item.requirement_id}: для наблюдаемой UI-классификации требуется непустой ui_outcomes"
            )
    return errors


def validate_plan_decisions(
    decisions: Iterable[PipelineDecision],
    *,
    expected_requirement_ids: list[str],
    schema_root: Path,
    validate_actions: bool,
) -> list[str]:
    records = list(decisions)
    errors = _exact_id_errors(
        [item.requirement_id for item in records],
        expected_requirement_ids,
        label="decisions",
    )
    catalog = build_target_catalog(schema_root)
    for item in records:
        consistency = item.consistency_error()
        if consistency:
            errors.append(f"{item.requirement_id}: {consistency}")
        seen_targets: set[tuple[str, str]] = set()
        for target in item.targets:
            key = (target.target_type, target.target_id)
            if key in seen_targets:
                errors.append(
                    f"{item.requirement_id}: цель повторяется: {target.target_type}:{target.target_id}"
                )
                continue
            seen_targets.add(key)
            if not validate_actions:
                continue
            exists = key in catalog
            if target.action in {"reuse", "extend"} and not exists:
                alternate = _alternate_target(catalog, target.target_id)
                suffix = f"; точный ID существует как {alternate}" if alternate else ""
                errors.append(
                    f"{item.requirement_id}: action={target.action} требует существующую "
                    f"цель {target.target_type}:{target.target_id}{suffix}. "
                    "Используй точный существующий ID либо action=create с операцией создания"
                )
            if target.action == "create" and exists:
                errors.append(
                    f"{item.requirement_id}: цель {target.target_type}:{target.target_id} "
                    "уже существует, поэтому action=create недопустим. "
                    "Используй action=reuse без изменений цели либо action=extend, "
                    "если пакет обновляет существующую цель"
                )
    return errors


def validate_final_targets(
    decisions: Iterable[PipelineDecision],
    *,
    schema_root: Path,
) -> list[str]:
    catalog = build_target_catalog(schema_root)
    errors: list[str] = []
    for item in decisions:
        for target in item.targets:
            key = (target.target_type, target.target_id)
            if key in catalog:
                continue
            alternate = _alternate_target(catalog, target.target_id)
            suffix = f"; точный ID существует как {alternate}" if alternate else ""
            errors.append(
                f"{item.requirement_id}: итоговая цель отсутствует: "
                f"{target.target_type}:{target.target_id}{suffix}"
            )
    return errors


def _exact_id_errors(
    actual_ids: list[str],
    expected_ids: list[str],
    *,
    label: str,
) -> list[str]:
    errors: list[str] = []
    actual_set = set(actual_ids)
    expected_set = set(expected_ids)
    duplicates = sorted({item for item in actual_ids if actual_ids.count(item) > 1})
    if duplicates:
        errors.append(f"{label}: повторяющиеся ID требований: {', '.join(duplicates[:20])}")
    missing = [item for item in expected_ids if item not in actual_set]
    outside = [item for item in actual_ids if item not in expected_set]
    if missing:
        errors.append(f"{label}: отсутствуют ID требований: {', '.join(missing[:30])}")
    if outside:
        errors.append(f"{label}: получены посторонние ID требований: {', '.join(outside[:30])}")
    return errors


def _alternate_target(
    catalog: dict[tuple[str, str], dict], target_id: str
) -> str | None:
    matches = sorted(
        f"{target_type}:{candidate_id}"
        for (target_type, candidate_id) in catalog
        if candidate_id == target_id
    )
    return ", ".join(matches) if matches else None
