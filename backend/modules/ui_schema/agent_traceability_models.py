from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.ui_schema.agent_json_arguments import parse_json_array

from backend.modules.ui_schema.agent_requirement_decisions import TraceabilityItem


class TraceabilityWriteArgs(BaseModel):
    """One classified record per unresolved requirement in the current stage."""

    model_config = ConfigDict(extra="forbid")

    items: list[TraceabilityItem] = Field(
        min_length=1,
        description=(
            "Fresh complete final classification items for unresolved requirements in the "
            "current batch, or targeted corrected requirements after review. The backend "
            "infers the current batch and preserves valid submitted items."
        ),
    )
    agent_note: str = Field(default="")
    warnings: list[str] = Field(default_factory=list)

    @field_validator("items", "warnings", mode="before")
    @classmethod
    def _decode_json_arrays(cls, value: Any) -> Any:
        return parse_json_array(value)


def traceability_items_to_storage(
    items: list[TraceabilityItem],
    *,
    agent_note: str = "",
    warnings: list[str] | None = None,
) -> tuple[dict, dict]:
    links: list[dict] = []
    cross_cutting_ui: list[dict] = []
    no_ui: list[dict] = []
    unclear: list[dict] = []
    for item in items:
        for target in item.targets:
            links.append(
                {
                    "requirement_id": item.requirement_id,
                    **target.model_dump(exclude_none=True),
                    "relation": "implemented_by",
                }
            )
        if item.classification == "cross_cutting_ui":
            cross_cutting_ui.append(
                {
                    "requirement_id": item.requirement_id,
                    "reason": item.reason,
                    "scope": "targeted" if item.targets else "global",
                }
            )
        elif item.classification == "no_ui":
            no_ui.append({"requirement_id": item.requirement_id, "reason": item.reason})
        elif item.classification == "unclear":
            unclear.append({"requirement_id": item.requirement_id, "reason": item.reason})
    return (
        {"links": links},
        {
            "agent_note": str(agent_note or ""),
            "cross_cutting_ui": cross_cutting_ui,
            "no_ui": no_ui,
            "unclear": unclear,
            "warnings": list(warnings or []),
        },
    )
