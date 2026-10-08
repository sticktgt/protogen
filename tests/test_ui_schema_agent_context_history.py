from __future__ import annotations

import json

from backend.modules.ui_schema.agent_context_history import (
    compact_agent_messages,
    context_history_settings,
)


def _human(content: str = "run") -> dict:
    return {"role": "user", "content": content}


def _ai(tool: str, call_id: str) -> dict:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"name": tool, "id": call_id, "args": {}}],
    }


def _tool(call_id: str, payload: dict) -> dict:
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": json.dumps(payload, ensure_ascii=False),
    }


def _exchange(tool: str, call_id: str, payload: dict) -> list[dict]:
    return [_ai(tool, call_id), _tool(call_id, payload)]


def _tool_names(messages: list[dict]) -> list[str]:
    result: list[str] = []
    for message in messages:
        for call in message.get("tool_calls", []):
            result.append(call["name"])
    return result


def test_history_compaction_keeps_schema_anchor_and_current_batch_only() -> None:
    load_payload = {
        "requirements": {
            "total_count": 80,
            "current_batch": {"batch_id": "requirements_01", "requirements": [{"id": "R1"}]},
        },
        "ui_schema": {"pages": {"page.json": {"id": "page"}}},
        "element_types": {"page": [{"id": "text"}]},
        "agent_report": {},
        "validation": {},
    }
    messages = [
        _human(),
        *_exchange("load_synchronization_context", "c1", load_payload),
        *_exchange(
            "write_ui_schema_coverage_plan_batch",
            "c2",
            {"next_requirement_batch_context": {"batch_id": "requirements_02"}},
        ),
        *_exchange(
            "write_ui_schema_coverage_plan_batch",
            "c3",
            {"next_requirement_batch_context": {"batch_id": "requirements_03"}},
        ),
    ]

    compacted = compact_agent_messages(messages)

    assert _tool_names(compacted) == [
        "load_synchronization_context",
        "write_ui_schema_coverage_plan_batch",
    ]
    anchor = json.loads(compacted[2]["content"])
    assert anchor["ui_schema"] == load_payload["ui_schema"]
    assert anchor["requirements"]["current_batch"]["omitted_from_history_anchor"] is True
    assert "agent_report" not in anchor
    assert json.loads(compacted[-1]["content"])["next_requirement_batch_context"]["batch_id"] == "requirements_03"


def test_history_compaction_keeps_final_plan_and_recent_change_bundles() -> None:
    messages = [
        _human(),
        *_exchange(
            "load_synchronization_context",
            "c1",
            {"requirements": {"total_count": 2, "current_batch": {}}, "ui_schema": {}},
        ),
        *_exchange(
            "review_ui_schema_coverage_plan",
            "c2",
            {"review_complete": True, "schema_change_plan": {"items": [{"requirement_id": "R1"}]}},
        ),
        *_exchange("apply_ui_schema_changes", "c3", {"ok": False, "error": "retry"}),
        *_exchange("apply_ui_schema_changes", "c4", {"ok": True, "touched_target_ids": ["x"]}),
    ]

    compacted = compact_agent_messages(messages, keep_change_bundle_exchanges=2)

    assert _tool_names(compacted) == [
        "load_synchronization_context",
        "review_ui_schema_coverage_plan",
        "apply_ui_schema_changes",
        "apply_ui_schema_changes",
    ]


def test_traceability_stage_drops_plan_review_but_keeps_change_context() -> None:
    messages = [
        _human(),
        *_exchange(
            "load_synchronization_context",
            "c1",
            {"requirements": {"total_count": 2, "current_batch": {}}, "ui_schema": {}},
        ),
        *_exchange(
            "review_ui_schema_coverage_plan",
            "c2",
            {"review_complete": True, "schema_change_plan": {"items": []}},
        ),
        *_exchange("apply_ui_schema_changes", "c3", {"ok": True, "touched_target_ids": ["new.id"]}),
        *_exchange(
            "write_ui_schema_traceability_batch",
            "c4",
            {"next_requirement_batch_context": {"batch_id": "requirements_02"}},
        ),
    ]

    compacted = compact_agent_messages(messages)

    assert _tool_names(compacted) == [
        "load_synchronization_context",
        "apply_ui_schema_changes",
        "write_ui_schema_traceability_batch",
    ]


def test_context_history_settings_are_configurable() -> None:
    assert context_history_settings({}) == {
        "enabled": True,
        "keep_change_bundle_exchanges": 1,
    }
    assert context_history_settings(
        {
            "context": {
                "history_compaction": {
                    "enabled": False,
                    "keep_change_bundle_exchanges": 2,
                }
            }
        }
    ) == {
        "enabled": False,
        "keep_change_bundle_exchanges": 2,
    }
