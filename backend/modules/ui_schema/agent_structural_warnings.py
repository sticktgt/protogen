from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from backend.modules.ui_schema.agent_pipeline_models import PipelineDecision
from backend.modules.ui_schema.agent_pipeline_runtime import PipelineRuntime
from backend.modules.ui_schema.agent_pipeline_values import unique_strings
from backend.modules.ui_schema.agent_structural_candidates import collect_structural_candidates
from backend.modules.ui_schema.files import write_json

_HIGH_SIGNAL_KINDS = {
    "id_container_mismatch",
    "self_navigation",
    "multiple_navigation_targets",
    "new_page_without_incoming_navigation",
    "emptied_existing_container",
    "empty_extended_container",
    "empty_new_container",
}

_KIND_LABELS = {
    "id_container_mismatch": "элементы вне ожидаемого контейнера",
    "self_navigation": "навигация страницы на саму себя",
    "multiple_navigation_targets": "несколько безусловных целей у одного источника навигации",
    "new_page_without_incoming_navigation": "новые страницы без входящей навигации",
    "emptied_existing_container": "существующие контейнеры, опустошённые текущим запуском",
    "empty_extended_container": "контейнеры, заявленные как расширенные, но оставшиеся пустыми",
    "empty_new_container": "новые пустые содержательные контейнеры",
}


def collect_structural_warnings(
    *,
    runtime: PipelineRuntime,
    decisions: list[PipelineDecision],
    maximum_candidates: int,
) -> tuple[list[str], int]:
    """Collect structural candidates without invoking the model or changing the schema."""
    candidates, structural_context = collect_structural_candidates(
        base_root=runtime.run_path / "base" / "ui_schema",
        working_root=runtime.run_path / "working" / "ui_schema",
        decisions=[item.model_dump() for item in decisions],
        maximum_candidates=maximum_candidates,
    )
    warnings = _candidate_warnings(candidates)
    if structural_context.get("truncated"):
        warnings.append(
            "Структурная проверка ограничена первыми "
            f"{len(candidates)} кандидатами из "
            f"{structural_context.get('total_candidate_count', len(candidates))}; "
            "остальные изменения при необходимости можно проверить вручную."
        )
    warnings = unique_strings(warnings)
    write_json(
        runtime.run_path / "result" / "structural_review.json",
        {
            "candidate_count": len(candidates),
            "total_candidate_count": structural_context.get(
                "total_candidate_count", len(candidates)
            ),
            "status": "warnings_only" if candidates else "not_needed",
            "candidates": candidates,
            "warnings": warnings,
        },
    )
    return warnings, len(candidates)


def _candidate_warnings(candidates: Iterable[dict[str, Any]]) -> list[str]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        kind = str(candidate.get("kind") or "")
        if kind in _HIGH_SIGNAL_KINDS:
            grouped[kind].append(candidate)

    warnings: list[str] = []
    for kind in sorted(grouped, key=lambda value: _kind_order(value)):
        items = grouped[kind]
        refs = [_candidate_ref(item) for item in items]
        visible_refs = [value for value in refs if value][:5]
        suffix = ""
        if len(items) > len(visible_refs):
            suffix = f" и ещё {len(items) - len(visible_refs)}"
        details = ", ".join(visible_refs) if visible_refs else f"{len(items)} кандидат(а)"
        warnings.append(
            "Структурная проверка: рекомендуется вручную проверить "
            f"{_KIND_LABELS[kind]}: {details}{suffix}."
        )
    return warnings


def _candidate_ref(candidate: dict[str, Any]) -> str:
    kind = str(candidate.get("kind") or "")
    if kind == "new_page_without_incoming_navigation":
        return str(candidate.get("page_id") or "")
    facts = candidate.get("facts") if isinstance(candidate.get("facts"), dict) else {}
    if kind in {"self_navigation", "multiple_navigation_targets"}:
        link = facts.get("link") if isinstance(facts.get("link"), dict) else {}
        source_id = str(link.get("source_id") or "")
        if source_id:
            return source_id
    element_ids = candidate.get("element_ids")
    if isinstance(element_ids, list) and element_ids:
        return str(element_ids[0] or "")
    return str(candidate.get("candidate_id") or "")


def _kind_order(kind: str) -> int:
    order = [
        "id_container_mismatch",
        "self_navigation",
        "multiple_navigation_targets",
        "new_page_without_incoming_navigation",
        "emptied_existing_container",
        "empty_extended_container",
        "empty_new_container",
    ]
    try:
        return order.index(kind)
    except ValueError:
        return len(order)
