from __future__ import annotations

from collections import Counter
from typing import Any

from backend.modules.ui_schema.agent_validation_rules import validate_element
from backend.modules.ui_schema.element_types import root_type_ids, type_definition


def validate_generated_document(file_path: str, content: dict[str, Any]) -> None:
    """Reject technically invalid app/page trees before they enter working state."""
    if file_path == "app.json":
        _validate_tree_document(
            file_path=file_path,
            items=content.get("root_elements", []),
            scope="app",
        )
        _validate_unique_app_roots(content.get("root_elements", []))
    elif file_path.startswith("pages/"):
        _validate_tree_document(
            file_path=file_path,
            items=content.get("elements", []),
            scope="page",
        )


def _validate_tree_document(*, file_path: str, items: Any, scope: str) -> None:
    if not isinstance(items, list):
        collection = "root_elements" if scope == "app" else "elements"
        raise ValueError(f"{file_path}.{collection} должен быть массивом")

    errors: list[str] = []
    object_ids: set[str] = set()
    element_ids: set[str] = set()
    element_types: dict[str, str] = {}
    for item in items:
        validate_element(
            item,
            scope=scope,
            parent_type=None,
            object_ids=object_ids,
            element_ids=element_ids,
            element_types=element_types,
            errors=errors,
            path=file_path,
        )
    if errors:
        details = " | ".join(dict.fromkeys(errors))
        if scope == "app":
            allowed = ", ".join(sorted(root_type_ids(scope="app"))) or "<нет>"
            details += (
                f" | Разрешённые корневые типы app.json: {allowed}. "
                "Типы со scope=page нельзя использовать в app.json."
            )
        raise ValueError(f"Технически некорректный {file_path}: {details}")


def _validate_unique_app_roots(items: Any) -> None:
    counts = Counter(
        str(item.get("type"))
        for item in items or []
        if isinstance(item, dict) and isinstance(item.get("type"), str)
    )
    duplicated = sorted(
        type_id
        for type_id, count in counts.items()
        if count > 1 and (type_definition(type_id) or {}).get("unique_root") is True
    )
    if duplicated:
        raise ValueError(
            "Технически некорректный app.json: повторяются уникальные корневые типы: "
            + ", ".join(duplicated)
        )
