from __future__ import annotations

from pathlib import Path

from backend.modules.ui_schema.agent_traceability_correction import (
    build_traceability_correction_context,
)
from backend.modules.ui_schema.files import write_json


def test_traceability_correction_context_reports_same_id_page_alternative(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    write_json(
        run_path / "input/requirements.json",
        {
            "requirements": [
                {
                    "id": "R-1",
                    "name": "Список",
                    "description": "Показать список",
                    "acceptanceCriteria": ["Список виден пользователю"],
                }
            ]
        },
    )
    write_json(run_path / "working/ui_schema/app.json", {"id": "app", "root_elements": []})
    write_json(
        run_path / "working/ui_schema/schema.json",
        {"pages": [{"id": "page.one", "file": "pages/page.one.json"}]},
    )
    write_json(
        run_path / "working/ui_schema/pages/page.one.json",
        {"id": "page.one", "title": "Страница", "elements": []},
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
                            "target_id": "page.one",
                            "implementation_status": "implemented",
                        }
                    ],
                    "reason": "Показывается на странице",
                }
            ]
        },
    )
    validation = {
        "repair_hints": [
            {
                "kind": "missing_requirement_link_target",
                "requirement_id": "R-1",
            }
        ]
    }

    context = build_traceability_correction_context(
        run_path,
        agent_config={"context": {"requirement_fields": ["id", "name", "description", "acceptanceCriteria"]}},
        validation=validation,
    )

    check = context["items"][0]["current_target_checks"][0]
    assert check["target_summary"]["exists"] is False
    assert check["same_id_alternatives"][0]["target_type"] == "page"
    assert context["requirement_ids"] == ["R-1"]
