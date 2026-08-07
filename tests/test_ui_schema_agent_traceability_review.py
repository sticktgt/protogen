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

from backend.modules.ui_schema.agent_pipeline_audit import validate_audit_output
from backend.modules.ui_schema.agent_pipeline_context import audit_context
from backend.modules.ui_schema.agent_pipeline_models import (
    PipelineAuditIssue,
    PipelineAuditOutput,
)
from backend.modules.ui_schema.files import write_json


def test_pipeline_audit_context_contains_actual_neutral_target_facts(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    write_json(run_path / "input/task.json", {"operation": "synchronize"})
    write_json(
        run_path / "working/ui_schema/schema.json",
        {
            "pages": [
                {"id": "page.one", "title": "Page", "file": "pages/page.one.json"}
            ]
        },
    )
    write_json(run_path / "working/ui_schema/app.json", {"id": "app", "root_elements": []})
    write_json(run_path / "working/ui_schema/links.json", {"links": []})
    write_json(
        run_path / "working/ui_schema/mappings/requirement_ui_links.json",
        {"links": []},
    )
    write_json(
        run_path / "working/ui_schema/pages/page.one.json",
        {
            "id": "page.one",
            "title": "Page",
            "elements": [
                {
                    "id": "page.one.panel",
                    "type": "section",
                    "label": "Panel",
                    "children": [],
                }
            ],
        },
    )

    context = audit_context(
        run_path=run_path,
        requirements=[{"id": "R-1", "name": "Requirement"}],
        decisions=[
            {
                "requirement_id": "R-1",
                "ui_effect": "display",
                "classification": "direct_ui",
                "targets": [
                    {
                        "target_type": "ui_element",
                        "target_id": "page.one.panel",
                        "action": "reuse",
                        "implementation_status": "implemented",
                    }
                ],
                "reason": "Visible result",
            }
        ],
    )

    summary = context["target_summaries"]["ui_element:page.one.panel"]
    assert summary["exists"] is True
    assert summary["element_type"] == "section"
    assert summary["child_count"] == 0
    assert summary["parent_id"] == "page.one"


def test_pipeline_audit_accepts_issue_only_output_for_current_batch() -> None:
    output = PipelineAuditOutput(
        issues=[
            PipelineAuditIssue(
                requirement_id="R-1",
                issue="Target is incomplete",
            )
        ]
    )

    assert validate_audit_output(output, ["R-1", "R-2"]) == []
    assert validate_audit_output(PipelineAuditOutput(), ["R-1", "R-2"]) == []


def test_pipeline_audit_rejects_unrelated_issue_ids() -> None:
    output = PipelineAuditOutput(
        issues=[
            PipelineAuditIssue(
                requirement_id="R-X",
                issue="Wrong item",
            )
        ]
    )

    errors = validate_audit_output(output, ["R-1", "R-2"])
    assert any("outside current batch" in item for item in errors)


def test_pipeline_audit_batches_only_direct_ui_requirements(tmp_path: Path) -> None:
    from backend.modules.ui_schema.agent_pipeline_audit import run_audit_batches
    from backend.modules.ui_schema.agent_pipeline_models import PipelineDecision
    from backend.modules.ui_schema.files import read_json

    run_path = tmp_path / "run"
    write_json(run_path / "input/task.json", {"operation": "synchronize"})
    write_json(run_path / "working/ui_schema/schema.json", {"pages": []})
    write_json(run_path / "working/ui_schema/app.json", {"id": "app", "root_elements": []})
    write_json(run_path / "working/ui_schema/links.json", {"links": []})

    requirements = [
        {"id": f"D-{index}", "name": f"Direct {index}"}
        for index in range(41)
    ] + [
        {"id": f"N-{index}", "name": f"No UI {index}"}
        for index in range(30)
    ] + [
        {"id": f"C-{index}", "name": f"Cross {index}"}
        for index in range(20)
    ]
    decisions = [
        PipelineDecision(
            requirement_id=item["id"],
            ui_effect="display" if item["id"].startswith("D-") else "none",
            classification=(
                "direct_ui"
                if item["id"].startswith("D-")
                else "no_ui"
                if item["id"].startswith("N-")
                else "cross_cutting_ui"
            ),
            targets=[],
            reason="Тестовое решение",
        )
        for item in requirements
    ]

    class Runtime:
        def __init__(self) -> None:
            self.run_path = run_path
            self.batches: list[list[str]] = []

        def ensure_not_cancelled(self) -> None:
            return None

        def invoke_validated(self, *, base_context, validator, **_kwargs):
            ids = [item["id"] for item in base_context["requirements"]]
            self.batches.append(ids)
            output = PipelineAuditOutput()
            assert validator(output) == []
            return output

    runtime = Runtime()
    issues, warnings, batch_count = run_audit_batches(
        runtime=runtime,
        requirements=requirements,
        decisions=decisions,
        batch_size=40,
    )

    assert issues == []
    assert warnings == []
    assert batch_count == 2
    assert [len(batch) for batch in runtime.batches] == [40, 1]
    assert all(item.startswith("D-") for batch in runtime.batches for item in batch)
    assert read_json(run_path / "result/audit.json", {})["total_batches"] == 2


def test_pipeline_audit_skips_non_direct_ui_without_llm_call(tmp_path: Path) -> None:
    from backend.modules.ui_schema.agent_pipeline_audit import run_audit_batches
    from backend.modules.ui_schema.agent_pipeline_models import PipelineDecision
    from backend.modules.ui_schema.files import read_json

    run_path = tmp_path / "run"
    write_json(run_path / "input/task.json", {"operation": "synchronize"})
    write_json(run_path / "working/ui_schema/schema.json", {"pages": []})
    write_json(run_path / "working/ui_schema/app.json", {"id": "app", "root_elements": []})
    write_json(run_path / "working/ui_schema/links.json", {"links": []})

    requirements = [
        {"id": "N-1", "name": "No UI"},
        {"id": "C-1", "name": "Cross"},
    ]
    decisions = [
        PipelineDecision(
            requirement_id="N-1",
            ui_effect="none",
            classification="no_ui",
            targets=[],
            reason="Нет отдельного UI",
        ),
        PipelineDecision(
            requirement_id="C-1",
            ui_effect="state",
            classification="cross_cutting_ui",
            targets=[],
            reason="Сквозное правило",
        ),
    ]

    class Runtime:
        def __init__(self) -> None:
            self.run_path = run_path

        def ensure_not_cancelled(self) -> None:
            return None

        def invoke_validated(self, **_kwargs):
            raise AssertionError("LLM audit не должен вызываться")

    issues, warnings, batch_count = run_audit_batches(
        runtime=Runtime(),
        requirements=requirements,
        decisions=decisions,
        batch_size=40,
    )

    assert issues == []
    assert warnings == []
    assert batch_count == 0
    assert read_json(run_path / "result/audit.json", {}) == {
        "completed_batches": 0,
        "total_batches": 0,
        "issues": [],
        "warnings": [],
    }
