from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.ui_schema.agent_schema_io import write_ui_schema_bundle
from backend.modules.ui_schema.agent_validation_rules import validate_ui_links
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
            raise ValueError("links должен быть JSON-массивом, а не строкой")
        return candidate

def write_ui_links(
    *,
    working_root: Path,
    result_root: Path,
    links: list[UiLinkInput | dict[str, Any]],
) -> dict[str, Any]:
    page_ids, element_ids, element_types = _known_targets(working_root)
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
            raise ValueError(f"Повторяющийся id UI-связи: {link_id}")
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
    _validate_incoming_links(
        normalized,
        page_ids=page_ids,
        element_ids=element_ids,
        element_types=element_types,
    )
    merged = _merge_existing_links(working_root, normalized)
    return write_ui_schema_bundle(
        working_root=working_root,
        result_root=result_root,
        files=[{"file_path": "links.json", "content": {"links": merged}}],
        maximum_files=1,
    )


def remove_new_ui_links_by_id(
    *,
    base_root: Path,
    working_root: Path,
    result_root: Path,
    link_ids: list[str],
) -> dict[str, Any]:
    normalized = [str(item or "").strip() for item in link_ids]
    normalized = [item for item in dict.fromkeys(normalized) if item]
    base_data = read_json(base_root / "links.json", {"links": []})
    base_links = base_data.get("links", []) if isinstance(base_data, dict) else []
    base_ids = {
        str(item.get("id") or "")
        for item in base_links if isinstance(item, dict) and str(item.get("id") or "")
    }
    protected = [item for item in normalized if item in base_ids]
    if protected:
        raise ValueError(
            "Нельзя удалить UI-связи из базовой схемы: " + ", ".join(protected)
        )

    data = read_json(working_root / "links.json", {"links": []})
    existing = data.get("links", []) if isinstance(data, dict) else []
    if not isinstance(existing, list):
        raise ValueError("`links.json.links` должен быть массивом")
    existing_ids = {
        str(item.get("id") or "")
        for item in existing
        if isinstance(item, dict) and str(item.get("id") or "")
    }
    missing = [item for item in normalized if item not in existing_ids]
    if missing:
        raise ValueError(
            "Нельзя удалить отсутствующие UI-связи: " + ", ".join(missing)
        )
    remaining = [
        dict(item)
        for item in existing
        if isinstance(item, dict) and str(item.get("id") or "") not in set(normalized)
    ]
    result = write_ui_schema_bundle(
        working_root=working_root,
        result_root=result_root,
        files=[{"file_path": "links.json", "content": {"links": remaining}}],
        maximum_files=1,
    )
    return {
        **result,
        "removed_ui_link_count": len(normalized),
        "removed_ui_link_ids": normalized,
    }

def _validate_incoming_links(
    links: list[dict[str, Any]],
    *,
    page_ids: set[str],
    element_ids: set[str],
    element_types: dict[str, str],
) -> None:
    errors: list[str] = []
    validate_ui_links(
        {"links": links},
        page_ids=page_ids,
        element_ids=element_ids,
        element_types=element_types,
        errors=errors,
    )
    if errors:
        raise ValueError("Технически некорректен links.json: " + " | ".join(errors))

def _merge_existing_links(
    working_root: Path,
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    data = read_json(working_root / "links.json", {"links": []})
    existing = data.get("links", []) if isinstance(data, dict) else []
    if not isinstance(existing, list):
        raise ValueError("`links.json.links` должен быть массивом")

    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(existing):
        if not isinstance(raw, dict):
            raise ValueError(f"links.json.links[{index}] должен быть объектом")
        item = dict(raw)
        link_id = _required_text(item.get("id"), f"links.json.links[{index}].id")
        if link_id in seen_ids:
            raise ValueError(f"Повторяющийся id существующей UI-связи: {link_id}")
        seen_ids.add(link_id)
        result.append(item)

    for item in incoming:
        link_id = str(item["id"])
        same_id = next(
            (index for index, current in enumerate(result) if current.get("id") == link_id),
            None,
        )
        if same_id is not None:
            result[same_id] = dict(item)
            continue

        signature = _link_signature(item)
        same_link = next(
            (
                index
                for index, current in enumerate(result)
                if _link_signature(current) == signature
            ),
            None,
        )
        if same_link is not None:
            replacement = dict(item)
            replacement["id"] = result[same_link]["id"]
            result[same_link] = replacement
            continue
        result.append(dict(item))

    _validate_unique_links(result)
    return result

def _link_signature(item: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(item.get("source_type") or ""),
        str(item.get("source_id") or ""),
        str(item.get("target_type") or ""),
        str(item.get("target_id") or ""),
        str(item.get("relation") or ""),
    )

def _validate_unique_links(links: list[dict[str, Any]]) -> None:
    ids: set[str] = set()
    signatures: set[tuple[str, str, str, str, str]] = set()
    for item in links:
        link_id = str(item.get("id") or "")
        signature = _link_signature(item)
        if link_id in ids:
            raise ValueError(f"После объединения повторяется id UI-связи: {link_id}")
        if signature in signatures:
            raise ValueError(
                "После объединения повторяется UI-связь: "
                + " | ".join(signature)
            )
        ids.add(link_id)
        signatures.add(signature)

def _known_targets(
    working_root: Path,
) -> tuple[set[str], set[str], dict[str, str]]:
    schema = read_json(working_root / "schema.json", {})
    page_ids = {
        str(item.get("id"))
        for item in (schema.get("pages", []) if isinstance(schema, dict) else [])
        if isinstance(item, dict) and item.get("id")
    }
    element_ids: set[str] = set()
    element_types: dict[str, str] = {}
    app = read_json(working_root / "app.json", {})
    _collect_elements(
        app.get("root_elements", []) if isinstance(app, dict) else [],
        element_ids,
        element_types,
    )
    pages_root = working_root / "pages"
    if pages_root.is_dir():
        for path in pages_root.glob("*.json"):
            page = read_json(path, {})
            _collect_elements(
                page.get("elements", []) if isinstance(page, dict) else [],
                element_ids,
                element_types,
            )
    return page_ids, element_ids, element_types

def _collect_elements(
    items: Any,
    target: set[str],
    element_types: dict[str, str],
) -> None:
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id:
            target.add(item_id)
            type_id = item.get("type")
            if isinstance(type_id, str) and type_id:
                element_types[item_id] = type_id
        _collect_elements(item.get("children", []), target, element_types)

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
        f"Невозможно определить {label}_type для {object_id}: точный ID не соответствует "
        "ровно одной существующей странице или UI-элементу"
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
        raise ValueError(f"{label} должен быть непустой строкой")
    return text
