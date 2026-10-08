from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.ui_schema.agent_element_tools import SingleElementPayload
from backend.modules.ui_schema.agent_element_tree_merge import merge_explicit_element_tree
from backend.modules.ui_schema.element_types import root_type_ids
from backend.modules.ui_schema.agent_write_validation import validate_generated_document
from backend.modules.ui_schema.files import read_json, write_json

_DEFAULT_MAX_BATCH_CHANGES = 40


class PageElementChange(BaseModel):
    """One targeted create or update operation in app.json or a page."""

    model_config = ConfigDict(extra="forbid")

    page_id: str = Field(description="Exact existing page ID, or app for app.json")
    parent_id: str | None = Field(
        default=None,
        description=(
            "For a new page element omit parent_id only to place it at the page root; use an "
            "exact container ID for a child. For app.json, a root-allowed app type may omit "
            "parent_id; every app child needs an exact app container ID. Existing elements may "
            "omit parent_id to preserve their current parent. Parent changes are rejected here."
        ),
    )
    element: SingleElementPayload
    position: int | None = Field(
        default=None,
        ge=0,
        description="Optional explicit position inside the unchanged target parent.",
    )

    @field_validator("page_id")
    @classmethod
    def normalize_page_id(cls, value: str) -> str:
        return _clean_id(value, label="page_id")

    @field_validator("parent_id")
    @classmethod
    def normalize_parent_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class PageElementsBatchArgs(BaseModel):
    """Apply several targeted changes across app.json and existing pages."""

    model_config = ConfigDict(extra="forbid")

    changes: list[PageElementChange] = Field(
        min_length=1,
        description=(
            "Coherent targeted creates and updates across app.json and existing pages. "
            "Use page_id=app for app.json. Existing elements remain under their current parent. "
            "New elements require parent_id; use the document ID for its root. Split work into "
            "a few meaningful batches when that improves correctness or fits the configured limit."
        ),
    )


class PageElementMove(BaseModel):
    """One explicit parent change for an existing app or page element."""

    model_config = ConfigDict(extra="forbid")

    page_id: str
    element_id: str
    new_parent_id: str = Field(
        description="Exact new parent ID; use page_id to move the element to its document root."
    )
    position: int | None = Field(default=None, ge=0)

    @field_validator("page_id", "element_id", "new_parent_id")
    @classmethod
    def normalize_ids(cls, value: str, info) -> str:
        return _clean_id(value, label=info.field_name)


class PageElementMovesArgs(BaseModel):
    """Apply explicit element moves across app.json and pages."""

    model_config = ConfigDict(extra="forbid")

    moves: list[PageElementMove] = Field(min_length=1)


def write_page_elements_batch(
    *,
    working_root: Path,
    changes: list[PageElementChange | dict[str, Any]],
    maximum_changes: int = _DEFAULT_MAX_BATCH_CHANGES,
) -> dict[str, Any]:
    _enforce_batch_limit(changes, maximum_changes, label="changes")
    documents: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []

    for raw_change in changes:
        change = (
            raw_change
            if isinstance(raw_change, PageElementChange)
            else PageElementChange.model_validate(raw_change)
        )
        if change.page_id not in documents:
            documents[change.page_id] = _read_document(working_root, change.page_id)
        document = documents[change.page_id]
        results.append(_apply_change(document, change))

    _validate_and_write_documents(working_root, documents)
    page_ids = sorted(document_id for document_id in documents if document_id != "app")
    return {
        "ok": True,
        "message": f"Applied {len(results)} targeted UI element changes",
        "change_count": len(results),
        "document_count": len(documents),
        "documents": sorted(documents),
        "page_count": len(page_ids),
        "pages": page_ids,
        "changes": results,
    }


def move_page_elements_batch(
    *,
    working_root: Path,
    moves: list[PageElementMove | dict[str, Any]],
    maximum_changes: int = _DEFAULT_MAX_BATCH_CHANGES,
) -> dict[str, Any]:
    _enforce_batch_limit(moves, maximum_changes, label="moves")
    documents: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []

    for raw_move in moves:
        move = (
            raw_move
            if isinstance(raw_move, PageElementMove)
            else PageElementMove.model_validate(raw_move)
        )
        if move.page_id not in documents:
            documents[move.page_id] = _read_document(working_root, move.page_id)
        document = documents[move.page_id]
        results.append(_apply_move(document, move))

    _validate_and_write_documents(working_root, documents)
    page_ids = sorted(document_id for document_id in documents if document_id != "app")
    return {
        "ok": True,
        "message": f"Moved {len(results)} UI elements explicitly",
        "move_count": len(results),
        "document_count": len(documents),
        "documents": sorted(documents),
        "page_count": len(page_ids),
        "pages": page_ids,
        "moves": results,
    }


