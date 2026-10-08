from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from backend.modules.ui_schema.agent_requirement_batches import configured_requirement_fields
from backend.modules.ui_schema.agent_requirement_scope import compact_requirements
from backend.modules.ui_schema.agent_target_catalog import build_target_catalog, target_summary
from backend.modules.ui_schema.agent_traceability_items import read_traceability_items
from backend.modules.ui_schema.files import read_json


def build_traceability_correction_context(
    run_path: Path,
    *,
    agent_config: dict[str, Any] | None,
    validation: dict[str, Any] | None = None,
    requirement_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    ids = _correction_ids(run_path, validation=validation, requirement_ids=requirement_ids)
    if not ids:
        return {}

    requirements = {
        str(item.get("id") or ""): item
        for item in compact_requirements(
            run_path,
            fields=configured_requirement_fields(agent_config),
        )
        if str(item.get("id") or "")
    }
    current_items = read_traceability_items(run_path / "result")
    catalog = build_target_catalog(run_path / "working" / "ui_schema")

    items: list[dict[str, Any]] = []
    for requirement_id in ids:
        current = dict(current_items.get(requirement_id, {}))
        targets: list[dict[str, Any]] = []
        for target in current.get("targets", []) if isinstance(current, dict) else []:
            if not isinstance(target, dict):
                continue
            target_type = str(target.get("target_type") or "")
            target_id = str(target.get("target_id") or "")
            summary = target_summary(
                catalog,
                target_type=target_type,
                target_id=target_id,
            )
            alternatives = []
            for alternative_type in ("page", "ui_element"):
                if alternative_type == target_type:
                    continue
                alternative = target_summary(
                    catalog,
                    target_type=alternative_type,
                    target_id=target_id,
                )
                if alternative.get("exists"):
                    alternatives.append(alternative)
            targets.append(
                {
                    "current_target": dict(target),
                    "target_summary": summary,
                    "same_id_alternatives": alternatives,
                }
            )
        items.append(
            {
                "requirement": requirements.get(requirement_id, {"id": requirement_id}),
                "current_traceability": current,
                "current_target_checks": targets,
            }
        )

    return {
        "policy": {
            "backend_selects_ids_from_technical_errors_only": True,
            "llm_rewrites_complete_items": True,
            "backend_does_not_choose_targets_or_classification": True,
        },
        "requirement_ids": ids,
        "items": items,
        "instruction": (
            "Перепиши ровно эти требования через write_ui_schema_traceability_batch без batch_id. "
            "Верни один полный TraceabilityItem на требование. Исправь target_type/target_id, "
            "если нужная цель уже существует. Меняй схему только когда требованию действительно "
            "нужен отсутствующий UI-объект; после такого изменения перепиши все requirement ID, "
            "возвращённые как dirty."
        ),
    }


def dirty_requirement_ids(run_path: Path) -> list[str]:
    state = read_json(run_path / "result" / "traceability_dirty.json", {})
    return sorted(
        {
            str(item).strip()
            for item in state.get("requirement_ids", [])
            if str(item).strip()
        }
    )


def _correction_ids(
    run_path: Path,
    *,
    validation: dict[str, Any] | None,
    requirement_ids: Iterable[str] | None,
) -> list[str]:
    result = set(dirty_requirement_ids(run_path))
    result.update(str(item).strip() for item in (requirement_ids or []) if str(item).strip())
    source = validation if isinstance(validation, dict) else read_json(
        run_path / "result" / "validation_preview.json", {}
    )
    for hint in source.get("repair_hints", []) if isinstance(source, dict) else []:
        if not isinstance(hint, dict):
            continue
        if str(hint.get("kind") or "") != "missing_requirement_link_target":
            continue
        requirement_id = str(hint.get("requirement_id") or "").strip()
        if requirement_id:
            result.add(requirement_id)
    return sorted(result)
