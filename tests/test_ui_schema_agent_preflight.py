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

from backend.modules.ui_schema.agent_change_preflight import validate_plan_preflight
from backend.modules.ui_schema.agent_pipeline_models import (
    PipelineChangeBundle,
    PipelineDecision,
    PipelineElementChange,
    PipelinePageDocument,
    PipelinePlanOutput,
    PipelineTarget,
    RequirementAnalysisItem,
)
from backend.modules.ui_schema.agent_pipeline_planning import _apply_plan_with_repair
from backend.modules.ui_schema.agent_target_catalog import build_technical_index
from backend.modules.ui_schema.files import write_json


def _schema(run_path: Path) -> Path:
    root = run_path / "working/ui_schema"
    write_json(
        root / "schema.json",
        {
            "pages": [
                {"id": "page.one", "title": "One", "file": "pages/page.one.json"},
                {"id": "page.two", "title": "Two", "file": "pages/page.two.json"},
            ]
        },
    )
    write_json(root / "app.json", {"id": "app", "root_elements": []})
    write_json(root / "links.json", {"links": []})
    write_json(root / "mappings/requirement_ui_links.json", {"links": []})
    write_json(
        root / "pages/page.one.json",
        {
            "id": "page.one",
            "title": "One",
            "elements": [
                {
                    "id": "page.one.main",
                    "type": "section",
                    "label": "Main",
                    "children": [
                        {
                            "id": "page.one.existing",
                            "type": "text",
                            "label": "Existing",
                        }
                    ],
                }
            ],
        },
    )
    write_json(
        root / "pages/page.two.json",
        {
            "id": "page.two",
            "title": "Two",
            "elements": [
                {"id": "page.two.main", "type": "section", "label": "Other"}
            ],
        },
    )
    write_json(run_path / "input/task.json", {"operation": "synchronize"})
    return root


def _rejected_plan() -> PipelinePlanOutput:
    return PipelinePlanOutput.model_validate(
        {
            "decisions": [
                {
                    "requirement_id": "R-1",
                    "ui_effect": "display",
                    "classification": "direct_ui",
                    "targets": [
                        {
                            "target_type": "ui_element",
                            "target_id": "page.one.existing",
                            "action": "create",
                            "implementation_status": "implemented",
                        }
                    ],
                    "reason": "Показать значение.",
                }
            ],
            "changes": {
                "upsert_elements": [
                    {
                        "page_id": "page.one",
                        "parent_id": "page.one.table",
                        "element": {
                            "id": "page.one.existing",
                            "type": "text",
                            "label": "Moved",
                        },
                    },
                    {
                        "page_id": "page.one",
                        "parent_id": "page.one.main",
                        "element": {
                            "id": "page.one.table",
                            "type": "table",
                            "label": "Table",
                        },
                    },
                    {
                        "page_id": "page.one",
                        "parent_id": "page.one.table",
                        "element": {
                            "id": "page.one.bad_column",
                            "type": "text",
                            "label": "Bad column",
                        },
                    },
                ],
                "ui_links": [
                    {
                        "source_id": "page.one.main",
                        "target_id": "page.one",
                        "relation": "navigates_to",
                    }
                ],
            },
        }
    )


def test_technical_index_exposes_existing_status_actions_and_parent(tmp_path: Path) -> None:
    root = _schema(tmp_path / "run")

    index = build_technical_index(root)

    existing = next(
        item for item in index["elements"] if item["id"] == "page.one.existing"
    )
    assert index["listed_target_status"] == "existing"
    assert index["listed_target_allowed_actions"] == ["reuse", "extend"]
    assert index["missing_target_allowed_actions"] == ["create"]
    assert existing["parent_id"] == "page.one.main"
    assert existing["page_id"] == "page.one"
    assert existing.get("link_source", False) is False


def test_plan_preflight_reports_all_static_errors_together(tmp_path: Path) -> None:
    root = _schema(tmp_path / "run")
    plan = _rejected_plan()

    issues = validate_plan_preflight(
        schema_root=root,
        decisions=plan.decisions,
        changes=plan.changes,
    )

    codes = {item["code"] for item in issues}
    assert {
        "existing_target_with_create",
        "implicit_parent_change",
        "child_type_not_allowed",
        "link_source_not_allowed",
    } <= codes
    implicit = next(item for item in issues if item["code"] == "implicit_parent_change")
    assert implicit["current_parent_id"] == "page.one.main"
    assert implicit["requested_parent_id"] == "page.one.table"


def test_plan_preflight_rejects_app_as_create_pages_document(tmp_path: Path) -> None:
    root = _schema(tmp_path / "run")
    changes = PipelineChangeBundle(
        create_pages=[
            PipelinePageDocument(
                page_id="app",
                title="Application",
                elements=[
                    {
                        "id": "app.top_bar",
                        "type": "top_bar",
                        "label": "Верхняя панель",
                    }
                ],
            )
        ]
    )

    issues = validate_plan_preflight(
        schema_root=root,
        decisions=[],
        changes=changes,
    )

    app_issue = next(item for item in issues if item["code"] == "app_not_a_page")
    assert "upsert_elements" in app_issue["message"]


def test_planning_repair_receives_aggregated_local_context(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    _schema(run_path)
    rejected = _rejected_plan()
    repaired = PipelinePlanOutput(
        decisions=[
            PipelineDecision(
                requirement_id="R-1",
                ui_effect="display",
                classification="direct_ui",
                targets=[
                    PipelineTarget(
                        target_type="ui_element",
                        target_id="page.one.existing",
                        action="extend",
                        implementation_status="implemented",
                    )
                ],
                reason="Существующий элемент обновлён на текущем месте.",
            )
        ],
        changes=PipelineChangeBundle(
            upsert_elements=[
                PipelineElementChange(
                    page_id="page.one",
                    element={
                        "id": "page.one.existing",
                        "type": "text",
                        "label": "Updated",
                    },
                )
            ]
        ),
    )

    class Runtime:
        def __init__(self) -> None:
            self.run_path = run_path
            self.repair_context = None
            self.applied = 0

        def event(self, **_kwargs) -> None:
            return None

        def invoke_validated(self, *, stage, base_context, validator, **_kwargs):
            assert stage == "repair"
            self.repair_context = base_context
            assert validator(repaired) == []
            return repaired

        def apply_changes(self, _changes) -> None:
            self.applied += 1

    runtime = Runtime()
    result = _apply_plan_with_repair(
        runtime=runtime,
        plan=rejected,
        requirement_batch=[{"id": "R-1", "name": "Value"}],
        batch_analysis=[
            RequirementAnalysisItem(
                requirement_id="R-1",
                ui_effect="display",
                classification="direct_ui",
                ui_outcomes=["Значение показано"],
                reason="Наблюдаемый результат.",
            )
        ],
        batch_index=1,
        batch_total=1,
        maximum_repairs=1,
        expected_requirement_ids=["R-1"],
    )

    assert result == repaired
    assert runtime.applied == 1
    context = runtime.repair_context
    assert context is not None
    assert "all_requirement_analysis" not in context
    assert set(context["ui_schema"]["pages"]) == {"page.one.json"}
    assert "page.two.json" not in context["ui_schema"]["pages"]
    assert len(context["technical_issues"]) >= 4
    assert {
        "existing_target_with_create",
        "implicit_parent_change",
        "child_type_not_allowed",
        "link_source_not_allowed",
    } <= {item["code"] for item in context["technical_issues"]}
    assert any(
        item["id"] == "page.one.existing"
        for item in context["technical_index"]["elements"]
    )
