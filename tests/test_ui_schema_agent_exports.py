from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.modules.ui_schema.agent_exports import build_requirements_ui_result
from backend.modules.ui_schema.files import write_json


def test_single_target_prototype_traceability_is_not_reported_as_a_warning(
    tmp_path: Path,
) -> None:
    requirements = [
        {"id": f"REQ-{number:04d}", "name": f"Requirement {number}"}
        for number in range(1, 11)
    ]
    requirements_file = tmp_path / "requirements.json"
    schema_root = tmp_path / "ui_schema"
    report_file = tmp_path / "agent_report.json"

    write_json(requirements_file, {"requirements": requirements})
    write_json(schema_root / "app.json", {"id": "app", "root_elements": []})
    write_json(
        schema_root / "schema.json",
        {
            "schema_version": "0.1",
            "pages": [{"id": "home", "file": "pages/home.json", "title": "Home"}],
        },
    )
    write_json(
        schema_root / "pages/home.json",
        {
            "id": "home",
            "title": "Home",
            "elements": [
                {
                    "id": "home.panel",
                    "type": "section",
                    "label": "Panel",
                    "children": [],
                }
            ],
        },
    )
    write_json(
        schema_root / "mappings/requirement_ui_links.json",
        {
            "links": [
                {
                    "id": f"link-{number}",
                    "requirement_id": requirement["id"],
                    "target_type": "ui_element",
                    "target_id": "home.panel",
                    "relation": "implemented_by",
                }
                for number, requirement in enumerate(requirements, start=1)
            ]
        },
    )
    write_json(
        report_file,
        {"cross_cutting_ui": [], "no_ui": [], "unclear": [], "warnings": []},
    )

    result = build_requirements_ui_result(
        requirements_file=requirements_file,
        ui_schema_root=schema_root,
        agent_report_file=report_file,
        run={"run_id": "run-test", "workspace_id": "workspace-test"},
    )

    assert result["traceability"]["requirements_multi_target"] == 0
    assert result["traceability"]["average_targets_per_traced_requirement"] == 1.0
    assert result["traceability_warnings"] == []
