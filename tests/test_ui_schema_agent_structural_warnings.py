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

from backend.modules.ui_schema.agent_pipeline_models import PipelineDecision, PipelineTarget
from backend.modules.ui_schema.agent_structural_warnings import collect_structural_warnings
from backend.modules.ui_schema.files import read_json, write_json


class _Runtime:
    def __init__(self, run_path: Path) -> None:
        self.run_path = run_path


def _write_schema(root: Path, *, include_page_link: bool) -> None:
    write_json(
        root / "app.json",
        {
            "id": "app",
            "root_elements": [
                {
                    "id": "app.main_menu",
                    "type": "main_menu",
                    "label": "Меню",
                    "children": [],
                }
            ],
        },
    )
    write_json(
        root / "schema.json",
        {"pages": [{"id": "cards.list", "title": "Карты"}]},
    )
    write_json(
        root / "pages/cards.list.json",
        {"id": "cards.list", "title": "Карты", "elements": []},
    )
    links = []
    if include_page_link:
        links.append(
            {
                "id": "link.menu.cards",
                "source_type": "ui_element",
                "source_id": "app.main_menu",
                "target_type": "page",
                "target_id": "cards.list",
                "relation": "navigates_to",
            }
        )
    write_json(root / "links.json", {"links": links})


def test_structural_candidates_become_warnings_without_schema_changes(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    base = run_path / "base/ui_schema"
    working = run_path / "working/ui_schema"
    write_json(base / "app.json", {"id": "app", "root_elements": []})
    write_json(base / "schema.json", {"pages": []})
    write_json(base / "links.json", {"links": []})
    _write_schema(working, include_page_link=False)

    decisions = [
        PipelineDecision(
            requirement_id="R-1",
            ui_effect="navigation",
            classification="direct_ui",
            targets=[
                PipelineTarget(
                    target_type="page",
                    target_id="cards.list",
                    action="create",
                    implementation_status="implemented",
                )
            ],
            reason="Нужна отдельная страница.",
        )
    ]
    before = read_json(working / "app.json", {})
    warnings, count = collect_structural_warnings(
        runtime=_Runtime(run_path),
        decisions=decisions,
        maximum_candidates=24,
    )

    assert count >= 1
    assert any("cards.list" in item for item in warnings)
    assert read_json(working / "app.json", {}) == before
    result = read_json(run_path / "result/structural_review.json", {})
    assert result["status"] == "warnings_only"
    assert result["candidate_count"] == count
