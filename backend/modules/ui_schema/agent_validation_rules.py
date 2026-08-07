from __future__ import annotations

from typing import Any

from backend.modules.ui_schema.element_types import (
    allowed_child_types,
    allowed_parent_types,
    ensure_type_allowed,
    is_root_allowed,
    root_type_ids,
    type_definition,
)


SUPPORTED_REQUIREMENT_LINK_RELATIONS = frozenset(
    {"implemented_by", "supports", "triggers", "starts_flow"}
)
SUPPORTED_IMPLEMENTATION_STATUSES = frozenset(
    {"planned", "in_progress", "implemented"}
)


def validate_element(
    element: Any,
    *,
    scope: str,
    parent_type: str | None,
    object_ids: set[str],
    element_ids: set[str],
    element_types: dict[str, str],
    errors: list[str],
    path: str,
) -> None:
    if not isinstance(element, dict):
        errors.append(f"{path} содержит элемент, который не является объектом")
        return

    element_id = element.get("id")
    type_id = element.get("type")
    label = element.get("label")
    if not isinstance(element_id, str) or not element_id.strip():
        errors.append(f"В {path} найден элемент без корректного id")
        return
    if element_id in object_ids:
        errors.append(f"Повторяющийся id UI-объекта: {element_id}")
        return
    object_ids.add(element_id)
    element_ids.add(element_id)

    try:
        definition = ensure_type_allowed(str(type_id), scope=scope)
    except ValueError as exc:
        errors.append(f"Элемент {element_id}: {exc}")
        definition = None
    if not isinstance(label, str) or not label.strip():
        errors.append(f"Элемент {element_id} должен иметь непустой label")

    if parent_type is None and isinstance(type_id, str) and definition is not None:
        try:
            if not is_root_allowed(type_id, scope=scope):
                if scope == "app":
                    errors.append(
                        f"Корневой элемент app.json {element_id} имеет недопустимый тип: {type_id}"
                    )
                else:
                    errors.append(
                        f"Элемент {element_id} типа {type_id} нельзя размещать в корне страницы"
                    )
        except ValueError as exc:
            errors.append(f"Элемент {element_id}: {exc}")
    if parent_type is not None:
        try:
            if type_id not in allowed_child_types(parent_type, scope=scope):
                errors.append(f"Элемент {element_id} типа {type_id} нельзя размещать внутри {parent_type}")
            configured_parents = (
                allowed_parent_types(str(type_id), scope=scope)
                if definition is not None
                else None
            )
            if configured_parents is not None and parent_type not in configured_parents:
                allowed = ", ".join(sorted(configured_parents)) or "<none>"
                errors.append(
                    f"Элемент {element_id} типа {type_id} требует родителя типа: {allowed}; "
                    f"фактический тип родителя: {parent_type}"
                )
        except ValueError as exc:
            errors.append(f"Элемент {element_id}: {exc}")

    children = element.get("children")
    if definition and definition.get("kind") == "atomic":
        if isinstance(children, list) and children:
            errors.append(f"Атомарный элемент {element_id} не может содержать children")
        elif children not in (None, []):
            errors.append(f"Атомарный элемент {element_id} содержит некорректное значение children")
    elif definition and definition.get("kind") == "group":
        if children is None:
            children = []
        if not isinstance(children, list):
            errors.append(f"У группового элемента {element_id} поле children должно быть массивом")
            children = []
        for child in children:
            validate_element(
                child,
                scope=scope,
                parent_type=str(type_id),
                object_ids=object_ids,
                element_ids=element_ids,
                element_types=element_types,
                errors=errors,
                path=f"{path}.{element_id}.children",
            )
    if isinstance(type_id, str):
        element_types[element_id] = type_id


def validate_ui_links(
    data: dict[str, Any],
    *,
    page_ids: set[str],
    element_ids: set[str],
    element_types: dict[str, str],
    errors: list[str],
) -> None:
    links = data.get("links")
    if not isinstance(links, list):
        errors.append("`links.json.links` должен быть массивом")
        return
    seen: set[str] = set()
    for index, link in enumerate(links):
        if not isinstance(link, dict):
            errors.append(f"links[{index}] должен быть объектом")
            continue
        link_id = link.get("id")
        if not isinstance(link_id, str) or not link_id:
            errors.append(f"UI-связь в позиции {index} не имеет id")
        elif link_id in seen:
            errors.append(f"Повторяющийся id UI-связи: {link_id}")
        else:
            seen.add(link_id)

        source_type, source_id = link.get("source_type"), link.get("source_id")
        target_type, target_id = link.get("target_type"), link.get("target_id")
        relation = link.get("relation")
        if not target_exists(source_type, source_id, page_ids, element_ids):
            errors.append(f"UI-связь {link_id or index} имеет отсутствующий источник: {source_type}:{source_id}")
        if not target_exists(target_type, target_id, page_ids, element_ids):
            errors.append(f"UI-связь {link_id or index} ведёт на отсутствующую цель: {target_type}:{target_id}")
        if source_type == "ui_element" and source_id in element_types:
            definition = type_definition(element_types[source_id])
            if not definition or definition.get("link_source") is not True:
                errors.append(f"Элемент {source_id} не может быть источником UI-связи")
        if relation not in {"navigates_to", "opens_modal"}:
            errors.append(f"UI-связь {link_id or index} использует неподдерживаемый тип связи: {relation}")
        if relation == "opens_modal" and target_type == "ui_element":
            if element_types.get(str(target_id)) != "modal":
                errors.append(f"Цель UI-связи {link_id or index} с relation=opens_modal должна иметь тип modal")


