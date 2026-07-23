from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


CONFIG_PATH = Path(__file__).resolve().parents[3] / "modules" / "ui_schema" / "config.yaml"
VALID_SCOPES = {"page", "app"}
VALID_KINDS = {"group", "atomic"}


@lru_cache(maxsize=1)
def element_type_catalog() -> tuple[dict[str, Any], ...]:
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    raw_types = data.get("ui", {}).get("element_types", [])
    if not isinstance(raw_types, list):
        raise RuntimeError("ui.element_types must be a list in modules/ui_schema/config.yaml")

    catalog: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_item in raw_types:
        if not isinstance(raw_item, dict):
            raise RuntimeError("Each ui.element_types item must be an object")
        item = dict(raw_item)
        type_id = item.get("id")
        scope = item.get("scope")
        kind = item.get("kind")
        if not isinstance(type_id, str) or not type_id:
            raise RuntimeError("Each UI element type must have a non-empty id")
        if type_id in seen:
            raise RuntimeError(f"Duplicate UI element type: {type_id}")
        if scope not in VALID_SCOPES:
            raise RuntimeError(f"Unsupported scope for UI element type {type_id}: {scope}")
        if kind not in VALID_KINDS:
            raise RuntimeError(f"Unsupported kind for UI element type {type_id}: {kind}")
        allowed_children = item.get("allowed_children")
        if allowed_children is not None and not isinstance(allowed_children, list):
            raise RuntimeError(f"allowed_children must be a list for UI element type {type_id}")
        seen.add(type_id)
        catalog.append(item)

    for item in catalog:
        for child_type in item.get("allowed_children", []):
            if child_type not in seen:
                raise RuntimeError(
                    f"Unknown allowed child type {child_type} for UI element type {item['id']}"
                )
    return tuple(catalog)


@lru_cache(maxsize=1)
def element_types_by_id() -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in element_type_catalog()}


def type_definition(type_id: str) -> dict[str, Any] | None:
    return element_types_by_id().get(type_id)


def type_ids(*, scope: str | None = None, kind: str | None = None) -> set[str]:
    return {
        item["id"]
        for item in element_type_catalog()
        if (scope is None or item["scope"] == scope) and (kind is None or item["kind"] == kind)
    }


def ensure_type_allowed(type_id: str, *, scope: str) -> dict[str, Any]:
    item = type_definition(type_id)
    if item is None or item.get("scope") != scope:
        raise ValueError(f"Unsupported {scope} element type: {type_id}")
    return item


def is_group_type(type_id: str, *, scope: str | None = None) -> bool:
    item = type_definition(type_id)
    return bool(item and item.get("kind") == "group" and (scope is None or item.get("scope") == scope))


def allowed_child_types(parent_type: str, *, scope: str) -> set[str]:
    parent = ensure_type_allowed(parent_type, scope=scope)
    if parent.get("kind") != "group":
        return set()
    configured = parent.get("allowed_children")
    if configured is not None:
        return set(configured)
    return type_ids(scope=scope)


def root_type_ids(*, scope: str) -> set[str]:
    return {
        item["id"]
        for item in element_type_catalog()
        if item.get("scope") == scope and item.get("root_allowed") is True
    }
