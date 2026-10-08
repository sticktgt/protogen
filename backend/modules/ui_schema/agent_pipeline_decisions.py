from __future__ import annotations

from typing import Literal

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

_CONCRETE_EFFECTS = frozenset(
    {
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
)


def decision_consistency_error(
    *,
    classification: str,
    ui_effect: str,
    target_count: int,
) -> str | None:
    """Check only whether model-selected fields form a storable decision."""
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