def validate_requirement_links(
    data: dict[str, Any],
    *,
    requirement_ids: set[str],
    page_ids: set[str],
    element_ids: set[str],
    errors: list[str],
    warnings: list[str],
) -> None:
    links = data.get("links")
    if not isinstance(links, list):
        errors.append("requirement_ui_links.json.links должен быть массивом")
        return

    seen_ids: dict[str, bool] = {}
    seen_pairs: dict[tuple[str, str, str, str], bool] = {}
    inherited_requirement_ids: set[str] = set()
    inherited_issues: list[str] = []

    for index, link in enumerate(links):
        if not isinstance(link, dict):
            errors.append(f"requirement_ui_links.json.links[{index}] должен быть объектом")
            continue

        requirement_id = link.get("requirement_id")
        is_current_requirement = requirement_id in requirement_ids
        if not is_current_requirement and requirement_id not in (None, ""):
            inherited_requirement_ids.add(str(requirement_id))

        link_id = link.get("id")
        if not isinstance(link_id, str) or not link_id:
            message = f"Связь с требованием в позиции {index} не имеет технического id"
            _append_link_issue(
                message,
                current=is_current_requirement,
                errors=errors,
                inherited_issues=inherited_issues,
            )
        elif link_id in seen_ids:
            message = f"Повторяющийся id связи с требованием: {link_id}"
            _append_link_issue(
                message,
                current=is_current_requirement or seen_ids[link_id],
                errors=errors,
                inherited_issues=inherited_issues,
            )
        else:
            seen_ids[link_id] = is_current_requirement

        target_type = link.get("target_type")
        target_id = link.get("target_id")
        relation = link.get("relation")
        if not target_exists(target_type, target_id, page_ids, element_ids):
            _append_link_issue(
                (
                    f"Связь с требованием {link_id or index} ведёт на отсутствующую цель: "
                    f"{target_type}:{target_id}"
                ),
                current=is_current_requirement,
                errors=errors,
                inherited_issues=inherited_issues,
            )
        if relation not in SUPPORTED_REQUIREMENT_LINK_RELATIONS:
            _append_link_issue(
                f"Связь с требованием {link_id or index} использует неподдерживаемый тип связи: {relation}",
                current=is_current_requirement,
                errors=errors,
                inherited_issues=inherited_issues,
            )
        implementation_status = link.get("implementation_status")
        if implementation_status not in (None, "") and implementation_status not in SUPPORTED_IMPLEMENTATION_STATUSES:
            _append_link_issue(
                f"Связь с требованием {link_id or index} содержит неподдерживаемый "
                f"implementation_status: {implementation_status}",
                current=is_current_requirement,
                errors=errors,
                inherited_issues=inherited_issues,
            )

        pair = (
            str(requirement_id),
            str(target_type),
            str(target_id),
            str(relation),
        )
        if pair in seen_pairs:
            _append_link_issue(
                (
                    f"Повторяющаяся трассировка требования: {requirement_id} → "
                    f"{target_type}:{target_id} ({relation})"
                ),
                current=is_current_requirement or seen_pairs[pair],
                errors=errors,
                inherited_issues=inherited_issues,
            )
        else:
            seen_pairs[pair] = is_current_requirement

    if inherited_requirement_ids:
        requirement_count = len(inherited_requirement_ids)
        requirement_word = "требованием" if _is_singular_ru(requirement_count) else "требованиями"
        warnings.append(
            f"Найдены сохранённые связи с {requirement_count} {requirement_word}, "
            "которых нет в выбранном входном файле. "
            "Они не удалены автоматически. Откройте раздел «Ручная проверка» и решите: "
            "оставить связи для частичного файла, обновить ID переименованного требования "
            "или удалить действительно неактуальные связи вручную."
        )
    if inherited_issues:
        issue_count = len(inherited_issues)
        issue_phrase = (
            "сохранённой связи"
            if _is_singular_ru(issue_count)
            else "сохранённых связей"
        )
        warnings.append(
            f"У {issue_count} {issue_phrase} с отсутствующими требованиями "
            "обнаружены устаревшие или повреждённые данные. Они не блокируют синхронизацию. "
            "Целевые объекты, технические ID и рекомендации показаны в разделе "
            "«Ручная проверка»."
        )


def _append_link_issue(
    message: str,
    *,
    current: bool,
    errors: list[str],
    inherited_issues: list[str],
) -> None:
    if current:
        errors.append(message)
    else:
        inherited_issues.append(message)


def target_exists(target_type: Any, target_id: Any, page_ids: set[str], element_ids: set[str]) -> bool:
    if target_type == "page":
        return target_id in page_ids
    if target_type == "ui_element":
        return target_id in element_ids
    return False


def _is_singular_ru(value: int) -> bool:
    number = abs(int(value))
    return number % 10 == 1 and number % 100 != 11
