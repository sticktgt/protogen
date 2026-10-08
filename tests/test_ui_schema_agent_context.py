from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import types

if "backend.app.state" not in sys.modules:
    app_package = types.ModuleType("backend.app")
    app_package.__path__ = []
    state_module = types.ModuleType("backend.app.state")
    state_module.AppState = type("AppState", (), {})
    sys.modules["backend.app"] = app_package
    sys.modules["backend.app.state"] = state_module

from backend.modules.ui_schema.agent_context import (
    build_synchronization_context,
    write_compact_agent_inputs,
)
from backend.modules.ui_schema.agent_pipeline_context import audit_context
from backend.modules.ui_schema.files import read_json, write_json


def _pipeline_config(*, analysis_batch_size: int = 2) -> dict:
    return {
        "pipeline": {
            "analysis_batch_size": analysis_batch_size,
            "planning_batch_size": analysis_batch_size,
            "audit_batch_size": 3,
            "correction_batch_size": 2,
            "stage_attempts": 2,
            "apply_repair_attempts": 1,
            "validation_repair_attempts": 1,
            "structural_review_candidate_limit": 24,
            "output_contract_prompt": "pipeline_output_contract",
            "change_rules_prompt": "pipeline_change_rules",
            "tool_choice": "required",
            "stages": {},
        },
        "context": {
            "requirement_fields": [
                "id",
                "name",
                "description",
                "acceptanceCriteria",
            ]
        },
    }


def _write_empty_schema(run_path: Path) -> None:
    write_json(run_path / "working/ui_schema/app.json", {"id": "app", "root_elements": []})
    write_json(run_path / "working/ui_schema/schema.json", {"pages": []})
    write_json(run_path / "working/ui_schema/links.json", {"links": []})
    write_json(
        run_path / "working/ui_schema/mappings/requirement_ui_links.json",
        {"links": []},
    )


