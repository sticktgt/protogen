from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.modules.ui_schema.agent_pipeline_output import extract_stage_payload


def test_extracts_normalized_tool_envelope() -> None:
    response = {
        "tool_calls": [
            {
                "name": "submit_stage",
                "args": {"payload": {"items": [{"requirement_id": "R-1"}]}},
            }
        ]
    }

    assert extract_stage_payload(response, expected_name="submit_stage") == {
        "items": [{"requirement_id": "R-1"}]
    }


def test_extracts_openai_compatible_raw_tool_call() -> None:
    response = {
        "additional_kwargs": {
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "submit_stage",
                        "arguments": '{"payload":{"issues":[]}}',
                    },
                }
            ]
        }
    }

    assert extract_stage_payload(response, expected_name="submit_stage") == {
        "issues": []
    }


def test_accepts_exact_json_content_when_provider_ignores_tool_channel() -> None:
    response = {"content": '{"items":[],"warnings":[]}'}

    assert extract_stage_payload(response, expected_name="submit_stage") == {
        "items": [],
        "warnings": [],
    }


def test_accepts_text_content_blocks_and_fenced_json() -> None:
    response = {
        "content": [
            {
                "type": "text",
                "text": '```json\n{"payload":{"issues":[]}}\n```',
            }
        ]
    }

    assert extract_stage_payload(response, expected_name="submit_stage") == {
        "issues": []
    }
