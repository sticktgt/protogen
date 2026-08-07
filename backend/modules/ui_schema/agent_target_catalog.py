from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from backend.modules.ui_schema.storage import list_pages, read_app
from backend.modules.ui_schema.element_types import element_type_catalog, type_definition


def build_target_catalog(schema_root: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """Build a compact technical catalog of pages and UI elements.

    The catalog exposes only structural facts. It does not decide whether a target is
    semantically suitable for a requirement.
    """
    result: dict[tuple[str, str], dict[str, Any]] = {}
    type_kinds = {
        str(item.get("id") or ""): str(item.get("kind") or "")
        for item in element_type_catalog()
    }

    app = read_app(schema_root)
    _collect_elements(
        app.get("root_elements", []),
        result,
        page_id="app",
        parent_id="app",
        type_kinds=type_kinds,
    )

    for page_ref in list_pages(schema_root):
        page = page_ref.get("details") or {}
        page_id = str(page_ref.get("id") or page.get("id") or "").strip()
        if not page_id:
            continue
        result[("page", page_id)] = {
            "target_type": "page",
            "target_id": page_id,
            "exists": True,
            "target_status": "existing",
            "allowed_actions": ["reuse", "extend"],
            "title": str(page.get("title") or page_ref.get("title") or ""),
            "description": str(page.get("description") or ""),
            "root_element_count": len(page.get("elements", []))
            if isinstance(page.get("elements"), list)
            else 0,
        }
        _collect_elements(
            page.get("elements", []),
            result,
            page_id=page_id,
            parent_id=page_id,
            type_kinds=type_kinds,
        )
    return result


def build_technical_index(
    schema_root: Path,
    *,
    page_ids: Iterable[str] | None = None,
    target_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return a compact model-facing index without replacing canonical tree storage."""
    catalog = build_target_catalog(schema_root)
    page_filter = {str(item) for item in page_ids or [] if str(item)}
    target_filter = {str(item) for item in target_ids or [] if str(item)}
    pages: list[dict[str, Any]] = []
    elements: list[dict[str, Any]] = []
    for (target_type, target_id), raw in sorted(catalog.items()):
        item_page = str(raw.get("page_id") or target_id)
        if page_filter or target_filter:
            if item_page not in page_filter and target_id not in target_filter:
                continue
        if target_type == "page":
            pages.append({"id": target_id})
        else:
            element = {
                "id": target_id,
                "page_id": item_page,
                "parent_id": str(raw.get("parent_id") or ""),
                "type": str(raw.get("element_type") or ""),
            }
            if raw.get("link_source") is True:
                element["link_source"] = True
            elements.append(element)
    return {
        "note": (
            "Каждая перечисленная цель уже существует: для неё допустимы action=reuse "
            "или action=extend. Отсутствующая в индексе цель считается новой и допускает "
            "action=create только вместе с операцией создания. Индекс содержит те же "
            "технические факты, что и каноническая вложенная схема. Поле link_source "
            "присутствует только у элементов, которым разрешено быть источником UI-связи."
        ),
        "listed_target_status": "existing",
        "listed_target_allowed_actions": ["reuse", "extend"],
        "missing_target_allowed_actions": ["create"],
        "pages": pages,
        "elements": elements,
    }


def target_summary(
    catalog: dict[tuple[str, str], dict[str, Any]],
    *,
    target_type: str,
    target_id: str,
) -> dict[str, Any]:
    key = (str(target_type or "").strip(), str(target_id or "").strip())
    if key in catalog:
        return dict(catalog[key])
    return {
        "target_type": key[0],
        "target_id": key[1],
        "exists": False,
        "target_status": "missing",
        "allowed_actions": ["create"],
    }


def _collect_elements(
    elements: Any,
    result: dict[tuple[str, str], dict[str, Any]],
    *,
    page_id: str,
    parent_id: str,
    type_kinds: dict[str, str],
) -> None:
    for element in elements if isinstance(elements, list) else []:
        if not isinstance(element, dict):
            continue
        element_id = str(element.get("id") or "").strip()
        if not element_id:
            continue
        children = element.get("children", [])
        child_items = children if isinstance(children, list) else []
        element_type = str(element.get("type") or "")
        definition = type_definition(element_type) or {}
        result[("ui_element", element_id)] = {
            "target_type": "ui_element",
            "target_id": element_id,
            "exists": True,
            "target_status": "existing",
            "allowed_actions": ["reuse", "extend"],
            "page_id": page_id,
            "scope": "app" if page_id == "app" else "page",
            "parent_id": parent_id,
            "element_type": element_type,
            "element_kind": type_kinds.get(element_type, ""),
            "link_source": definition.get("link_source") is True,
            "label": str(element.get("label") or ""),
            "description": str(element.get("description") or ""),
            "child_count": len(child_items),
        }
        _collect_elements(
            child_items,
            result,
            page_id=page_id,
            parent_id=element_id,
            type_kinds=type_kinds,
        )
