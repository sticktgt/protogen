from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.modules.ui_schema.agent_requirement_decisions import validate_decision_consistency
from backend.modules.ui_schema.agent_traceability_models import (
    TraceabilityWriteArgs,
    traceability_items_to_storage,
)
from backend.modules.ui_schema.agent_tool_trace import tool_argument_summary


def test_unified_traceability_payload_is_compact_and_unambiguous() -> None:
    payload = TraceabilityWriteArgs.model_validate(
        {
            "items": [
                {
                    "requirement_id": "REQ-1",
                    "ui_effect": "display",
                    "classification": "direct_ui",
                    "targets": [
                        {
                            "target_type": "page",
                            "target_id": "home",
                            "implementation_status": "implemented",
                        }
                    ],
                    "reason": "The required content is visible on the target.",
                },
                {
                    "requirement_id": "REQ-2",
                    "ui_effect": "none",
                    "classification": "no_ui",
                    "targets": [],
                    "reason": "Чистая внутренняя операция без наблюдаемого результата.",
                },
            ],
            "agent_note": "Проверено по фактической схеме.",
        }
    )

    assert payload.items[0].targets[0].implementation_status == "implemented"
    assert not hasattr(payload.items[0].targets[0], "relation")
    assert not hasattr(payload.items[0].targets[0], "id")
    summary = tool_argument_summary(
        "write_ui_schema_traceability_batch",
        payload.model_dump(exclude_none=True),
    )
    assert summary["items"] == 2


def test_old_parallel_traceability_arrays_are_rejected() -> None:
    with pytest.raises(ValidationError):
        TraceabilityWriteArgs.model_validate(
            {
                "requirement_links": [],
                "no_ui": [],
            }
        )



def test_cross_cutting_ui_uses_a_concrete_effect_and_optional_targets() -> None:
    global_item = TraceabilityWriteArgs.model_validate(
        {
            "items": [
                {
                    "requirement_id": "REQ-1",
                    "ui_effect": "formatting",
                    "classification": "cross_cutting_ui",
                    "targets": [],
                    "reason": "The formatting rule applies across the interface.",
                }
            ]
        }
    ).items[0]
    targeted_item = TraceabilityWriteArgs.model_validate(
        {
            "items": [
                {
                    "requirement_id": "REQ-2",
                    "ui_effect": "message",
                    "classification": "cross_cutting_ui",
                    "targets": [
                        {
                            "target_type": "page",
                            "target_id": "page.one",
                            "implementation_status": "in_progress",
                        }
                    ],
                    "reason": "The same message rule applies to several related flows.",
                }
            ]
        }
    ).items[0]

    links, report = traceability_items_to_storage([global_item, targeted_item])
    assert links["links"][0]["relation"] == "implemented_by"
    assert report["cross_cutting_ui"] == [
        {"requirement_id": "REQ-1", "reason": global_item.reason, "scope": "global"},
        {"requirement_id": "REQ-2", "reason": targeted_item.reason, "scope": "targeted"},
    ]


def test_model_facing_traceability_target_rejects_custom_relation() -> None:
    with pytest.raises(ValidationError):
        TraceabilityWriteArgs.model_validate(
            {
                "items": [
                    {
                        "requirement_id": "REQ-1",
                        "ui_effect": "navigation",
                        "classification": "direct_ui",
                        "targets": [
                            {
                                "target_type": "ui_element",
                                "target_id": "nav.item",
                                "implementation_status": "implemented",
                                "relation": "provides_access",
                            }
                        ],
                        "reason": "The navigation item provides access.",
                    }
                ]
            }
        )

def test_batch_tool_trace_keeps_page_and_element_ids_from_structured_models() -> None:
    from backend.modules.ui_schema.agent_element_batch_tools import PageElementChange
    from backend.modules.ui_schema.agent_tool_observability import extract_tool_args

    args = extract_tool_args(
        {
            "changes": [
                PageElementChange.model_validate(
                    {
                        "page_id": "page.alpha",
                        "parent_id": "page.alpha.table",
                        "element": {
                            "id": "page.alpha.table.status",
                            "type": "table_column",
                            "label": "Статус",
                        },
                    }
                ),
                PageElementChange.model_validate(
                    {
                        "page_id": "page.beta",
                        "parent_id": "page.beta.table",
                        "element": {
                            "id": "page.beta.table.reference",
                            "type": "table_column",
                            "label": "Связанное значение",
                        },
                    }
                ),
            ]
        }
    )

    summary = tool_argument_summary("write_ui_schema_elements", args)
    assert summary["changes"] == 2
    assert summary["page_ids"] == ["page.alpha", "page.beta"]
    assert summary["element_ids"] == [
        "page.alpha.table.status",
        "page.beta.table.reference",
    ]


def test_traceability_accepts_explicit_in_progress_status() -> None:
    payload = TraceabilityWriteArgs.model_validate(
        {
            "items": [
                {
                    "requirement_id": "REQ-1",
                    "ui_effect": "display",
                    "classification": "direct_ui",
                    "targets": [
                        {
                            "target_type": "ui_element",
                            "target_id": "overview.result",
                            "implementation_status": "in_progress",
                        }
                    ],
                    "reason": "The target is relevant but incomplete.",
                }
            ]
        }
    )

    assert payload.items[0].targets[0].implementation_status == "in_progress"


def test_traceability_requires_explicit_implementation_status() -> None:
    with pytest.raises(ValidationError):
        TraceabilityWriteArgs.model_validate(
            {
                "items": [
                    {
                        "requirement_id": "REQ-1",
                        "ui_effect": "display",
                        "classification": "direct_ui",
                        "targets": [
                            {
                                "target_type": "page",
                                "target_id": "overview",
                            }
                        ],
                        "reason": "Visible result.",
                    }
                ]
            }
        )


def test_traceability_reports_inconsistent_effect_and_classification_inside_tool() -> None:
    payload = TraceabilityWriteArgs.model_validate(
        {
            "items": [
                {
                    "requirement_id": "REQ-1",
                    "ui_effect": "display",
                    "classification": "no_ui",
                    "targets": [],
                    "reason": "Inconsistent on purpose.",
                }
            ]
        }
    )

    with pytest.raises(ValueError, match="no_ui requires ui_effect=none"):
        validate_decision_consistency(payload.items[0])


def test_traceability_rejects_removed_reset_argument() -> None:
    with pytest.raises(ValidationError):
        TraceabilityWriteArgs.model_validate({"reset": True, "items": []})


def test_traceability_rejects_removed_review_completion_flag() -> None:
    with pytest.raises(ValidationError):
        TraceabilityWriteArgs.model_validate({"review_complete": True, "items": []})
