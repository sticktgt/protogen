from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.modules.ui_schema.agent_element_payloads import (
    UiElementPayload,
    plain_element_list,
)
from backend.modules.ui_schema.agent_normalize_documents import canonicalize_schema_document
from backend.modules.ui_schema.agent_schema_io import (
    normalize_write_path,
    write_ui_schema_bundle,
)
from backend.modules.ui_schema.agent_tool_payloads import decode_json_argument
from backend.modules.ui_schema.files import read_json

_DEFAULT_MAX_TOP_LEVEL_ELEMENTS = 16
_SCHEMA_REGISTRY_LOCK = Lock()


class PageDocumentArgs(BaseModel):
    """One page per tool call keeps provider payloads bounded and recoverable."""

    model_config = ConfigDict(extra="forbid")

    page_id: str = Field(description="Exact page ID, for example reports.statement")
    title: str = Field(description="Human-readable page title")
    description: str = Field(default="", description="Short page purpose")
    elements: list[UiElementPayload] = Field(
        default_factory=list,
        description=(
            "Native JSON array of top-level page elements. Never serialize it into a string. "
            "For a large page create the page shell first and use write_ui_schema_page_elements."
        ),
    )
    file_path: str | None = Field(
        default=None,
        description=(
            "Optional relative path pages/<page_id>.json. Omit to derive it from page_id."
        ),
    )

    @field_validator("elements", mode="before")
    @classmethod
    def normalize_elements(cls, value: Any):
        return normalize_element_batch(value, label="elements")

    @model_validator(mode="after")
    def validate_identity(self):
        self.page_id = _clean_page_id(self.page_id)
        self.file_path = normalize_page_path(self.page_id, self.file_path)
        return self


class PageElementsArgs(BaseModel):
    """Add or replace a few top-level groups in an already created page."""

    model_config = ConfigDict(extra="forbid")

    page_id: str = Field(description="Exact ID of an existing page")
    elements: list[UiElementPayload] = Field(
        description=(
            "Native JSON array of a few top-level elements. Existing top-level elements with "
            "the same IDs are replaced; all others are preserved."
        )
    )

    @field_validator("elements", mode="before")
    @classmethod
    def normalize_elements(cls, value: Any):
        return normalize_element_batch(value, label="elements")

    @model_validator(mode="after")
    def validate_identity(self):
        self.page_id = _clean_page_id(self.page_id)
        return self


def write_page_document(
    *,
    working_root: Path,
    result_root: Path,
    page_id: str,
    title: str,
    description: str,
    elements: list[UiElementPayload | dict[str, Any]],
    file_path: str | None,
    maximum_top_level_elements: int,
) -> dict[str, Any]:
    plain_elements = plain_element_list(elements)
    _enforce_element_limit(plain_elements, maximum_top_level_elements)
    normalized_path = normalize_page_path(page_id, file_path)
    page = {
        "id": page_id,
        "title": title,
        "description": description,
        "elements": plain_elements,
    }
    result = write_ui_schema_bundle(
        working_root=working_root,
        result_root=result_root,
        files=[{"file_path": normalized_path, "content": page}],
        maximum_files=1,
    )
    _register_page(working_root, page_id=page_id, title=title)
    return result


def write_page_elements(
    *,
    working_root: Path,
    result_root: Path,
    page_id: str,
    elements: list[UiElementPayload | dict[str, Any]],
    maximum_top_level_elements: int,
) -> dict[str, Any]:
    plain_elements = plain_element_list(elements)
    _enforce_element_limit(plain_elements, maximum_top_level_elements)
    path = working_root / "pages" / f"{page_id}.json"
    page = read_json(path, {})
    if not isinstance(page, dict) or page.get("id") != page_id:
        raise ValueError(
            f"Page {page_id} does not exist yet. Call write_ui_schema_page first, "
            "possibly with elements: [], then add small element batches."
        )

    current = page.get("elements", [])
    if not isinstance(current, list):
        current = []
    incoming_ids = {_element_id(item, index) for index, item in enumerate(plain_elements)}
    merged = [
        item
        for item in current
        if not isinstance(item, dict) or item.get("id") not in incoming_ids
    ]
    merged.extend(plain_elements)
    page["elements"] = merged
    return write_ui_schema_bundle(
        working_root=working_root,
        result_root=result_root,
        files=[{"file_path": f"pages/{page_id}.json", "content": page}],
        maximum_files=1,
    )


