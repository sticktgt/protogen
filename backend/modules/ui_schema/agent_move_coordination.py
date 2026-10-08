from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_element_batch_tools import (
    PageElementChange,
    PageElementMove,
)
from backend.modules.ui_schema.files import read_json


def coordinate_upserts_with_explicit_moves(
    *,
    working_root: Path,
    upsert_elements: list[PageElementChange | dict[str, Any]],
    move_elements: list[PageElementMove | dict[str, Any]],
) -> list[PageElementChange]:
    """Preflight element placement and coordinate explicitly declared moves.

    Existing elements keep their current parent during the upsert phase. A changed
    parent is accepted only when the same bundle contains a matching move_elements
    operation. All implicit parent changes are reported together so one repair call
    can fix the complete rejected bundle.
    """
    changes = [_as_change(item) for item in upsert_elements]
    moves = _move_map(move_elements)
    if not changes and not moves:
        return []

    parent_cache: dict[str, dict[str, str]] = {}
    errors: list[str] = []
    coordinated: list[PageElementChange] = []
    upsert_keys: set[tuple[str, str]] = set()

    for change in changes:
        key = (change.page_id, change.element.id)
        upsert_keys.add(key)
        parents = parent_cache.setdefault(
            change.page_id,
            _element_parents(working_root, change.page_id),
        )
        current_parent = parents.get(change.element.id)
        move = moves.get(key)

        if current_parent is None:
            if move is not None:
                errors.append(
                    f"Элемент {change.element.id} не существовал до текущего пакета. "
                    f"Создай его сразу внутри {move.new_parent_id} и не добавляй "
                    "в move_elements"
                )
            coordinated.append(change)
            continue

        requested_parent = change.parent_id
        if move is None:
            if requested_parent not in (None, current_parent):
                errors.append(
                    f"Элемент {change.element.id} сейчас находится внутри {current_parent}; "
                    f"upsert_elements не может неявно перенести его в {requested_parent}. "
                    "Сохрани текущего родителя в upsert_elements либо добавь move_elements "
                    "для явной смены родителя"
                )
            coordinated.append(change)
            continue

        if requested_parent not in (None, current_parent, move.new_parent_id):
            errors.append(
                f"Для элемента {change.element.id} заданы противоречивые родители: "
                f"upsert_elements parent_id={requested_parent}, "
                f"текущий родитель={current_parent}, "
                f"move_elements new_parent_id={move.new_parent_id}"
            )
            coordinated.append(change)
            continue

        coordinated.append(change.model_copy(update={"parent_id": None}))

    for key, move in moves.items():
        if key in upsert_keys:
            continue
        parents = parent_cache.setdefault(
            move.page_id,
            _element_parents(working_root, move.page_id),
        )
        if move.element_id not in parents:
            errors.append(
                f"Элемент {move.element_id} не существовал до текущего пакета. "
                f"Создай его сразу внутри {move.new_parent_id} и не добавляй "
                "в move_elements"
            )

    if errors:
        raise ValueError("Некорректные инструкции размещения элементов: " + " | ".join(errors))
    return coordinated


def _as_change(item: PageElementChange | dict[str, Any]) -> PageElementChange:
    if isinstance(item, PageElementChange):
        return item
    return PageElementChange.model_validate(item)


def _move_map(
    items: list[PageElementMove | dict[str, Any]],
) -> dict[tuple[str, str], PageElementMove]:
    result: dict[tuple[str, str], PageElementMove] = {}
    for item in items:
        move = item if isinstance(item, PageElementMove) else PageElementMove.model_validate(item)
        key = (move.page_id, move.element_id)
        if key in result:
            raise ValueError(
                f"Для элемента {move.element_id} указано несколько операций move_elements "
                f"в документе {move.page_id}."
            )
        result[key] = move
    return result


def _element_parents(working_root: Path, page_id: str) -> dict[str, str]:
    path = working_root / ("app.json" if page_id == "app" else f"pages/{page_id}.json")
    document = read_json(path, {})
    if not isinstance(document, dict) or document.get("id") != page_id:
        raise ValueError(f"Документ {page_id} не существует или содержит неверный id")

    field = "root_elements" if page_id == "app" else "elements"
    roots = document.get(field, [])
    if not isinstance(roots, list):
        raise ValueError(f"Document {page_id}.{field} must be a list")

    result: dict[str, str] = {}

    def walk(items: list[Any], parent_id: str) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            element_id = str(item.get("id") or "")
            if element_id:
                result[element_id] = parent_id
                children = item.get("children", [])
                if isinstance(children, list):
                    walk(children, element_id)

    walk(roots, page_id)
    return result