def write_one_page_element(
    *,
    working_root: Path,
    page_id: str,
    parent_id: str | None,
    element: SingleElementPayload | dict[str, Any],
    position: int | None,
) -> dict[str, Any]:
    """Compatibility wrapper around the safe batch writer."""
    return write_page_elements_batch(
        working_root=working_root,
        changes=[
            PageElementChange(
                page_id=page_id,
                parent_id=parent_id,
                element=element,
                position=position,
            )
        ],
    )


def element_batch_limit(agent_config: dict[str, Any]) -> int:
    execution = agent_config.get("execution", {}) if isinstance(agent_config, dict) else {}
    value = execution.get("write_element_batch_max_changes") if isinstance(execution, dict) else None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_BATCH_CHANGES
    return parsed if parsed > 0 else _DEFAULT_MAX_BATCH_CHANGES


def _enforce_batch_limit(items: list[Any], maximum: int, *, label: str) -> None:
    if len(items) > maximum:
        raise ValueError(
            f"{label} may contain at most {maximum} operations; split the work into "
            "a few larger targeted batches"
        )


def _apply_change(page: dict[str, Any], change: PageElementChange) -> dict[str, Any]:
    elements = _document_elements(page, change.page_id)

    payload = change.element.model_dump(exclude_none=True)
    target_id = payload["id"]
    location = _find_location(elements, target_id, root_parent=change.page_id)

    if location is not None:
        container, index, current, current_parent = location
        requested_parent = change.parent_id
        if requested_parent is not None and requested_parent != current_parent:
            raise ValueError(
                f"Element {target_id} is currently under {current_parent}; targeted writes "
                f"cannot move it to {requested_parent}. Use move_elements in "
                "the current changes bundle for an explicit parent change."
            )
        if "children" in payload:
            updated = merge_explicit_element_tree(
                document_elements=elements,
                current=current,
                payload=payload,
            )
        else:
            updated = deepcopy(current)
            updated.update(payload)
        container[index] = updated
        if change.position is not None:
            item = container.pop(index)
            _insert(container, item, change.position)
        return {
            "page_id": change.page_id,
            "element_id": target_id,
            "operation": "updated",
            "parent_id": current_parent,
        }

    parent_id = change.parent_id
    if parent_id is None:
        if change.page_id == "app":
            if payload.get("type") in root_type_ids(scope="app"):
                parent_id = "app"
        else:
            # Omitted parent_id has one unambiguous technical meaning for a new page
            # element: create it at the page root. Child placement still requires an
            # exact parent_id selected by the model.
            parent_id = change.page_id
    if parent_id is None:
        raise ValueError(
            f"New app element {target_id} requires parent_id=app or an exact existing app container ID."
        )

    existing_ids = _all_ids(elements)
    incoming_ids = _all_ids([payload])
    collisions = sorted(existing_ids & incoming_ids)
    if collisions:
        raise ValueError(
            "New element subtree contains IDs that already exist in the document: "
            + ", ".join(collisions[:10])
            + ". Update those elements separately or move them explicitly."
        )

    if parent_id == change.page_id:
        target_container = elements
    else:
        parent_location = _find_location(elements, parent_id, root_parent=change.page_id)
        if parent_location is None:
            raise ValueError(
                f"Parent element {parent_id} does not exist in document {change.page_id}."
            )
        parent = parent_location[2]
        children = parent.get("children")
        if children is None:
            children = []
            parent["children"] = children
        if not isinstance(children, list):
            raise ValueError(f"Parent element {parent_id}.children must be a list")
        target_container = children

    _insert(target_container, payload, change.position)
    return {
        "page_id": change.page_id,
        "element_id": target_id,
        "operation": "created",
        "parent_id": parent_id,
    }


