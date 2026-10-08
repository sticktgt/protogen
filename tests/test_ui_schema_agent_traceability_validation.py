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

from backend.modules.ui_schema import agent_traceability_validation as target

def test_final_traceability_requires_coverage_plan_and_validates(
    tmp_path: Path, monkeypatch
) -> None:
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        target,
        "require_coverage_plan",
        lambda run_path: calls.setdefault("plan", run_path) or {},
    )
    monkeypatch.setattr(
        target,
        "write_traceability_chunk",
        lambda **kwargs: calls.setdefault("write", kwargs) or {"ok": True},
    )
    def fake_plan_diff(run_path: Path):
        calls["diff"] = run_path
        return {"changed_count": 3}

    monkeypatch.setattr(target, "write_coverage_plan_diff", fake_plan_diff)
    monkeypatch.setattr(
        target,
        "validate_and_mark_completion",
        lambda run_path, *, completed_by: {
            "valid": True,
            "errors": [],
            "warnings": [],
            "completed_by": completed_by,
        },
    )

    result = target.write_traceability_with_optional_validation(
        run_path=tmp_path,
        working_root=tmp_path / "working/ui_schema",
        result_root=tmp_path / "result",
        requirement_ui_links={"links": []},
        agent_report={"no_ui": []},
        validate_after_write=True,
    )

    assert calls["plan"] == tmp_path
    assert calls["diff"] == tmp_path
    assert result["coverage_plan_changes"] == 3
    assert result["valid"] is True
    assert result["completed"] is True
    assert result["next_action"] == "stop"

def test_traceability_can_defer_validation_when_disabled(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(target, "require_coverage_plan", lambda _path: {})
    monkeypatch.setattr(
        target,
        "write_traceability_chunk",
        lambda **_kwargs: {"ok": True, "chunk_index": 1},
    )
    monkeypatch.setattr(
        target,
        "write_coverage_plan_diff",
        lambda _path: {"changed_count": 0},
    )
    monkeypatch.setattr(
        target,
        "validate_and_mark_completion",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("validation must not run")
        ),
    )

    result = target.write_traceability_with_optional_validation(
        run_path=tmp_path,
        working_root=tmp_path / "working/ui_schema",
        result_root=tmp_path / "result",
        requirement_ui_links={"links": []},
        agent_report={"no_ui": []},
        validate_after_write=False,
    )

    assert result["completed"] is False
    assert result["next_action"] == "validate_ui_schema_state"

def test_completion_requires_finished_pipeline_v2(
    tmp_path: Path, monkeypatch
) -> None:
    from backend.modules.ui_schema import agent_completion

    monkeypatch.setattr(
        agent_completion,
        "validate_ui_schema",
        lambda *_args, **_kwargs: {"valid": True, "errors": [], "warnings": []},
    )
    monkeypatch.setattr(
        agent_completion,
        "preservation_validation",
        lambda _base, _working, validation, **_kwargs: validation,
    )
    monkeypatch.setattr(agent_completion, "approved_deletions", lambda _path: (set(), set()))
    monkeypatch.setattr(agent_completion, "build_repair_hints", lambda _path: [])

    result = agent_completion.validate_agent_working_schema(tmp_path)

    assert result["valid"] is False
    assert result["errors"] == [
        "Управляемая синхронизация UI-схемы не завершена; текущий этап: unknown"
    ]

def test_final_validation_does_not_rewrite_invalid_table_children(tmp_path: Path) -> None:
    import shutil

    from backend.modules.ui_schema import agent_completion
    from backend.modules.ui_schema.files import read_json, write_json

    for snapshot in ("base", "working"):
        shutil.copytree(
            PROJECT_ROOT / "modules/ui_schema/init",
            tmp_path / snapshot / "ui_schema",
        )

    page_path = tmp_path / "working/ui_schema/pages/sample.json"
    write_json(
        page_path,
        {
            "id": "sample",
            "title": "Sample",
            "elements": [
                {
                    "id": "sample.table",
                    "type": "table",
                    "label": "Table",
                    "children": [
                        {
                            "id": "sample.table.name",
                            "type": "text",
                            "label": "Name",
                        }
                    ],
                }
            ],
        },
    )
    write_json(
        tmp_path / "working/ui_schema/schema.json",
        {
            "version": "0.1",
            "pages": [
                {
                    "id": "sample",
                    "file": "pages/sample.json",
                    "title": "Sample",
                }
            ],
        },
    )
    write_json(tmp_path / "input/requirements.json", {"requirements": []})
    write_json(
        tmp_path / "result/pipeline_state.json",
        {"version": 2, "status": "generated", "phase": "generated"},
    )

    result = agent_completion.validate_agent_working_schema(tmp_path)

    assert result["valid"] is False
    assert any("нельзя размещать внутри table" in item for item in result["errors"])
    page = read_json(page_path, {})
    assert page["elements"][0]["children"][0]["type"] == "text"
