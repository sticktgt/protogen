from __future__ import annotations

from typing import Any

from backend.modules.ui_schema.agent_pipeline_models import PipelineStructuralReviewOutput
from backend.modules.ui_schema.element_types import type_definition


def validate_structural_navigation_changes(
    *,
    output: PipelineStructuralReviewOutput,
    candidates: list[dict[str, Any]],
    errors: list[str],
) -> tuple[set[str], set[str], set[str]]:
    """Validate link edits/removals allowed by bounded structural candidates."""
    editable_links: dict[str, dict[str, Any]] = {}
    removable_link_ids: set[str] = set()
    inaccessible_pages: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        kind = candidate.get("kind")
        removable_link_ids.update(str(item) for item in candidate.get("new_link_ids", []) if str(item))
        if kind == "self_navigation":
            link = candidate.get("facts", {}).get("link", {})
            _register_link(editable_links, link, candidate)
        elif kind == "multiple_navigation_targets":
            for link in candidate.get("facts", {}).get("links", []):
                _register_link(editable_links, link, candidate)
        elif kind == "new_page_without_incoming_navigation":
            page_id = str(
                candidate.get("facts", {}).get("page_id")
                or candidate.get("page_id")
                or ""
            )
            if page_id:
                inaccessible_pages[page_id] = candidate

    removed_link_ids = set(output.changes.remove_ui_links)
    outside_removals = sorted(removed_link_ids - removable_link_ids)
    if outside_removals:
        errors.append(
            "remove_ui_links содержит ID вне новых связей структурных кандидатов: "
            + ", ".join(outside_removals)
        )

    upsert_by_id = {
        str(change.element.get("id") or "").strip(): change
        for change in output.changes.upsert_elements
        if str(change.element.get("id") or "").strip()
    }
    changed_link_ids: set[str] = set()
    linked_inaccessible_pages: set[str] = set()
    for link in output.changes.ui_links:
        link_id = str(link.id or "").strip()
        if link_id:
            changed_link_ids.add(link_id)
        if link_id and link_id in editable_links:
            _validate_existing_candidate_link_change(
                link=link,
                original=editable_links[link_id],
                errors=errors,
            )
            continue

        target_page_id = str(link.target_id or "")
        candidate = inaccessible_pages.get(target_page_id)
        if (
            candidate is None
            or link.relation != "navigates_to"
            or link.target_type not in (None, "page")
        ):
            errors.append(
                "ui_links содержит связь вне структурных кандидатов: "
                + (link_id or f"{link.source_id}->{link.target_id}")
            )
            continue
        if _valid_new_page_navigation(
            link=link,
            candidate=candidate,
            upsert_by_id=upsert_by_id,
            errors=errors,
        ):
            linked_inaccessible_pages.add(target_page_id)
    return changed_link_ids, removed_link_ids, linked_inaccessible_pages


def _register_link(
    target: dict[str, dict[str, Any]],
    link: Any,
    candidate: dict[str, Any],
) -> None:
    if not isinstance(link, dict):
        return
    link_id = str(link.get("id") or "")
    if not link_id:
        return
    target[link_id] = {
        "link": link,
        "kind": str(candidate.get("kind") or ""),
        "source_page_id": str(candidate.get("facts", {}).get("source_page_id") or ""),
    }


def _validate_existing_candidate_link_change(
    *,
    link: Any,
    original: dict[str, Any],
    errors: list[str],
) -> None:
    stored = original["link"]
    link_id = str(link.id or "")
    if (
        link.source_type != stored.get("source_type")
        or link.source_id != stored.get("source_id")
        or link.relation != stored.get("relation")
    ):
        errors.append(
            f"Для структурного кандидата {link_id} через ui_links можно изменить только цель"
        )
    if (
        original.get("kind") == "self_navigation"
        and link.target_type == "page"
        and link.target_id == original["source_page_id"]
    ):
        errors.append(
            f"Кандидат ui_links {link_id} по-прежнему ведёт на собственную страницу"
        )


def _valid_new_page_navigation(
    *,
    link: Any,
    candidate: dict[str, Any],
    upsert_by_id: dict[str, Any],
    errors: list[str],
) -> bool:
    target_page_id = str(link.target_id or "")
    if link.source_type not in (None, "ui_element"):
        errors.append(
            f"Для новой страницы {target_page_id} структурная навигация должна исходить от ui_element"
        )
        return False
    facts = candidate.get("facts", {})
    allowed_existing_sources = {
        str(item)
        for item in facts.get("existing_navigation_source_ids", [])
        if str(item)
    }
    allowed_parent_ids = {
        str(item)
        for item in facts.get("allowed_navigation_parent_ids", [])
        if str(item)
    }
    source_id = str(link.source_id or "")
    if source_id in allowed_existing_sources:
        return True

    upsert = upsert_by_id.get(source_id)
    if upsert is None:
        errors.append(
            f"Источник {source_id} для новой страницы {target_page_id} должен быть существующим пунктом навигации кандидата или новым элементом текущей доводки"
        )
        return False
    source_type_id = str(upsert.element.get("type") or "")
    definition = type_definition(source_type_id) or {}
    if definition.get("link_source") is not True:
        errors.append(
            f"Новый источник {source_id} типа {source_type_id} не поддерживает UI-связи"
        )
        return False
    if str(upsert.parent_id or "") not in allowed_parent_ids:
        errors.append(
            f"Новый источник {source_id} для страницы {target_page_id} должен находиться внутри разрешённого контейнера навигации"
        )
        return False
    return True
