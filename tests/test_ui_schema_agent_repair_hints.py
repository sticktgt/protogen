from __future__ import annotations

from pathlib import Path

from backend.modules.ui_schema.agent_repair_hints import build_repair_hints
from backend.modules.ui_schema.files import write_json


def test_missing_group_target_hint_requests_contentful_batch(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    working = run_path / "working" / "ui_schema"
    write_json(run_path / "input" / "requirements.json", {"requirements": [{"id": "REQ-1"}]})
    write_json(working / "app.json", {"id": "app", "root_elements": []})
    write_json(
        working / "schema.json",
        {"pages": [{"id": "overview", "title": "Обзор", "file": "pages/overview.json"}]},
    )
    write_json(
        working / "pages" / "overview.json",
        {
            "id": "overview",
            "title": "Обзор",
            "description": "",
            "elements": [
                {
                    "id": "overview.content",
                    "type": "section",
                    "label": "Содержимое",
                    "children": [],
                }
            ],
        },
    )
    write_json(
        working / "mappings" / "requirement_ui_links.json",
        {
            "links": [
                {
                    "id": "link-1",
                    "requirement_id": "REQ-1",
                    "target_type": "ui_element",
                    "target_id": "overview.content.result",
                    "relation": "implemented_by",
                    "implementation_status": "implemented",
                }
            ]
        },
    )

    hints = build_repair_hints(run_path)

    assert len(hints) == 1
    assert hints[0]["suggested_tool"] == "apply_ui_schema_changes"
    assert "минимальными обязательными дочерними элементами" in hints[0]["instruction"]
    assert "Не создавай пустой контейнер" in hints[0]["instruction"]
