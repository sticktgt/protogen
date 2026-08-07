from __future__ import annotations

import sys
import types
from pathlib import Path

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

from backend.modules.ui_schema.agent_coverage_plan import revise_coverage_plan_items
from backend.modules.ui_schema.agent_coverage_plan_execution import (
    build_coverage_plan_execution_report,
    finalize_coverage_plan_execution,
)
from backend.modules.ui_schema.files import read_json, write_json


def _prepare_run(tmp_path: Path, *, action: str, target_id: str = "page.one.value") -> Path:
    run_path = tmp_path / "run"
    write_json(
        run_path / "input/requirements.json",
        {"requirements": [{"id": "R-1", "description": "Observable result"}]},
    )
    for root_name in ("base", "working"):
        schema_root = run_path / root_name / "ui_schema"
        write_json(
            schema_root / "schema.json",
            {
                "schema_version": "0.1",
                "application": {"name": "Sample"},
                "pages": [
                    {"id": "page.one", "title": "Page", "file": "pages/page.one.json"}
                ],
            },
        )
        write_json(schema_root / "app.json", {"id": "app", "root_elements": []})
        write_json(
            schema_root / "pages/page.one.json",
            {
                "id": "page.one",
                "title": "Page",
                "elements": [
                    {
                        "id": "page.one.main",
                        "type": "section",
                        "label": "Main",
                        "children": [
                            {
                                "id": "page.one.value",
                                "type": "text",
                                "label": "Existing value",
                            }
                        ],
                    }
                ],
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
                            "target_id": target_id,
                            "action": action,
                        }
                    ],
                    "note": "Represent the observable result in the selected target.",
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
    return run_path


def test_unchanged_planned_extend_is_a_nonblocking_review_observation(tmp_path: Path) -> None:
    run_path = _prepare_run(tmp_path, action="extend")

    report = build_coverage_plan_execution_report(run_path)

    assert report["complete"] is True
    assert report["gaps"] == []
    assert report["observations"] == [
        {
            "requirement_id": "R-1",
            "target_type": "ui_element",
            "target_id": "page.one.value",
            "planned_action": "extend",
            "signal": "planned_extend_target_unchanged",
        }
    ]

    finalized = finalize_coverage_plan_execution(run_path)
    assert finalized["ok"] is True
    assert finalized["observation_count"] == 1

def test_planned_create_requires_the_target_to_appear(tmp_path: Path) -> None:
    run_path = _prepare_run(
        tmp_path,
        action="create",
        target_id="page.one.new_value",
    )

    report = finalize_coverage_plan_execution(run_path)

    assert report["ok"] is False
    assert report["gaps"][0]["signal"] == "planned_create_target_missing"


def test_model_can_still_explicitly_revise_an_extend_to_reuse(tmp_path: Path) -> None:
    run_path = _prepare_run(tmp_path, action="extend")
    assert finalize_coverage_plan_execution(run_path)["ok"] is True

    revised = revise_coverage_plan_items(
        run_path,
        items=[
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
                "note": "The existing target already contains the observable result.",
            }
        ],
        reason="The reviewed target already provides the required result.",
    )

    assert revised["revised_requirement_ids"] == ["R-1"]
    finalized = finalize_coverage_plan_execution(run_path)
    assert finalized["ok"] is True
    assert finalized["checked_target_count"] == 0



def test_empty_planned_group_target_is_a_nonblocking_review_observation(tmp_path: Path) -> None:
    run_path = _prepare_run(
        tmp_path,
        action="create",
        target_id="page.one.empty_group",
    )
    page_path = run_path / "working/ui_schema/pages/page.one.json"
    page = read_json(page_path, {})
    page["elements"].append(
        {
            "id": "page.one.empty_group",
            "type": "section",
            "label": "Empty group",
            "children": [],
        }
    )
    write_json(page_path, page)

    report = finalize_coverage_plan_execution(run_path)

    assert report["ok"] is True
    assert report["gaps"] == []
    assert report["observations"][0]["signal"] == "planned_group_target_empty"
    assert report["observations"][0]["target_facts"]["child_count"] == 0