def test_agent_context_uses_configured_requirement_projection(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    write_json(
        run_path / "input/requirements.json",
        {
            "projects": [{"id": "PROJECT"}],
            "requirements": [
                {
                    "id": "REQ-1",
                    "code": "REQ-1",
                    "name": "Экран",
                    "description": "Показать экран.",
                    "acceptanceCriteria": ["Экран виден."],
                    "types": ["ui"],
                    "criticality": "high",
                    "projectId": "PROJECT",
                }
            ],
        },
    )
    write_json(run_path / "input/task.json", {"operation": "synchronize"})
    _write_empty_schema(run_path)

    context = build_synchronization_context(
        run_path,
        agent_config=_pipeline_config(analysis_batch_size=1),
    )

    assert context["requirements"]["total_count"] == 1
    assert context["requirements"]["items"] == [
        {
            "id": "REQ-1",
            "name": "Экран",
            "description": "Показать экран.",
            "acceptanceCriteria": ["Экран виден."],
        }
    ]
    assert context["pipeline"] == {
        "version": 2,
        "analysis_batch_size": 1,
        "audit_batch_size": 3,
        "stages": [
            "analysis",
            "planning",
            "apply",
            "audit",
            "correction",
            "structural_check",
            "validation",
        ],
    }
    assert read_json(run_path / "input/requirements.json", {})["projects"] == [
        {"id": "PROJECT"}
    ]

    write_compact_agent_inputs(
        run_root=run_path,
        agent_config=_pipeline_config(analysis_batch_size=1),
    )
    stored = read_json(run_path / "input/requirements.agent.json", {})
    assert stored == context["requirements"]
    assert "types" not in stored["items"][0]
    assert "criticality" not in stored["items"][0]


def test_module_config_exposes_pipeline_parameters_and_requirement_projection() -> None:
    import yaml

    config = yaml.safe_load(
        (PROJECT_ROOT / "modules/ui_schema/config.yaml").read_text(encoding="utf-8")
    )

    assert config["agent"]["context"]["requirement_fields"] == [
        "id",
        "name",
        "description",
        "acceptanceCriteria",
    ]
    assert config["agent"]["pipeline"]["analysis_batch_size"] == 24
    assert config["agent"]["pipeline"]["planning_batch_size"] == 12
    assert config["agent"]["pipeline"]["audit_batch_size"] == 40
    assert config["agent"]["pipeline"]["correction_batch_size"] == 12
    assert config["agent"]["pipeline"]["correction_rounds"] == 1
    assert config["agent"]["pipeline"]["structural_review_candidate_limit"] == 24
    assert config["agent"]["execution"]["max_llm_calls"] == 32
    assert config["agent"]["execution"]["max_duration_seconds"] == 1800
    assert "requirement_analysis" not in config["agent"]


def test_audit_context_exposes_current_target_details_without_action_history(
    tmp_path: Path,
) -> None:
    run_path = tmp_path / "run"
    base = run_path / "base/ui_schema"
    working = run_path / "working/ui_schema"
    for root in (base, working):
        write_json(root / "app.json", {"id": "app", "root_elements": []})
        write_json(root / "schema.json", {"pages": []})
        write_json(root / "links.json", {"links": []})
    write_json(
        working / "pages/cards.list.json",
        {
            "id": "cards.list",
            "title": "Карты",
            "elements": [
                {
                    "id": "cards.list.table",
                    "type": "table",
                    "label": "Карты",
                    "children": [],
                }
            ],
        },
    )
    write_json(
        working / "schema.json",
        {
            "pages": [
                {
                    "id": "cards.list",
                    "title": "Карты",
                    "file": "pages/cards.list.json",
                }
            ]
        },
    )
    write_json(
        working / "links.json",
        {
            "links": [
                {
                    "id": "link.cards",
                    "source_type": "page",
                    "source_id": "home",
                    "target_type": "page",
                    "target_id": "cards.list",
                    "relation": "navigates_to",
                }
            ]
        },
    )
    write_json(run_path / "input/task.json", {"operation": "synchronize"})

    context = audit_context(
        run_path=run_path,
        requirements=[{"id": "R-1", "name": "Список карт"}],
        decisions=[
            {
                "requirement_id": "R-1",
                "targets": [
                    {
                        "target_type": "page",
                        "target_id": "cards.list",
                        "action": "create",
                    }
                ],
            }
        ],
    )

    summary = context["target_summaries"]["page:cards.list"]
    assert summary["exists"] is True
    assert "allowed_actions" not in summary
    assert "target_lifecycle" not in context
    assert "decision_target_checks" not in context
    outline = context["target_outlines"]["cards.list"]
    assert outline["elements"][0]["id"] == "cards.list.table"
    assert outline["elements"][0]["parent_id"] == "cards.list"
    assert context["related_ui_links"][0]["id"] == "link.cards"


def test_agent_context_keeps_all_projected_requirements_for_diagnostics(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    write_json(
        run_path / "input/requirements.json",
        {
            "requirements": [
                {"id": "R-1", "name": "First"},
                {"id": "R-2", "name": "Second"},
                {"id": "R-3", "name": "Third"},
            ]
        },
    )
    write_json(run_path / "input/task.json", {"operation": "synchronize"})
    _write_empty_schema(run_path)

    context = build_synchronization_context(
        run_path,
        agent_config={
            **_pipeline_config(analysis_batch_size=2),
            "context": {"requirement_fields": ["id", "name"]},
        },
    )

    assert context["requirements"]["total_count"] == 3
    assert [item["id"] for item in context["requirements"]["items"]] == [
        "R-1",
        "R-2",
        "R-3",
    ]
    assert context["pipeline"]["analysis_batch_size"] == 2


def test_audit_context_includes_descendant_links_for_element_target(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    base = run_path / "base/ui_schema"
    working = run_path / "working/ui_schema"
    for root in (base, working):
        write_json(root / "app.json", {"id": "app", "root_elements": []})
        write_json(root / "schema.json", {"pages": [{"id": "home", "title": "Home"}]})
        write_json(
            root / "pages/home.json",
            {
                "id": "home",
                "title": "Home",
                "elements": [
                    {
                        "id": "home.form",
                        "type": "form",
                        "label": "Форма",
                        "children": [
                            {"id": "home.form.submit", "type": "button", "label": "Отправить"}
                        ],
                    }
                ],
            },
        )
        write_json(
            root / "links.json",
            {
                "links": [
                    {
                        "id": "link.submit",
                        "source_type": "ui_element",
                        "source_id": "home.form.submit",
                        "target_type": "page",
                        "target_id": "home",
                        "relation": "navigates_to",
                    }
                ]
            },
        )
    write_json(run_path / "input/task.json", {"operation": "synchronize"})

    context = audit_context(
        run_path=run_path,
        requirements=[{"id": "R-1", "name": "Форма"}],
        decisions=[
            {
                "requirement_id": "R-1",
                "targets": [
                    {
                        "target_type": "ui_element",
                        "target_id": "home.form",
                        "action": "reuse",
                    }
                ],
            }
        ],
    )

    outline = context["target_outlines"]["home"]
    assert [item["id"] for item in outline["elements"]] == [
        "home.form",
        "home.form.submit",
    ]
    assert outline["elements"][1]["parent_id"] == "home.form"
    assert [item["id"] for item in context["related_ui_links"]] == ["link.submit"]
