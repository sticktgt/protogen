from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.modules.ui_schema.agent_coverage_plan_targets import (
    build_coverage_plan_target_report,
)
from backend.modules.ui_schema.files import write_json


def _run(tmp_path: Path, target_type: str) -> Path:
    run_path = tmp_path / "run"
    write_json(
        run_path / "input/requirements.json",
        {"requirements": [{"id": "R-1", "description": "Observable result"}]},
    )
    root = run_path / "working/ui_schema"
    write_json(
        root / "schema.json",
        {
            "schema_version": "0.1",
            "application": {"name": "Sample"},
            "pages": [{"id": "page.one", "title": "Page", "file": "pages/page.one.json"}],
        },
    )
    write_json(root / "app.json", {"id": "app", "root_elements": []})
    write_json(
        root / "pages/page.one.json",
        {
            "id": "page.one",
            "title": "Page",
            "elements": [{"id": "page.one.main", "type": "section", "label": "Main"}],
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
                            "target_type": target_type,
                            "target_id": "page.one",
                            "action": "extend",
                        }
                    ],
                    "note": "Represent the observable result.",
                }
            ]
        },
    )
    return run_path


def test_existing_target_type_mismatch_is_reported_before_schema_changes(tmp_path: Path) -> None:
    report = build_coverage_plan_target_report(_run(tmp_path, "ui_element"))

    assert report["complete"] is False
    assert report["gaps"][0]["signal"] == "existing_target_type_mismatch"
    assert report["gaps"][0]["available_targets_with_same_id"][0]["target_type"] == "page"


def test_exact_existing_page_target_is_valid_for_extend(tmp_path: Path) -> None:
    report = build_coverage_plan_target_report(_run(tmp_path, "page"))

    assert report["complete"] is True
    assert report["gaps"] == []
