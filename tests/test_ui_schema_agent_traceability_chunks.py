from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import types
if "backend.app.state" not in sys.modules:
    app_package = types.ModuleType("backend.app")
    app_package.__path__ = []
    state_module = types.ModuleType("backend.app.state")
    state_module.AppState = type("AppState", (), {})
    sys.modules["backend.app"] = app_package
    sys.modules["backend.app.state"] = state_module

from backend.modules.ui_schema.agent_traceability import write_traceability_chunk
from backend.modules.ui_schema.files import read_json, write_json


def test_traceability_chunks_initialize_merge_and_replace_touched_requirements(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    working_root = run_path / "working/ui_schema"
    result_root = run_path / "result"
    write_json(
        run_path / "input/requirements.json",
        {"requirements": [{"id": "REQ-A"}, {"id": "REQ-B"}, {"id": "REQ-C"}]},
    )
    write_json(
        working_root / "mappings/requirement_ui_links.json",
        {
            "links": [
                _link("old-a", "REQ-A", "old.target"),
                _link("legacy", "REQ-OLD", "legacy.target"),
            ]
        },
    )

    first = write_traceability_chunk(
        run_path=run_path,
        working_root=working_root,
        result_root=result_root,
        requirement_ui_links={"links": [_link(None, "REQ-A", "page.a")]},
        agent_report={"no_ui": [{"requirement_id": "REQ-B", "reason": "Нет UI-влияния"}]},
    )
    second = write_traceability_chunk(
        run_path=run_path,
        working_root=working_root,
        result_root=result_root,
        requirement_ui_links={"links": []},
        agent_report={"unclear": [{"requirement_id": "REQ-C", "reason": "Не указан результат"}]},
    )

    links = read_json(working_root / "mappings/requirement_ui_links.json", {})["links"]
    report = read_json(result_root / "agent_report.json", {})
    assert first["started_new_traceability"] is True
    assert second["chunk_index"] == 2
    assert links[0]["id"].startswith("requirement_link_")
    assert links[0]["implementation_status"] == "implemented"
    assert [item["requirement_id"] for item in report["no_ui"]] == ["REQ-B"]
    assert [item["requirement_id"] for item in report["unclear"]] == ["REQ-C"]

    correction = write_traceability_chunk(
        run_path=run_path,
        working_root=working_root,
        result_root=result_root,
        requirement_ui_links={"links": [_link("new-b", "REQ-B", "page.b")]},
        agent_report={},
    )
    links = read_json(working_root / "mappings/requirement_ui_links.json", {})["links"]
    report = read_json(result_root / "agent_report.json", {})
    assert correction["chunk_index"] == 3
    assert {item["requirement_id"] for item in links} == {"REQ-A", "REQ-B"}
    assert report["no_ui"] == []
    assert [item["requirement_id"] for item in report["unclear"]] == ["REQ-C"]


def _link(
    link_id: str | None,
    requirement_id: str,
    target_id: str,
) -> dict[str, str]:
    result = {
        "requirement_id": requirement_id,
        "target_type": "page",
        "target_id": target_id,
        "relation": "implemented_by",
        "implementation_status": "implemented",
    }
    if link_id:
        result["id"] = link_id
    return result
