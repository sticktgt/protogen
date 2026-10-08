from __future__ import annotations

from collections import OrderedDict
from typing import Any

from pydantic import BaseModel


def flatten_upsert_changes(changes: list[Any]) -> list[dict[str, Any]]:
    """Flatten nested element trees into ordered targeted upserts.

    The transformation preserves model-selected IDs, types, labels and hierarchy.
    It never moves an existing element: the normal targeted-write validation still
    rejects a parent change. Duplicate descriptions of the same element are merged
    only when they agree on page and explicit parent.
    """
    merged: "OrderedDict[tuple[str, str], dict[str, Any]]" = OrderedDict()

    def plain(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(exclude_none=True)
        if isinstance(value, dict):
            return {key: plain(item) for key, item in value.items()}
        if isinstance(value, list):
            return [plain(item) for item in value]
        return value

    def add_change(
        *,
        page_id: str,
        parent_id: str | None,
        element: dict[str, Any],
        position: int | None,
    ) -> None:
        payload = dict(element)
        children = payload.pop("children", None)
        element_id = str(payload.get("id") or "").strip()
        if not element_id:
            raise ValueError("Nested upsert element is missing id")
        key = (page_id, element_id)
        existing = merged.get(key)
        if existing is None:
            merged[key] = {
                "page_id": page_id,
                "parent_id": parent_id,
                "element": payload,
                **({"position": position} if position is not None else {}),
            }
        else:
            old_parent = existing.get("parent_id")
            if old_parent and parent_id and old_parent != parent_id:
                raise ValueError(
                    f"Element {element_id} is described under conflicting parents: "
                    f"{old_parent} and {parent_id}"
                )
            if not old_parent and parent_id:
                existing["parent_id"] = parent_id
            existing["element"].update(payload)
            if position is not None:
                existing["position"] = position

        if children not in (None, []):
            if not isinstance(children, list):
                raise ValueError(f"Element {element_id}.children must be a JSON array")
            for child in children:
                if not isinstance(child, dict):
                    raise ValueError(f"Element {element_id}.children contains a non-object")
                add_change(
                    page_id=page_id,
                    parent_id=element_id,
                    element=child,
                    position=None,
                )

    for raw in changes:
        change = plain(raw)
        if not isinstance(change, dict):
            raise ValueError("Each upsert_elements item must be an object")
        page_id = str(change.get("page_id") or "").strip()
        element = change.get("element")
        if not page_id or not isinstance(element, dict):
            raise ValueError("Each upsert_elements item requires page_id and element")
        parent_value = change.get("parent_id")
        parent_id = str(parent_value).strip() if parent_value not in (None, "") else None
        add_change(
            page_id=page_id,
            parent_id=parent_id,
            element=element,
            position=change.get("position"),
        )

    items = list(merged.values())
    incoming_ids = {(item["page_id"], item["element"]["id"]) for item in items}
    emitted: set[tuple[str, str]] = set()
    ordered: list[dict[str, Any]] = []
    pending = list(items)
    while pending:
        progress = False
        for item in list(pending):
            parent_id = item.get("parent_id")
            dependency = (item["page_id"], parent_id) if parent_id else None
            if dependency is None or dependency not in incoming_ids or dependency in emitted:
                ordered.append(item)
                emitted.add((item["page_id"], item["element"]["id"]))
                pending.remove(item)
                progress = True
        if not progress:
            ids = ", ".join(str(item["element"]["id"]) for item in pending[:10])
            raise ValueError(f"Cyclic parent dependencies in upsert_elements: {ids}")
    return ordered
