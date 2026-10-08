from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.modules.ui_schema.agent_preflight_issues import preflight_issue
from backend.modules.ui_schema.agent_target_catalog import build_target_catalog
from backend.modules.ui_schema.element_types import (
    allowed_child_types,
    allowed_parent_types,
    ensure_type_allowed,
    is_root_allowed,
    type_definition,
)


class VirtualSchema:
    def __init__(self) -> None:
        self.pages: set[str] = set()
        self.elements: dict[str, dict[str, Any]] = {}
        self.initial_element_ids: set[str] = set()

    @classmethod
    def from_root(cls, schema_root) -> "VirtualSchema":
        state = cls()
        for (target_type, target_id), item in build_target_catalog(schema_root).items():
            if target_type == "page":
                state.pages.add(target_id)
                continue
            state.elements[target_id] = {
                "id": target_id,
                "page_id": str(item.get("page_id") or ""),
                "parent_id": str(item.get("parent_id") or ""),
                "type": str(item.get("element_type") or ""),
                "label": str(item.get("label") or ""),
                "created_in_bundle": False,
            }
        state.initial_element_ids = set(state.elements)
        return state

    def target_exists(self, target_type: str, target_id: str) -> bool:
        if target_type == "page":
            return target_id in self.pages
        if target_type == "ui_element":
            return target_id in self.elements
        return False

    def add_tree(
        self,
        *,
        page_id: str,
        elements: Any,
        parent_id: str,
        issues: list[dict[str, Any]],
        source: str,
    ) -> None:
        for raw in elements if isinstance(elements, list) else []:
            if not isinstance(raw, dict):
                issues.append(
                    preflight_issue(
                        "invalid_element",
                        f"{source}: элемент должен быть объектом",
                    )
                )
                continue
            element_id = str(raw.get("id") or "").strip()
            type_id = str(raw.get("type") or "").strip()
            if not element_id:
                issues.append(
                    preflight_issue(
                        "missing_element_id",
                        f"{source}: элемент не имеет id",
                    )
                )
                continue
            if element_id in self.elements:
                issues.append(
                    preflight_issue(
                        "duplicate_element_id",
                        f"Элемент {element_id} уже существует; нельзя создавать второй объект с тем же id",
                        element_id=element_id,
                    )
                )
                continue
            self.elements[element_id] = {
                "id": element_id,
                "page_id": page_id,
                "parent_id": parent_id,
                "type": type_id,
                "label": str(raw.get("label") or ""),
                "created_in_bundle": True,
            }
            validate_virtual_placement(
                state=self,
                element_id=element_id,
                page_id=page_id,
                parent_id=parent_id,
                type_id=type_id,
                issues=issues,
            )
            self.add_tree(
                page_id=page_id,
                elements=raw.get("children", []),
                parent_id=element_id,
                issues=issues,
                source=source,
            )


def collect_page_operation_issues(
    state: VirtualSchema,
    *,
    create_pages: list[Any],
    update_pages: list[Any],
    issues: list[dict[str, Any]],
) -> None:
    seen_create: set[str] = set()
    for index, raw in enumerate(create_pages):
        item = raw.model_dump(exclude_none=True) if isinstance(raw, BaseModel) else dict(raw)
        page_id = str(item.get("page_id") or item.get("id") or "").strip()
        if not page_id:
            issues.append(
                preflight_issue(
                    "missing_page_id",
                    f"create_pages[{index}] не содержит page_id",
                )
            )
            continue
        if page_id == "app":
            issues.append(
                preflight_issue(
                    "app_not_a_page",
                    "app.json нельзя создавать через create_pages; изменяй глобальные элементы через upsert_elements с page_id=app",
                    page_id=page_id,
                    allowed_operations=["upsert_elements"],
                )
            )
            continue
        if page_id in seen_create:
            issues.append(
                preflight_issue(
                    "duplicate_create_page",
                    f"Страница {page_id} несколько раз указана в create_pages",
                    page_id=page_id,
                )
            )
            continue
        seen_create.add(page_id)
        if page_id in state.pages:
            issues.append(
                preflight_issue(
                    "create_page_exists",
                    f"Страница {page_id} уже существует; используй update_pages и upsert_elements",
                    page_id=page_id,
                    allowed_actions=["reuse", "extend"],
                )
            )
            continue
        state.pages.add(page_id)
        state.add_tree(
            page_id=page_id,
            elements=item.get("elements", []),
            parent_id=page_id,
            issues=issues,
            source=f"create_pages[{index}]",
        )

    for index, raw in enumerate(update_pages):
        item = raw.model_dump(exclude_none=True) if isinstance(raw, BaseModel) else dict(raw)
        page_id = str(item.get("page_id") or "").strip()
        if not page_id:
            issues.append(
                preflight_issue(
                    "missing_page_id",
                    f"update_pages[{index}] не содержит page_id",
                )
            )
        elif page_id == "app":
            issues.append(
                preflight_issue(
                    "app_not_a_page",
                    "app.json нельзя изменять через update_pages; изменяй глобальные элементы через upsert_elements с page_id=app",
                    page_id=page_id,
                    allowed_operations=["upsert_elements"],
                )
            )
        elif page_id not in state.pages:
            issues.append(
                preflight_issue(
                    "update_page_missing",
                    f"Страница {page_id} отсутствует; update_pages применим только к существующей или создаваемой странице",
                    page_id=page_id,
                    allowed_actions=["create"],
                )
            )


