from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.modules.ui_schema.agent_tool_payloads import decode_json_argument


class UiElementPayload(BaseModel):
    """Structured tool payload for one UI element.

    ``label`` is published as required in the tool JSON Schema. For compatibility
    with providers that still emit the historic ``title`` field, the validator
    copies a non-empty title into label before normal validation.
    """

    model_config = ConfigDict(extra="allow")

    id: str = Field(description="Stable dotted UI element ID")
    type: str = Field(
        description=(
            "Exact element type ID from the synchronization context. A table child representing "
            "a column uses table_column. app.json uses only app-scoped types such as app_text "
            "and app_action inside top_bar."
        )
    )
    label: str = Field(description="Non-empty human-readable element label")
    title: str | None = Field(
        default=None,
        description="Optional legacy/display title; label is still required",
    )
    children: list["UiElementPayload"] = Field(
        default_factory=list,
        description=(
            "Native JSON array of child UI element objects. Respect the parent type's "
            "allowed_children list from the synchronization context."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_label(cls, value: Any):
        if not isinstance(value, dict):
            return value
        result = dict(value)
        label = result.get("label")
        if not isinstance(label, str) or not label.strip():
            for key in ("title", "text", "name", "placeholder"):
                candidate = result.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    result["label"] = candidate.strip()
                    break
        return result

    @field_validator("id", "type", "label")
    @classmethod
    def require_text(cls, value: str, info):
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{info.field_name} must be a non-empty string")
        return text

    @field_validator("children", mode="before")
    @classmethod
    def normalize_children(cls, value: Any):
        if value in (None, ""):
            return []
        candidate = decode_json_argument(value, label="element children")
        if not isinstance(candidate, list):
            raise ValueError("children must be a native JSON array")
        return candidate


def plain_element_list(items: list[UiElementPayload | dict[str, Any]] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items or []:
        if isinstance(item, BaseModel):
            result.append(item.model_dump(exclude_none=True))
        else:
            result.append(dict(item))
    return result