def _apply_move(page: dict[str, Any], move: PageElementMove) -> dict[str, Any]:
    elements = _document_elements(page, move.page_id)

    location = _find_location(elements, move.element_id, root_parent=move.page_id)
    if location is None:
        raise ValueError(
            f"Element {move.element_id} does not exist in document {move.page_id}"
        )
    source_container, source_index, element, current_parent = location

    if move.new_parent_id == move.element_id:
        raise ValueError("An element cannot be its own parent")
    subtree_ids = _all_ids([element])
    if move.new_parent_id in subtree_ids:
        raise ValueError("An element cannot be moved under its own descendant")

    if move.new_parent_id == current_parent:
        if move.position is not None:
            item = source_container.pop(source_index)
            _insert(source_container, item, move.position)
        return {
            "page_id": move.page_id,
            "element_id": move.element_id,
            "from_parent_id": current_parent,
            "to_parent_id": current_parent,
            "operation": "reordered" if move.position is not None else "unchanged",
        }

    source_container.pop(source_index)
    if move.new_parent_id == move.page_id:
        target_container = elements
    else:
        target_location = _find_location(
            elements,
            move.new_parent_id,
            root_parent=move.page_id,
        )
        if target_location is None:
            source_container.insert(source_index, element)
            raise ValueError(
                f"New parent {move.new_parent_id} does not exist in document {move.page_id}"
            )
        parent = target_location[2]
        children = parent.get("children")
        if children is None:
            children = []
            parent["children"] = children
        if not isinstance(children, list):
            source_container.insert(source_index, element)
            raise ValueError(f"Parent element {move.new_parent_id}.children must be a list")
        target_container = children

    _insert(target_container, element, move.position)
    return {
        "page_id": move.page_id,
        "element_id": move.element_id,
        "from_parent_id": current_parent,
        "to_parent_id": move.new_parent_id,
        "operation": "moved",
    }


def _read_document(working_root: Path, document_id: str) -> dict[str, Any]:
    if document_id == "app":
        path = working_root / "app.json"
        document = read_json(path, {})
        if not isinstance(document, dict) or document.get("id") != "app":
            raise ValueError("app.json does not exist or has invalid id")
        return deepcopy(document)

    path = working_root / "pages" / f"{document_id}.json"
    document = read_json(path, {})
    if not isinstance(document, dict) or document.get("id") != document_id:
        raise ValueError(
            f"Page {document_id} does not exist. Add it to create_pages in the same or an earlier accepted changes bundle first."
        )
    return deepcopy(document)


def _document_elements(document: dict[str, Any], document_id: str) -> list[dict[str, Any]]:
    field = "root_elements" if document_id == "app" else "elements"
    items = document.setdefault(field, [])
    if not isinstance(items, list):
        file_label = "app.json" if document_id == "app" else f"Page {document_id}"
        raise ValueError(f"{file_label}.{field} must be a list")
    return items


def _validate_and_write_documents(
    working_root: Path,
    documents: dict[str, dict[str, Any]],
) -> None:
    for document_id, document in documents.items():
        file_path = "app.json" if document_id == "app" else f"pages/{document_id}.json"
        validate_generated_document(file_path, document)
    for document_id, document in documents.items():
        target = (
            working_root / "app.json"
            if document_id == "app"
            else working_root / "pages" / f"{document_id}.json"
        )
        write_json(target, document)


def _find_location(
    items: list[Any],
    target_id: str,
    *,
    root_parent: str,
    parent_id: str | None = None,
) -> tuple[list[dict[str, Any]], int, dict[str, Any], str] | None:
    effective_parent = root_parent if parent_id is None else parent_id
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if item.get("id") == target_id:
            return items, index, item, effective_parent
        children = item.get("children", [])
        if isinstance(children, list):
            found = _find_location(
                children,
                target_id,
                root_parent=root_parent,
                parent_id=str(item.get("id") or effective_parent),
            )
            if found is not None:
                return found
    return None


def _all_ids(items: list[Any]) -> set[str]:
    result: set[str] = set()

    def walk(nodes: list[Any]) -> None:
        for item in nodes:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            if isinstance(item_id, str) and item_id:
                if item_id in result:
                    raise ValueError(f"Duplicate UI element ID in payload: {item_id}")
                result.add(item_id)
            children = item.get("children", [])
            if isinstance(children, list):
                walk(children)

    walk(items)
    return result


def _insert(items: list[dict[str, Any]], item: dict[str, Any], position: int | None) -> None:
    if position is None or position >= len(items):
        items.append(item)
    else:
        items.insert(position, item)


def _clean_id(value: str, *, label: str) -> str:
    text = str(value or "").strip()
    if not text or "/" in text or "\\" in text:
        raise ValueError(f"{label} must be a non-empty dotted identifier")
    return text
