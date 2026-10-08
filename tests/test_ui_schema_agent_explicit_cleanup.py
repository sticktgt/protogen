import json
from pathlib import Path

from backend.modules.ui_schema.agent_object_cleanup import approved_deletions, remove_schema_objects
from backend.modules.ui_schema.agent_preservation import preservation_validation


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _schema(root: Path) -> None:
    _write(root / "app.json", {"id": "app", "root_elements": []})
    _write(root / "schema.json", {"pages": [{"id": "home", "file": "pages/home.json"}]})
    _write(
        root / "pages/home.json",
        {
            "id": "home",
            "title": "Главная",
            "elements": [{"id": "home.legacy", "type": "text", "label": "Старый блок"}],
        },
    )
    _write(
        root / "links.json",
        {"links": [{"id": "ui-1", "source_id": "home.legacy", "target_id": "home"}]},
    )
    _write(
        root / "mappings/requirement_ui_links.json",
        {"links": [{"id": "req-1", "requirement_id": "REQ-OLD", "target_id": "home.legacy"}]},
    )


def test_explicit_cleanup_allows_only_recorded_base_deletion(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _schema(run / "base/ui_schema")
    _schema(run / "working/ui_schema")

    result = remove_schema_objects(
        run_path=run,
        removals=[
            {
                "target_type": "ui_element",
                "target_id": "home.legacy",
                "reason": "Блок заменён актуальным элементом согласно текущему полному набору требований",
                "requirement_ids": ["REQ-NEW"],
            }
        ],
    )
    assert result["removed_element_ids"] == ["home.legacy"]

    approved_pages, approved_elements = approved_deletions(run)
    validation = preservation_validation(
        run / "base/ui_schema",
        run / "working/ui_schema",
        {"errors": []},
        approved_page_ids=approved_pages,
        approved_element_ids=approved_elements,
    )
    assert validation["valid"] is True

    links = json.loads((run / "working/ui_schema/links.json").read_text())
    requirement_links = json.loads(
        (run / "working/ui_schema/mappings/requirement_ui_links.json").read_text()
    )
    assert links["links"] == []
    assert requirement_links["links"] == []
