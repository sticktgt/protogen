from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.modules.ui_schema.agent_preflight_issues import preflight_issue
from backend.modules.ui_schema.agent_preflight_state import (
    VirtualSchema,
    validate_virtual_placement,
)
from backend.modules.ui_schema.element_types import is_root_allowed


def collect_move_issues(
    state: VirtualSchema,
    *,
    move_elements: list[Any],
    issues: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for index, raw in enumerate(move_elements):
        item = raw.model_dump(exclude_none=True) if isinstance(raw, BaseModel) else dict(raw)
        page_id = str(item.get("page_id") or "").strip()
        element_id = str(item.get("element_id") or "").strip()
        new_parent_id = str(item.get("new_parent_id") or "").strip()
        key = (page_id, element_id)
        if not page_id or not element_id or not new_parent_id:
            issues.append(
                preflight_issue(
                    "invalid_move",
                    f"move_elements[{index}] должен содержать page_id, element_id и new_parent_id",
                )
            )
            continue
        if key in result:
            issues.append(
                preflight_issue(
                    "duplicate_move",
                    f"Для элемента {element_id} указано несколько операций move_elements",
                    page_id=page_id,
                    element_id=element_id,
                )
            )
            continue
        result[key] = item
        record = state.elements.get(element_id)
        if record is None or element_id not in state.initial_element_ids:
            issues.append(
                preflight_issue(
                    "move_new_or_missing_element",
                    f"Элемент {element_id} не существовал до текущего пакета; создай его сразу у нужного родителя без move_elements",
                    page_id=page_id,
                    element_id=element_id,
                    requested_parent_id=new_parent_id,
                )
            )
        elif str(record.get("page_id") or "") != page_id:
            issues.append(
                preflight_issue(
                    "move_wrong_document",
                    f"Элемент {element_id} находится в документе {record.get('page_id')}, а move_elements указывает {page_id}",
                    page_id=page_id,
                    element_id=element_id,
                )
            )
    return result


def collect_upsert_issues(
    state: VirtualSchema,
    *,
    upsert_elements: list[dict[str, Any]],
    move_map: dict[tuple[str, str], dict[str, Any]],
    issues: list[dict[str, Any]],
) -> None:
    _register_new_upsert_ids(state, upsert_elements=upsert_elements, issues=issues)
    for item in upsert_elements:
        page_id = str(item.get("page_id") or "").strip()
        element = item.get("element") if isinstance(item.get("element"), dict) else {}
        element_id = str(element.get("id") or "").strip()
        if not page_id or not element_id:
            issues.append(
                preflight_issue(
                    "invalid_upsert",
                    "Каждый upsert_elements должен содержать page_id и element.id",
                )
            )
            continue
        record = state.elements.get(element_id)
        if record is None:
            continue
        current_parent = str(record.get("parent_id") or "")
        raw_parent = item.get("parent_id")
        requested_parent = (
            str(raw_parent).strip() if raw_parent not in (None, "") else None
        )
        move = move_map.get((page_id, element_id))
        existed_before = element_id in state.initial_element_ids
        final_parent = _resolve_final_parent(
            state=state,
            page_id=page_id,
            element_id=element_id,
            type_id=str(element.get("type") or record.get("type") or ""),
            current_parent=current_parent,
            requested_parent=requested_parent,
            move=move,
            existed_before=existed_before,
            issues=issues,
        )
        record["parent_id"] = final_parent
        record["type"] = str(element.get("type") or record.get("type") or "")
        record["label"] = str(element.get("label") or record.get("label") or "")
        validate_virtual_placement(
            state=state,
            element_id=element_id,
            page_id=page_id,
            parent_id=final_parent,
            type_id=str(record.get("type") or ""),
            issues=issues,
        )


def collect_move_target_issues(
    state: VirtualSchema,
    *,
    move_map: dict[tuple[str, str], dict[str, Any]],
    issues: list[dict[str, Any]],
) -> None:
    for (page_id, element_id), move in move_map.items():
        record = state.elements.get(element_id)
        if record is None or element_id not in state.initial_element_ids:
            continue
        new_parent_id = str(move.get("new_parent_id") or "")
        if new_parent_id == element_id:
            issues.append(
                preflight_issue(
                    "move_into_self",
                    f"Элемент {element_id} нельзя переместить внутрь самого себя",
                    page_id=page_id,
                    element_id=element_id,
                )
            )
            continue
        record["parent_id"] = new_parent_id
        validate_virtual_placement(
            state=state,
            element_id=element_id,
            page_id=page_id,
            parent_id=new_parent_id,
            type_id=str(record.get("type") or ""),
            issues=issues,
        )
    _collect_move_cycle_issues(state, move_map=move_map, issues=issues)


def _collect_move_cycle_issues(
    state: VirtualSchema,
    *,
    move_map: dict[tuple[str, str], dict[str, Any]],
    issues: list[dict[str, Any]],
) -> None:
    for page_id, element_id in move_map:
        seen = {element_id}
        parent_id = str((state.elements.get(element_id) or {}).get("parent_id") or "")
        while parent_id and parent_id != page_id:
            if parent_id in seen:
                issues.append(
                    preflight_issue(
                        "move_cycle",
                        f"Перемещение элемента {element_id} создаёт циклическую иерархию через {parent_id}",
                        page_id=page_id,
                        element_id=element_id,
                        cycle_parent_id=parent_id,
                    )
                )
                break
            seen.add(parent_id)
            parent = state.elements.get(parent_id)
            if parent is None or str(parent.get("page_id") or "") != page_id:
                break
            parent_id = str(parent.get("parent_id") or "")


def _register_new_upsert_ids(
    state: VirtualSchema,
    *,
    upsert_elements: list[dict[str, Any]],
    issues: list[dict[str, Any]],
) -> None:
    for item in upsert_elements:
        page_id = str(item.get("page_id") or "").strip()
        element = item.get("element") if isinstance(item.get("element"), dict) else {}
        element_id = str(element.get("id") or "").strip()
        if not page_id or not element_id:
            continue
        if page_id != "app" and page_id not in state.pages:
            issues.append(
                preflight_issue(
                    "upsert_page_missing",
                    f"Документ {page_id} отсутствует; сначала создай страницу в create_pages",
                    page_id=page_id,
                    element_id=element_id,
                )
            )
            continue
        existing = state.elements.get(element_id)
        if existing is not None and str(existing.get("page_id") or "") != page_id:
            issues.append(
                preflight_issue(
                    "element_wrong_document",
                    f"Элемент {element_id} уже существует в документе {existing.get('page_id')}, а upsert_elements указывает {page_id}",
                    page_id=page_id,
                    element_id=element_id,
                )
            )
            continue
        if existing is None:
            state.elements[element_id] = {
                "id": element_id,
                "page_id": page_id,
                "parent_id": "",
                "type": str(element.get("type") or ""),
                "label": str(element.get("label") or ""),
                "created_in_bundle": True,
            }


def _resolve_final_parent(
    *,
    state: VirtualSchema,
    page_id: str,
    element_id: str,
    type_id: str,
    current_parent: str,
    requested_parent: str | None,
    move: dict[str, Any] | None,
    existed_before: bool,
    issues: list[dict[str, Any]],
) -> str:
    if existed_before:
        return _existing_element_parent(
            page_id=page_id,
            element_id=element_id,
            current_parent=current_parent,
            requested_parent=requested_parent,
            move=move,
            issues=issues,
        )
    if move is not None:
        return str(move.get("new_parent_id") or "")
    if requested_parent:
        return requested_parent
    if page_id != "app":
        return page_id
    try:
        if is_root_allowed(type_id, scope="app"):
            return "app"
    except ValueError:
        pass
    issues.append(
        preflight_issue(
            "new_element_parent_missing",
            f"Новый app-элемент {element_id} требует точный parent_id или root_allowed тип",
            page_id=page_id,
            element_id=element_id,
        )
    )
    return ""


def _existing_element_parent(
    *,
    page_id: str,
    element_id: str,
    current_parent: str,
    requested_parent: str | None,
    move: dict[str, Any] | None,
    issues: list[dict[str, Any]],
) -> str:
    if move is None:
        if requested_parent not in (None, current_parent):
            issues.append(
                preflight_issue(
                    "implicit_parent_change",
                    (
                        f"Элемент {element_id} сейчас находится внутри {current_parent}; "
                        f"upsert_elements не может неявно перенести его в {requested_parent}. "
                        "Сохрани текущего родителя либо добавь move_elements, если перенос действительно нужен"
                    ),
                    page_id=page_id,
                    element_id=element_id,
                    current_parent_id=current_parent,
                    requested_parent_id=requested_parent,
                    allowed_fixes=["keep_current_parent", "move_elements"],
                )
            )
        return current_parent

    new_parent = str(move.get("new_parent_id") or "")
    if requested_parent not in (None, current_parent, new_parent):
        issues.append(
            preflight_issue(
                "conflicting_parent_instructions",
                (
                    f"Для элемента {element_id} заданы противоречивые родители: "
                    f"текущий={current_parent}, upsert_elements={requested_parent}, "
                    f"move_elements={new_parent}"
                ),
                page_id=page_id,
                element_id=element_id,
                current_parent_id=current_parent,
                requested_parent_id=requested_parent,
                move_parent_id=new_parent,
            )
        )
    return new_parent
