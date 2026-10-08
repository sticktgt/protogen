from __future__ import annotations

import shutil
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# The uploaded module bundle intentionally omits the application shell.
# Production provides backend.app.state; the tests need only the type placeholder.
import types
if "backend.app.state" not in sys.modules:
    app_package = types.ModuleType("backend.app")
    app_package.__path__ = []
    state_module = types.ModuleType("backend.app.state")
    state_module.AppState = type("AppState", (), {})
    sys.modules["backend.app"] = app_package
    sys.modules["backend.app.state"] = state_module

from backend.modules.ui_schema.agent_paths import (
    active_run_path,
    completed_run_file,
    run_root,
)
from backend.modules.ui_schema.agent_preview import finalize_preview
from backend.modules.ui_schema.agent_runs import (
    apply_run,
    create_run,
    get_active_run,
    get_run,
    reject_run,
)
from backend.modules.ui_schema.files import read_json, write_json
from backend.modules.ui_schema.requirements_source import file_sha256

AGENT_CONFIG = yaml.safe_load(
    (PROJECT_ROOT / "modules/ui_schema/config.yaml").read_text(encoding="utf-8")
)["agent"]


def test_preview_writes_file_diff_manual_review_and_clears_stale_errors(tmp_path: Path) -> None:
    module_root, run_id = _create_run(tmp_path)
    root = run_root(module_root, run_id)
    write_json(
        root / "run.json",
        {
            **read_json(root / "run.json", {}),
            "validation_errors": ["old"],
            "validation_error_count": 9,
            "validation_warnings": ["old"],
            "error": "old",
            "stop_reason": "old",
        },
    )
    working_app = root / "working" / "ui_schema" / "app.json"
    app = read_json(working_app, {})
    app["title"] = "Updated"
    write_json(working_app, app)

    finalize_preview(
        module_root,
        run_id,
        {"valid": True, "errors": [], "warnings": []},
        cleanup_review={
            "status": "completed",
            "summary": "Проверено",
            "cleanup_candidates": [],
        },
    )

    run = get_run(module_root, run_id)
    assert run["status"] == "preview_ready"
    assert run["validation_errors"] == []
    assert run["validation_error_count"] == 0
    assert run["validation_warnings"] == []
    assert run["error"] == ""
    assert run["stop_reason"] == ""
    assert (root / "result" / "changes.json").is_file()
    assert (root / "result" / "file_diff.json").is_file()
    assert (root / "result" / "manual_review.json").is_file()
    assert read_json(root / "result" / "file_diff.json", {})["summary"]["modified"] >= 1


def test_reject_archives_diagnostics_clears_active_run_and_removes_heavy_run(tmp_path: Path) -> None:
    module_root, run_id = _create_run(tmp_path)
    finalize_preview(
        module_root,
        run_id,
        {"valid": True, "errors": [], "warnings": []},
    )

    result = reject_run(module_root, run_id)

    assert result["status"] == "rejected"
    assert result["archived"] is True
    assert get_active_run(module_root) is None
    assert not active_run_path(module_root).exists()
    assert not run_root(module_root, run_id).exists()
    assert completed_run_file(module_root, run_id).is_file()
    assert get_run(module_root, run_id)["status"] == "rejected"


def test_apply_replaces_schema_archives_run_and_keeps_requirements_reference(tmp_path: Path) -> None:
    module_root, run_id = _create_run(tmp_path)
    root = run_root(module_root, run_id)
    working_app = root / "working" / "ui_schema" / "app.json"
    app = read_json(working_app, {})
    app["title"] = "Applied title"
    write_json(working_app, app)
    finalize_preview(
        module_root,
        run_id,
        {"valid": True, "errors": [], "warnings": []},
    )

    result = apply_run(module_root, run_id, keep_last=3)

    assert result["status"] == "completed"
    assert read_json(module_root / "app.json", {})["title"] == "Applied title"
    source = read_json(module_root / "requirements_source.json", {})
    assert source["path"] == "requirements/requirements.json"
    assert not (module_root / "requirements.json").exists()
    assert get_active_run(module_root) is None
    assert not run_root(module_root, run_id).exists()
    assert completed_run_file(module_root, run_id).is_file()


def _create_run(tmp_path: Path) -> tuple[Path, str]:
    workspace = tmp_path / "workspace"
    module_root = workspace / "ui_schema"
    shutil.copytree(PROJECT_ROOT / "modules/ui_schema/init", module_root)
    (module_root / "requirements.json").unlink(missing_ok=True)
    source = workspace / "requirements" / "requirements.json"
    source.parent.mkdir(parents=True)
    write_json(source, {"requirements": []})
    run = create_run(
        module_root=module_root,
        workspace_id="workspace-test",
        requirements_data={"requirements": []},
        requirements_file_name=source.name,
        requirements_source_path="requirements/requirements.json",
        requirements_source_sha256=file_sha256(source),
        user_request="",
        base_mode="current",
        llm_public={"provider": "test", "model": "test"},
        config=AGENT_CONFIG,
    )
    write_json(
        run_root(module_root, run["run_id"]) / "result/pipeline_state.json",
        {"version": 2, "status": "generated", "phase": "generated"},
    )
    return module_root, run["run_id"]
