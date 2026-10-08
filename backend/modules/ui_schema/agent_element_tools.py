from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.modules.ui_schema.agent_element_payloads import UiElementPayload
from backend.modules.ui_schema.agent_tool_payloads import decode_json_argument


class SingleElementPayload(BaseModel):
    """One UI element for a targeted create or update."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(description="Exact stable dotted UI element ID")
    type: str = Field(description="Exact element type ID from synchronization context")
    label: str = Field(description="Non-empty human-readable element label")
    title: str | None = Field(default=None)
    children: list[UiElementPayload] | None = Field(
        default=None,
        description=(
            "Allowed when creating a fully new subtree. Omit when updating an existing "
            "element; update or create child elements as separate targeted changes."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_payload(cls, value: Any):
        candidate = decode_json_argument(value, label="element")
        if not isinstance(candidate, dict):
            return candidate
        result = dict(candidate)
        label = result.get("label")
        if not isinstance(label, str) or not label.strip():
            for key in ("title", "text", "name", "placeholder"):
                candidate_label = result.get(key)
                if isinstance(candidate_label, str) and candidate_label.strip():
                    result["label"] = candidate_label.strip()
                    break
        return result

    @field_validator("id", "type", "label")
    @classmethod
    def require_text(cls, value: str, info):
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{info.field_name} must be a non-empty string")
        return text


class PageElementWriteArgs(BaseModel):
    """Create or update one element without resending a whole document."""

    model_config = ConfigDict(extra="forbid")

    page_id: str = Field(description="Exact existing page ID, or app for app.json")
    parent_id: str | None = Field(
        default=None,
        description=(
            "Required for a new element; use page_id for the document root. Omit for "
            "an existing element to preserve its current parent."
        ),
    )
    element: SingleElementPayload
    position: int | None = Field(default=None, ge=0)

    @field_validator("page_id")
    @classmethod
    def normalize_page_id(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text or "/" in text or "\\" in text:
            raise ValueError("page_id must be a non-empty dotted identifier")
        return text

    @field_validator("parent_id")
    @classmethod
    def normalize_parent_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


def write_page_element(
    *,
    working_root: Path,
    page_id: str,
    parent_id: str | None,
    element: SingleElementPayload | dict[str, Any],
    position: int | None,
) -> dict[str, Any]:
    """Write one element through the same safe logic as the batch tool."""
    from backend.modules.ui_schema.agent_element_batch_tools import write_one_page_element

    return write_one_page_element(
        working_root=working_root,
        page_id=page_id,
        parent_id=parent_id,
        element=element,
        position=position,
    )
