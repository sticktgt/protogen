from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.ui_schema.agent_json_arguments import parse_json_array

ConcreteUiEffect = Literal[
    "display",
    "input",
    "selection",
    "action",
    "navigation",
    "message",
    "state",
    "formatting",
    "layout",
]
UiEffect = Literal[
    "display",
    "input",
    "selection",
    "action",
    "navigation",
    "message",
    "state",
    "formatting",
    "layout",
    "none",
    "unclear",
]
Classification = Literal["direct_ui", "cross_cutting_ui", "no_ui", "unclear"]

_CONCRETE_EFFECTS = {
    "display",
    "input",
    "selection",
    "action",
    "navigation",
    "message",
    "state",
    "formatting",
    "layout",
}


class CoveragePlanTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: Literal["page", "ui_element"]
    target_id: str = Field(min_length=1, description="Exact existing or intended target ID")
    action: Literal["reuse", "extend", "create"]


class CoveragePlanItem(BaseModel):
    """Structurally parsed model-authored coverage decision.

    Cross-field consistency is checked inside the tool implementation so one invalid
    item can be reported with the current workflow context without losing the other
    valid items in the same submission.
    """

    model_config = ConfigDict(extra="forbid")

    requirement_id: str = Field(min_length=1, description="Exact current requirement ID")
    ui_effect: UiEffect = Field(
        description=(
            "Mandatory observable UI effect. This is independent from whether the effect has "
            "one primary target or applies across several places."
        )
    )
    classification: Classification
    targets: list[CoveragePlanTarget] = Field(default_factory=list)
    note: str = Field(
        min_length=1,
        description=(
            "Short factual statement of the mandatory observable outcome, or why no UI "
            "effect can be derived"
        ),
    )

    @field_validator("targets", mode="before")
    @classmethod
    def _decode_targets(cls, value: Any) -> Any:
        return parse_json_array(value)


class TraceabilityTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: Literal["page", "ui_element"]
    target_id: str = Field(min_length=1, description="Exact existing target ID")
    implementation_status: Literal["planned", "in_progress", "implemented"]


class TraceabilityItem(BaseModel):
    """Structurally parsed final traceability decision.

    Semantic-field consistency is deliberately validated by the domain tool, not by
    the tool-call parser. This keeps validation technical while allowing precise,
    recoverable per-requirement errors.
    """

    model_config = ConfigDict(extra="forbid")

    requirement_id: str = Field(min_length=1, description="Exact current requirement ID")
    ui_effect: UiEffect
    classification: Classification
    targets: list[TraceabilityTarget] = Field(default_factory=list)
    reason: str = Field(min_length=1, description="Short factual final assessment reason")

    @field_validator("targets", mode="before")
    @classmethod
    def _decode_targets(cls, value: Any) -> Any:
        return parse_json_array(value)


def decision_consistency_error(
    *,
    classification: str,
    ui_effect: str,
    target_count: int,
) -> str | None:
    """Return a technical cross-field consistency error, if any.

    The function does not infer meaning from requirement text. It only checks that the
    fields selected by the model form a representable decision.
    """

    if classification == "direct_ui":
        if ui_effect not in _CONCRETE_EFFECTS:
            return "direct_ui requires a concrete observable ui_effect"
        if target_count < 1:
            return "direct_ui requires at least one target"
        return None
    if classification == "cross_cutting_ui":
        if ui_effect not in _CONCRETE_EFFECTS:
            return "cross_cutting_ui requires a concrete observable ui_effect"
        return None
    if classification == "no_ui":
        if ui_effect != "none":
            return "no_ui requires ui_effect=none"
        if target_count:
            return "no_ui must not contain targets"
        return None
    if classification == "unclear":
        if ui_effect != "unclear":
            return "unclear requires ui_effect=unclear"
        if target_count:
            return "unclear must not contain targets"
        return None
    return f"Unsupported classification: {classification}"


def validate_decision_consistency(item: CoveragePlanItem | TraceabilityItem) -> None:
    error = decision_consistency_error(
        classification=item.classification,
        ui_effect=item.ui_effect,
        target_count=len(item.targets),
    )
    if error:
        raise ValueError(error)