def validate_virtual_placement(
    *,
    state: VirtualSchema,
    element_id: str,
    page_id: str,
    parent_id: str,
    type_id: str,
    issues: list[dict[str, Any]],
) -> None:
    scope = "app" if page_id == "app" else "page"
    try:
        ensure_type_allowed(type_id, scope=scope)
    except ValueError as exc:
        issues.append(
            preflight_issue(
                "unsupported_element_type",
                f"Элемент {element_id}: {exc}",
                page_id=page_id,
                element_id=element_id,
                element_type=type_id,
            )
        )
        return

    if parent_id == page_id:
        if not is_root_allowed(type_id, scope=scope):
            issues.append(
                preflight_issue(
                    "root_type_not_allowed",
                    f"Элемент {element_id} типа {type_id} нельзя размещать в корне документа {page_id}",
                    page_id=page_id,
                    element_id=element_id,
                    element_type=type_id,
                    parent_id=parent_id,
                )
            )
        definition = type_definition(type_id) or {}
        if scope == "app" and definition.get("unique_root") is True:
            same_type_roots = [
                item_id
                for item_id, item in state.elements.items()
                if str(item.get("page_id") or "") == "app"
                and str(item.get("parent_id") or "") == "app"
                and str(item.get("type") or "") == type_id
            ]
            if len(same_type_roots) > 1:
                issues.append(
                    preflight_issue(
                        "duplicate_unique_app_root",
                        f"В app.json тип {type_id} допускается только один раз в корне: {', '.join(sorted(same_type_roots))}",
                        element_type=type_id,
                        element_ids=sorted(same_type_roots),
                    )
                )
        return

    parent = state.elements.get(parent_id)
    if parent is None:
        issues.append(
            preflight_issue(
                "parent_missing",
                f"Родитель {parent_id} для элемента {element_id} отсутствует в текущей схеме и пакете",
                page_id=page_id,
                element_id=element_id,
                parent_id=parent_id,
            )
        )
        return
    if str(parent.get("page_id") or "") != page_id:
        issues.append(
            preflight_issue(
                "parent_wrong_document",
                f"Родитель {parent_id} находится в документе {parent.get('page_id')}, а элемент {element_id} — в {page_id}",
                page_id=page_id,
                element_id=element_id,
                parent_id=parent_id,
            )
        )
        return

    parent_type = str(parent.get("type") or "")
    try:
        if type_id not in allowed_child_types(parent_type, scope=scope):
            issues.append(
                preflight_issue(
                    "child_type_not_allowed",
                    f"Элемент {element_id} типа {type_id} нельзя размещать внутри {parent_type}",
                    page_id=page_id,
                    element_id=element_id,
                    element_type=type_id,
                    parent_id=parent_id,
                    parent_type=parent_type,
                )
            )
        configured = allowed_parent_types(type_id, scope=scope)
        if configured is not None and parent_type not in configured:
            issues.append(
                preflight_issue(
                    "parent_type_not_allowed",
                    (
                        f"Элемент {element_id} типа {type_id} требует родителя типа "
                        f"{', '.join(sorted(configured)) or '<none>'}; фактический тип родителя — {parent_type}"
                    ),
                    page_id=page_id,
                    element_id=element_id,
                    element_type=type_id,
                    parent_id=parent_id,
                    parent_type=parent_type,
                    allowed_parent_types=sorted(configured),
                )
            )
    except ValueError as exc:
        issues.append(
            preflight_issue(
                "invalid_parent_type",
                f"Элемент {element_id}: {exc}",
                page_id=page_id,
                element_id=element_id,
                parent_id=parent_id,
            )
        )