def page_element_limit(agent_config: dict[str, Any]) -> int:
    execution = agent_config.get("execution", {}) if isinstance(agent_config, dict) else {}
    value = execution.get("write_page_max_top_level_elements") if isinstance(execution, dict) else None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_TOP_LEVEL_ELEMENTS
    return parsed if parsed > 0 else _DEFAULT_MAX_TOP_LEVEL_ELEMENTS


def normalize_element_batch(value: Any, *, label: str) -> list[dict[str, Any]]:
    try:
        candidate = decode_json_argument(value, label=label)
    except ValueError as exc:
        raise ValueError(
            f"{label} must be a native JSON array. Do not retry the same serialized payload. "
            "Create one page at a time; for a large page create a shell and call "
            f"write_ui_schema_page_elements with one or a few top-level groups. {exc}"
        ) from exc
    if isinstance(candidate, dict) and set(candidate) == {"elements"}:
        candidate = candidate["elements"]
    if not isinstance(candidate, list):
        raise ValueError(f"{label} must be a native JSON array")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(candidate):
        if not isinstance(item, dict):
            raise ValueError(f"{label}[{index}] must be an object")
        item_id = _element_id(item, index)
        if item_id in seen:
            raise ValueError(f"Duplicate top-level element ID in one batch: {item_id}")
        seen.add(item_id)
        normalized.append(item)
    return normalized


def normalize_page_path(page_id: str, file_path: str | None) -> str:
    expected = f"pages/{page_id}.json"
    if not file_path:
        return expected
    normalized = normalize_write_path(file_path)
    if normalized != expected:
        raise ValueError(
            f"Page {page_id} must use file_path {expected}, received {normalized}"
        )
    return normalized


def _clean_page_id(value: str) -> str:
    page_id = str(value or "").strip()
    if not page_id:
        raise ValueError("page_id must be non-empty")
    if "/" in page_id or "\\" in page_id or page_id in {".", ".."}:
        raise ValueError("page_id must be a dotted identifier without path separators")
    return page_id


def _element_id(item: dict[str, Any], index: int) -> str:
    value = item.get("id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"elements[{index}].id must be a non-empty string")
    return value.strip()


def _enforce_element_limit(elements: list[dict[str, Any]], maximum: int) -> None:
    if len(elements) > maximum:
        raise ValueError(
            f"A page tool call may contain at most {maximum} top-level elements; "
            "create the page shell and split top-level groups across "
            "write_ui_schema_page_elements calls"
        )


def _register_page(working_root: Path, *, page_id: str, title: str) -> None:
    from backend.modules.ui_schema.files import write_json

    path = working_root / "schema.json"
    with _SCHEMA_REGISTRY_LOCK:
        schema = read_json(path, {})
        if not isinstance(schema, dict):
            schema = {"schema_version": "0.1", "application": {}, "pages": []}
        schema = canonicalize_schema_document(schema)
        pages = schema.get("pages")
        if not isinstance(pages, list):
            pages = []
        expected = f"pages/{page_id}.json"
        updated = False
        for item in pages:
            if isinstance(item, dict) and item.get("id") == page_id:
                item["file"] = expected
                item.pop("file_path", None)
                item.pop("path", None)
                if title and not item.get("title"):
                    item["title"] = title
                updated = True
                break
        if not updated:
            pages.append({"id": page_id, "title": title, "file": expected})
        schema["pages"] = pages
        write_json(path, schema)
