from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if "backend.app.state" not in sys.modules:
    app_package = types.ModuleType("backend.app")
    app_package.__path__ = []
    state_module = types.ModuleType("backend.app.state")
    state_module.AppState = type("AppState", (), {})
    sys.modules["backend.app"] = app_package
    sys.modules["backend.app.state"] = state_module

from backend.modules.ui_schema.agent_coverage_plan import (
    coverage_plan_errors,
    write_coverage_plan_batch,
)
from backend.modules.ui_schema.agent_coverage_plan_review import (
    build_coverage_plan_review_context,
    review_coverage_plan,
)
from backend.modules.ui_schema.agent_traceability_dirty import (
    clear_traceability_dirty,
    mark_traceability_targets_dirty,
    traceability_dirty_errors,
)
from backend.modules.ui_schema.files import write_json


def _schema(run_path: Path) -> None:
    write_json(run_path / "working/ui_schema/app.json", {"id": "app", "root_elements": []})
    write_json(run_path / "working/ui_schema/schema.json", {"pages": []})


def test_coverage_plan_is_written_in_mechanical_batches_and_reviewed(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    write_json(
        run_path / "input/requirements.json",
        {
            "requirements": [
                {"id": "R-1", "description": "Visible result"},
                {"id": "R-2", "description": "Internal operation"},
            ]
        },
    )
    _schema(run_path)
    config = {
        "requirement_analysis": {
            "batch_size": 1,
            "coverage_plan_review": {
                "include_classifications": ["no_ui"],
                "include_page_targets": True,
                "shared_target_min_requirements": 0,
            },
        }
    }

    first = write_coverage_plan_batch(
        run_path,
        agent_config=config,
        items=[
            {
                "requirement_id": "R-1",
                "ui_effect": "display",
                "classification": "direct_ui",
                "targets": [
                    {
                        "target_type": "ui_element",
                        "target_id": "page.one.value",
                        "action": "create",
                    }
                ],
                "note": "Show the required visible result in the intended target.",
            }
        ],
    )
    assert first["next_batch_id"] == "requirements_02"
    assert first["batches_complete"] is False
    assert first["next_requirement_batch_context"]["requirement_ids"] == ["R-2"]
    assert first["next_requirement_batch_context"]["requirements"][0]["description"] == "Internal operation"

    second = write_coverage_plan_batch(
        run_path,
        agent_config=config,
        items=[
            {
                "requirement_id": "R-2",
                "ui_effect": "none",
                "classification": "no_ui",
                "note": "No observable result",
            }
        ],
    )
    assert second["batches_complete"] is True
    assert "quality review" in coverage_plan_errors(run_path, agent_config=config)[0]

    context = build_coverage_plan_review_context(run_path, agent_config=config)
    assert context["candidate_count"] == 1
    assert context["candidates"][0]["requirement"]["id"] == "R-2"
    assert "current_plan" not in context["candidates"][0]

    result = review_coverage_plan(
        run_path,
        agent_config=config,
        items=[
            {
                "requirement_id": "R-2",
                "ui_effect": "none",
                "classification": "no_ui",
                "targets": [],
                "note": "The requirement has no observable interface outcome.",
            }
        ],
    )
    assert result["accepted_in_call"] == 1
    assert result["review_complete"] is True
    assert result["schema_change_plan"]["item_count"] == 2
    assert result["schema_change_plan"]["items"][0]["note"]
    assert coverage_plan_errors(run_path, agent_config=config) == []


def test_coverage_plan_batch_keeps_current_batch_when_other_ids_are_submitted(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    write_json(
        run_path / "input/requirements.json",
        {"requirements": [{"id": "R-1"}, {"id": "R-2"}]},
    )
    config = {"requirement_analysis": {"batch_size": 1}}

    result = write_coverage_plan_batch(
        run_path,
        agent_config=config,
        items=[
            {
                "requirement_id": "R-2",
                "ui_effect": "none",
                "classification": "no_ui",
                "note": "No observable result",
            }
        ],
    )

    assert result["ok"] is False
    assert result["remaining_in_batch"] == 1
    assert result["current_requirement_batch_context"]["requirement_ids"] == ["R-1"]
    assert result["item_errors"][0]["requirement_id"] == "R-2"


def test_targeted_review_tracks_only_links_to_changed_targets(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    write_json(run_path / "result/traceability_state.json", {"initialized": True})
    write_json(
        run_path / "working/ui_schema/mappings/requirement_ui_links.json",
        {
            "links": [
                {"requirement_id": "R-1", "target_id": "page.one.value"},
                {"requirement_id": "R-2", "target_id": "page.one.other"},
            ]
        },
    )

    affected = mark_traceability_targets_dirty(run_path, ["page.one.value"])

    assert affected == ["R-1"]
    assert "R-1" in traceability_dirty_errors(run_path)[0]
    assert clear_traceability_dirty(run_path, ["R-1"]) == []
    assert traceability_dirty_errors(run_path) == []


def test_agent_toolset_exposes_batched_plan_and_targeted_reviews(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeTool:
        def __init__(self, function):
            self.name = function.__name__
            self.function = function

    def tool_decorator(function=None, **_kwargs):
        if function is not None:
            return FakeTool(function)
        return lambda decorated: FakeTool(decorated)

    langchain_package = types.ModuleType("langchain")
    langchain_tools = types.ModuleType("langchain.tools")
    langchain_tools.tool = tool_decorator
    monkeypatch.setitem(sys.modules, "langchain", langchain_package)
    monkeypatch.setitem(sys.modules, "langchain.tools", langchain_tools)

    from backend.modules.ui_schema.agent_tools import create_agent_tools

    names = {
        tool.name
        for tool in create_agent_tools(
            run_path=tmp_path / "run",
            agent_config={"execution": {}},
        )
    }

    assert "write_ui_schema_coverage_plan_batch" in names
    assert "review_ui_schema_coverage_plan" in names
    assert "apply_ui_schema_changes" in names
    assert "finalize_ui_schema_changes" in names
    assert "revise_ui_schema_coverage_plan" in names
    assert "write_ui_schema_traceability_batch" in names
    assert "review_ui_schema_traceability" in names
    assert "write_ui_schema_coverage_plan" not in names
    assert "write_ui_schema_page" not in names
    assert "write_ui_schema_elements" not in names


def test_coverage_plan_requires_retained_reasoning_for_each_item(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    write_json(
        run_path / "input/requirements.json",
        {"requirements": [{"id": "R-1"}]},
    )

    with pytest.raises(ValueError, match="note"):
        write_coverage_plan_batch(
            run_path,
            agent_config={"requirement_analysis": {"batch_size": 1}},
                items=[
                {
                    "requirement_id": "R-1",
                    "ui_effect": "none",
                    "classification": "no_ui",
                    "targets": [],
                }
            ],
        )


def test_coverage_review_candidate_selection_does_not_analyze_requirement_text(
    tmp_path: Path,
) -> None:
    run_path = tmp_path / "run"
    write_json(
        run_path / "input/requirements.json",
        {
            "requirements": [
                {
                    "id": "R-1",
                    "description": "The user must see and select a value in the interface.",
                },
                {
                    "id": "R-2",
                    "description": "Internal processing without an interface result.",
                },
            ]
        },
    )
    _schema(run_path)
    write_json(
        run_path / "result/coverage_plan.json",
        {
            "items": [
                {
                    "requirement_id": "R-1",
                    "ui_effect": "selection",
                    "classification": "direct_ui",
                    "targets": [
                        {
                            "target_type": "ui_element",
                            "target_id": "page.one.field",
                            "action": "create",
                        }
                    ],
                    "note": "Represent the visible selection in a field.",
                },
                {
                    "requirement_id": "R-2",
                    "ui_effect": "none",
                    "classification": "no_ui",
                    "targets": [],
                    "note": "No observable result is required.",
                },
            ]
        },
    )
    config = {
        "requirement_analysis": {
            "coverage_plan_review": {
                "include_classifications": ["no_ui"],
                "include_page_targets": False,
                "shared_target_min_requirements": 0,
            }
        }
    }

    context = build_coverage_plan_review_context(run_path, agent_config=config)

    assert [
        item["requirement"]["id"] for item in context["candidates"]
    ] == ["R-2"]


def test_change_tool_returns_first_traceability_batch_after_reviewed_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    class FakeTool:
        def __init__(self, function):
            self.name = function.__name__
            self.function = function

    def tool_decorator(function=None, **_kwargs):
        if function is not None:
            return FakeTool(function)
        return lambda decorated: FakeTool(decorated)

    langchain_package = types.ModuleType("langchain")
    langchain_tools = types.ModuleType("langchain.tools")
    langchain_tools.tool = tool_decorator
    monkeypatch.setitem(sys.modules, "langchain", langchain_package)
    monkeypatch.setitem(sys.modules, "langchain.tools", langchain_tools)

    run_path = tmp_path / "run"
    write_json(
        run_path / "input/requirements.json",
        {"requirements": [{"id": "R-1", "description": "Visible result"}]},
    )
    _schema(run_path)
    write_json(
        run_path / "working/ui_schema/schema.json",
        {"pages": [{"id": "page.one", "title": "Page", "file": "pages/page.one.json"}]},
    )
    write_json(
        run_path / "working/ui_schema/pages/page.one.json",
        {
            "id": "page.one",
            "title": "Page",
            "elements": [
                {
                    "id": "page.one.value",
                    "type": "select",
                    "label": "Visible value",
                }
            ],
        },
    )
    write_json(run_path / "working/ui_schema/links.json", {"links": []})
    write_json(
        run_path / "working/ui_schema/mappings/requirement_ui_links.json",
        {"links": []},
    )
    write_json(
        run_path / "result/coverage_plan.json",
        {
            "items": [
                {
                    "requirement_id": "R-1",
                    "ui_effect": "selection",
                    "classification": "direct_ui",
                    "targets": [
                        {
                            "target_type": "ui_element",
                            "target_id": "page.one.value",
                            "action": "reuse",
                        }
                    ],
                    "note": "The existing target presents the visible result.",
                }
            ]
        },
    )
    write_json(
        run_path / "result/coverage_plan_state.json",
        {
            "completed_batch_ids": ["requirements_01"],
            "batches_complete": True,
            "review_complete": True,
        },
    )
    config = {
        "requirement_analysis": {"batch_size": 1},
        "context": {"requirement_fields": ["id", "description"]},
        "execution": {},
    }

    from backend.modules.ui_schema.agent_tools import create_agent_tools

    tools = {
        tool.name: tool
        for tool in create_agent_tools(run_path=run_path, agent_config=config)
    }
    payload = json.loads(
        tools["apply_ui_schema_changes"].function(
            no_changes_reason="The reviewed plan is already represented."
        )
    )
    assert payload["ok"] is True
    assert payload["next_action"] == "continue_schema_changes_or_finalize"

    finalized = json.loads(tools["finalize_ui_schema_changes"].function())
    assert finalized["ok"] is True
    assert finalized["current_requirement_batch_context"]["requirement_ids"] == ["R-1"]
    assert finalized["next_action"] == "write_ui_schema_traceability_batch"


def test_public_review_context_hides_backend_selection_signals() -> None:
    from backend.modules.ui_schema.agent_review_batches import (
        build_review_batches,
        public_review_batch_context,
    )

    context = {
        "policy": {"selection_is_structural_only": True},
        "candidates": [
            {
                "requirement": {"id": "R-1", "description": "Visible outcome"},
                "selection_signals": ["model_selected_non_direct_class"],
                "related_target_summaries": [],
            }
        ],
    }
    batches = build_review_batches(
        context,
        agent_config={"requirement_analysis": {"review_batch_size": 20}},
        prefix="coverage_review",
    )

    public = public_review_batch_context(
        context,
        batches=batches,
        review_batch_id="coverage_review_01",
        completed_batch_ids=set(),
    )

    assert public["candidates"][0]["requirement"]["id"] == "R-1"
    assert "selection_signals" not in public["candidates"][0]
    assert "related_target_summaries" not in public["candidates"][0]
    assert "selection_signals" not in public["candidates"][0]


def test_finalize_after_traceability_routes_to_dirty_item_rewrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    class FakeTool:
        def __init__(self, function):
            self.name = function.__name__
            self.function = function

    def tool_decorator(function=None, **_kwargs):
        if function is not None:
            return FakeTool(function)
        return lambda decorated: FakeTool(decorated)

    langchain_package = types.ModuleType("langchain")
    langchain_tools = types.ModuleType("langchain.tools")
    langchain_tools.tool = tool_decorator
    monkeypatch.setitem(sys.modules, "langchain", langchain_package)
    monkeypatch.setitem(sys.modules, "langchain.tools", langchain_tools)

    run_path = tmp_path / "run"
    write_json(
        run_path / "input/requirements.json",
        {"requirements": [{"id": "R-1", "description": "Visible result"}]},
    )
    write_json(
        run_path / "working/ui_schema/app.json",
        {"id": "app", "root_elements": []},
    )
    write_json(
        run_path / "working/ui_schema/schema.json",
        {"pages": [{"id": "page.one", "file": "pages/page.one.json"}]},
    )
    write_json(
        run_path / "working/ui_schema/pages/page.one.json",
        {
            "id": "page.one",
            "title": "Page",
            "elements": [{"id": "page.one.value", "type": "text", "label": "Value"}],
        },
    )
    write_json(
        run_path / "base/ui_schema/app.json",
        {"id": "app", "root_elements": []},
    )
    write_json(
        run_path / "base/ui_schema/schema.json",
        {"pages": [{"id": "page.one", "file": "pages/page.one.json"}]},
    )
    write_json(
        run_path / "base/ui_schema/pages/page.one.json",
        {
            "id": "page.one",
            "title": "Page",
            "elements": [{"id": "page.one.value", "type": "text", "label": "Value"}],
        },
    )
    write_json(run_path / "working/ui_schema/links.json", {"links": []})
    write_json(
        run_path / "working/ui_schema/mappings/requirement_ui_links.json",
        {
            "links": [
                {
                    "id": "link-1",
                    "requirement_id": "R-1",
                    "target_type": "ui_element",
                    "target_id": "page.one.value",
                    "relation": "implemented_by",
                    "implementation_status": "implemented",
                }
            ]
        },
    )
    write_json(
        run_path / "result/coverage_plan.json",
        {
            "items": [
                {
                    "requirement_id": "R-1",
                    "ui_effect": "display",
                    "classification": "direct_ui",
                    "targets": [
                        {
                            "target_type": "ui_element",
                            "target_id": "page.one.value",
                            "action": "reuse",
                        }
                    ],
                    "note": "Visible result",
                }
            ]
        },
    )
    write_json(
        run_path / "result/coverage_plan_state.json",
        {
            "completed_batch_ids": ["requirements_01"],
            "batches_complete": True,
            "review_complete": True,
        },
    )
    write_json(
        run_path / "result/traceability_state.json",
        {"initialized": True, "initial_batches_complete": True, "review_complete": True},
    )
    write_json(
        run_path / "result/traceability_items.json",
        {
            "items": [
                {
                    "requirement_id": "R-1",
                    "ui_effect": "display",
                    "classification": "direct_ui",
                    "targets": [
                        {
                            "target_type": "ui_element",
                            "target_id": "page.one.value",
                            "implementation_status": "implemented",
                        }
                    ],
                    "reason": "Visible result",
                }
            ]
        },
    )
    write_json(
        run_path / "result/traceability_dirty.json",
        {"requirement_ids": ["R-1"], "target_ids": ["page.one.value"]},
    )
    config = {
        "requirement_analysis": {"batch_size": 1},
        "context": {"requirement_fields": ["id", "description"]},
        "execution": {},
    }

    from backend.modules.ui_schema.agent_tools import create_agent_tools

    tools = {tool.name: tool for tool in create_agent_tools(run_path=run_path, agent_config=config)}
    result = json.loads(tools["finalize_ui_schema_changes"].function())

    assert result["next_action"] == "rewrite_dirty_traceability_items"
    assert result["traceability_correction_context"]["requirement_ids"] == ["R-1"]
    assert "traceability_start_batch_context" not in result


def test_coverage_review_accepts_partial_group_and_returns_only_remaining_candidate(
    tmp_path: Path,
) -> None:
    run_path = tmp_path / "run"
    write_json(
        run_path / "input/requirements.json",
        {
            "requirements": [
                {"id": "R-1", "description": "First visible rule"},
                {"id": "R-2", "description": "Second visible rule"},
            ]
        },
    )
    _schema(run_path)
    config = {
        "requirement_analysis": {
            "batch_size": 2,
            "review_batch_size": 2,
            "coverage_plan_review": {
                "include_classifications": ["no_ui"],
                "include_page_targets": False,
                "shared_target_min_requirements": 0,
            },
        }
    }
    write_coverage_plan_batch(
        run_path,
        agent_config=config,
        items=[
            {
                "requirement_id": "R-1",
                "ui_effect": "none",
                "classification": "no_ui",
                "targets": [],
                "note": "No observable result in first pass.",
            },
            {
                "requirement_id": "R-2",
                "ui_effect": "none",
                "classification": "no_ui",
                "targets": [],
                "note": "No observable result in first pass.",
            },
        ],
    )
    context = build_coverage_plan_review_context(run_path, agent_config=config)
    write_json(run_path / "result/coverage_plan_review_pending.json", context)

    partial = review_coverage_plan(
        run_path,
        agent_config=config,
        items=[
            {
                "requirement_id": "R-1",
                "ui_effect": "display",
                "classification": "direct_ui",
                "targets": [
                    {
                        "target_type": "ui_element",
                        "target_id": "page.one.first",
                        "action": "create",
                    }
                ],
                "note": "The first result must be displayed.",
            }
        ],
    )

    assert partial["review_complete"] is False
    assert partial["remaining_in_batch"] == 1
    assert [
        item["requirement"]["id"]
        for item in partial["quality_review_context"]["candidates"]
    ] == ["R-2"]

    completed = review_coverage_plan(
        run_path,
        agent_config=config,
        items=[
            {
                "requirement_id": "R-2",
                "ui_effect": "display",
                "classification": "direct_ui",
                "targets": [
                    {
                        "target_type": "ui_element",
                        "target_id": "page.one.second",
                        "action": "create",
                    }
                ],
                "note": "The second result must be displayed.",
            }
        ],
    )

    assert completed["review_complete"] is True
    assert completed["schema_change_plan"]["item_count"] == 2
