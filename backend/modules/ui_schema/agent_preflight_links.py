from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.modules.ui_schema.agent_preflight_issues import preflight_issue
from backend.modules.ui_schema.agent_preflight_state import VirtualSchema
from backend.modules.ui_schema.element_types import type_definition


def collect_link_issues(
    state: VirtualSchema,
    *,
    ui_links: list[Any],
    issues: list[dict[str, Any]],
) -> None:
    seen_ids: set[str] = set()
    seen_signatures: set[tuple[str, str, str, str, str]] = set()
    for index, raw in enumerate(ui_links):
        item = raw.model_dump(exclude_none=True) if isinstance(raw, BaseModel) else dict(raw)
        source_id = str(item.get("source_id") or "").strip()
        target_id = str(item.get("target_id") or "").strip()
        relation = str(item.get("relation") or "").strip()
        source_type = str(item.get("source_type") or "").strip() or _infer_target_type(
            state, source_id
        )
        target_type = str(item.get("target_type") or "").strip() or _infer_target_type(
            state, target_id
        )
        link_id = str(item.get("id") or "").strip()
        _check_duplicate_link(
            link_id=link_id,
            signature=(source_type, source_id, target_type, target_id, relation),
            seen_ids=seen_ids,
            seen_signatures=seen_signatures,
            issues=issues,
        )
        _check_link_source(
            state=state,
            index=index,
            link_id=link_id,
            source_type=source_type,
            source_id=source_id,
            issues=issues,
        )
        _check_link_target(
            state=state,
            index=index,
            link_id=link_id,
            target_type=target_type,
            target_id=target_id,
            relation=relation,
            issues=issues,
        )
        if relation not in {"navigates_to", "opens_modal"}:
            issues.append(
                preflight_issue(
                    "link_relation_not_allowed",
                    f"UI-связь {link_id or index} использует неподдерживаемый relation={relation}",
                    link_id=link_id,
                    relation=relation,
                )
            )


def _check_duplicate_link(
    *,
    link_id: str,
    signature: tuple[str, str, str, str, str],
    seen_ids: set[str],
    seen_signatures: set[tuple[str, str, str, str, str]],
    issues: list[dict[str, Any]],
) -> None:
    if link_id:
        if link_id in seen_ids:
            issues.append(
                preflight_issue(
                    "duplicate_link_id",
                    f"Повторяющийся id UI-связи: {link_id}",
                    link_id=link_id,
                )
            )
        seen_ids.add(link_id)
    if signature in seen_signatures:
        source_type, source_id, target_type, target_id, relation = signature
        issues.append(
            preflight_issue(
                "duplicate_link",
                f"Пакет повторяет одну UI-связь: {source_type}:{source_id} -> {target_type}:{target_id} ({relation})",
                source_id=source_id,
                target_id=target_id,
                relation=relation,
            )
        )
    seen_signatures.add(signature)


def _check_link_source(
    *,
    state: VirtualSchema,
    index: int,
    link_id: str,
    source_type: str,
    source_id: str,
    issues: list[dict[str, Any]],
) -> None:
    if not source_type or not state.target_exists(source_type, source_id):
        issues.append(
            preflight_issue(
                "link_source_missing",
                f"UI-связь {link_id or index} имеет отсутствующий источник: {source_type or '?'}:{source_id}",
                link_id=link_id,
                source_type=source_type,
                source_id=source_id,
            )
        )
        return
    if source_type != "ui_element":
        return
    source = state.elements.get(source_id) or {}
    definition = type_definition(str(source.get("type") or "")) or {}
    if definition.get("link_source") is not True:
        issues.append(
            preflight_issue(
                "link_source_not_allowed",
                f"Элемент {source_id} не может быть источником UI-связи",
                link_id=link_id,
                source_type=source_type,
                source_id=source_id,
                source_element_type=str(source.get("type") or ""),
            )
        )


def _check_link_target(
    *,
    state: VirtualSchema,
    index: int,
    link_id: str,
    target_type: str,
    target_id: str,
    relation: str,
    issues: list[dict[str, Any]],
) -> None:
    if not target_type or not state.target_exists(target_type, target_id):
        issues.append(
            preflight_issue(
                "link_target_missing",
                f"UI-связь {link_id or index} ведёт на отсутствующую цель: {target_type or '?'}:{target_id}",
                link_id=link_id,
                target_type=target_type,
                target_id=target_id,
            )
        )
        return
    if relation == "opens_modal" and target_type == "ui_element":
        target = state.elements.get(target_id) or {}
        if str(target.get("type") or "") != "modal":
            issues.append(
                preflight_issue(
                    "modal_target_required",
                    f"Цель UI-связи {link_id or index} с relation=opens_modal должна иметь тип modal",
                    link_id=link_id,
                    target_id=target_id,
                )
            )


def _infer_target_type(state: VirtualSchema, target_id: str) -> str:
    in_pages = target_id in state.pages
    in_elements = target_id in state.elements
    if in_pages and not in_elements:
        return "page"
    if in_elements and not in_pages:
        return "ui_element"
    return ""
