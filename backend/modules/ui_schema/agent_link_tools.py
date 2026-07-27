from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.ui_schema.agent_schema_io import write_ui_schema_bundle
from backend.modules.ui_schema.agent_tool_payloads import decode_json_argument
from backend.modules.ui_schema.files import read_json


class UiLinkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(
        default=None,
        description="Stable technical link ID. May be omitted; backend will generate one.",
    )
    source_type: Literal["page", "ui_element"] | None = Field(
        default=None,
        description="Omit only when source_id exactly identifies an existing page or element.",
    )
    source_id: str
    target_type: Literal["page", "ui_element"] | None = Field(
        default=None,
        description="Omit only when target_id exactly identifies an existing page or element.",
    )
    target_id: str
    relation: Literal["navigates_to", "opens_modal"]


class UiLinksWriteArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    links: list[UiLinkInput] = Field(
        description=(
            "Native JSON array of UI links. IDs may be omitted; source/target types are inferred "
            "only from exact existing IDs. Never serialize the array into a string."
        )
    )

    @field_validator("links", mode="before")
    @classmethod
    def normalize_links(cls, value: Any):
        candidate = decode_json_argument(value, label="links")
        if isinstance(candidate, dict) and set(candidate) == {"links"}:
            candidate = candidate["links"]
        if not isinstance(candidate, list):
            raise ValueError("links must be a native JSON array")
        return candidate


def write_ui_links(
    *,
    working_root: Path,
    result_root: Path,
    links: list[UiLinkInput | dict[str, Any]],
) -> dict[str, Any]:
    page_ids, element_ids = _known_targets(working_root)
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(links):
        item = raw.model_dump() if isinstance(raw, BaseModel) else dict(raw)
        source_id = _required_text(item.get("source_id"), f"links[{index}].source_id")
        target_id = _required_text(item.get("target_id"), f"links[{index}].target_id")
        source_type = item.get("source_type") or _infer_target_type(
            source_id, page_ids=page_ids, element_ids=element_ids, label="source"
        )
        target_type = item.get("target_type") or _infer_target_type(
            target_id, page_ids=page_ids, element_ids=element_ids, label="target"
        )
        relation = _required_text(item.get("relation"), f"links[{index}].relation")
        link_id = str(item.get("id") or "").strip() or _generated_link_id(
            source_id, relation, target_id
        )
        if link_id in seen:
            raise ValueError(f"Duplicate UI link id: {link_id}")
        seen.add(link_id)
        normalized.append(
            {
                "id": link_id,
                "source_type": source_type,
                "source_id": source_id,
                "target_type": target_type,
                "target_id": target_id,
                "relation": relation,
            }
        )
    return write_ui_schema_bundle(
        working_root=working_root,
        result_root=result_root,
        files=[{"file_path": "links.json", "content": {"links": normalized}}],
        maximum_files=1,
    )


def _known_targets(working_root: Path) -> tuple[set[str], set[str]]:
    schema = read_json(working_root / "schema.json", {})
    page_ids = {
        str(item.get("id"))
        for item in (schema.get("pages", []) if isinstance(schema, dict) else [])
        if isinstance(item, dict) and item.get("id")
    }
    element_ids: set[str] = set()
    app = read_json(working_root / "app.json", {})
    _collect_elements(app.get("root_elements", []) if isinstance(app, dict) else [], element_ids)
    pages_root = working_root / "pages"
    if pages_root.is_dir():
        for path in pages_root.glob("*.json"):
            page = read_json(path, {})
            _collect_elements(page.get("elements", []) if isinstance(page, dict) else [], element_ids)
    return page_ids, element_ids


def _collect_elements(items: Any, target: set[str]) -> None:
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id:
            target.add(item_id)
        _collect_elements(item.get("children", []), target)


def _infer_target_type(
    object_id: str,
    *,
    page_ids: set[str],
    element_ids: set[str],
    label: str,
) -> Literal["page", "ui_element"]:
    in_pages = object_id in page_ids
    in_elements = object_id in element_ids
    if in_pages and not in_elements:
        return "page"
    if in_elements and not in_pages:
        return "ui_element"
    raise ValueError(
        f"Cannot infer {label}_type for {object_id}: the exact ID does not identify "
        "one existing page or UI element"
    )


def _generated_link_id(source_id: str, relation: str, target_id: str) -> str:
    readable = _slug(f"{source_id}.{relation}.{target_id}")
    digest = hashlib.sha1(
        f"{source_id}|{relation}|{target_id}".encode("utf-8")
    ).hexdigest()[:8]
    return f"link.{readable[:80]}.{digest}"


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_.-]+", ".", value).strip(".")
    return re.sub(r"\.+", ".", text) or "generated"


def _required_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} must be a non-empty string")
    return text
