from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

import yaml

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

from backend.modules.ui_schema.agent_diagnostics import build_diagnostics_archive
from backend.modules.ui_schema.agent_runs import create_run, run_root
from backend.modules.ui_schema.agent_tool_trace import append_tool_trace
from backend.modules.ui_schema.agent_validation_history import record_validation_attempt
from backend.modules.ui_schema.files import read_json, write_json
from backend.modules.ui_schema.requirements_source import file_sha256

AGENT_CONFIG = yaml.safe_load(
    (PROJECT_ROOT / "modules/ui_schema/config.yaml").read_text(encoding="utf-8")
)["agent"]


def test_validation_history_keeps_errors_codes_and_repair_hints(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    write_json(
        run_path / "run.json",
        {"config": {"diagnostics": AGENT_CONFIG["diagnostics"]}},
    )

    record_validation_attempt(
        run_path,
        {
            "valid": False,
            "errors": [
                "Page file does not exist: pages/missing.json",
                "Связь с требованием link-1 ведёт на отсутствующую цель: ui_element:missing",
            ],
            "warnings": ["warning"],
            "repair_hints": [{"target_id": "missing", "suggested_tool": "write_ui_schema_element"}],
            "assessment_counts": {"unclassified": 1},
        },
        source="agent_tool",
    )
    record_validation_attempt(
        run_path,
        {"valid": True, "errors": [], "warnings": [], "repair_hints": []},
        source="backend_post_run",
    )

    history = read_json(run_path / "result/validation_history.json", {})
    assert history["total_recorded"] == 2
    assert history["attempts"][0]["error_codes"] == ["missing_file", "missing_target"]
    assert history["attempts"][0]["repair_hints"][0]["target_id"] == "missing"
    assert history["attempts"][1]["valid"] is True


def test_tool_trace_is_compact_and_bounded(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    settings = dict(AGENT_CONFIG["diagnostics"])
    settings["tool_trace"] = {**settings["tool_trace"], "max_entries": 2}
    write_json(run_path / "run.json", {"config": {"diagnostics": settings}})

    for number in range(3):
        append_tool_trace(
            run_path,
            {
                "tool_call": number + 1,
                "tool": "write_ui_schema_page_elements",
                "duration_ms": 10 + number,
                "status": "ok",
                "arguments": {"page_id": "page", "top_level_elements": number + 1},
                "result": {"ok": True},
            },
        )

    records = [
        json.loads(line)
        for line in (run_path / "result/tool_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [item["tool_call"] for item in records] == [1, 3]
    assert "content" not in records[-1]["arguments"]


def test_diagnostics_archive_contains_source_fingerprints_history_and_trace(tmp_path: Path) -> None:
    module_root, run_id = _create_run(tmp_path)
    root = run_root(module_root, run_id)
    record_validation_attempt(
        root,
        {"valid": False, "errors": ["Duplicate UI object id: duplicate"], "warnings": []},
        source="agent_tool",
    )
    append_tool_trace(
        root,
        {
            "tool_call": 1,
            "tool": "validate_ui_schema_state",
            "duration_ms": 25,
            "status": "ok",
            "arguments": {},
            "result": {"valid": False, "error_count": 1},
        },
    )

    archive_path = build_diagnostics_archive(module_root, run_id)
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("diagnostics_manifest.json"))
        fingerprints = json.loads(archive.read("reference/source_fingerprints.json"))

    assert manifest["format_version"] == "0.2"
    assert "result/validation_history.json" in names
    assert "result/tool_trace.jsonl" in names
    assert fingerprints["files"]
    assert all(item["matches_snapshot"] for item in fingerprints["files"])
    prompt_paths = {
        item["prompt_snapshot_path"] for item in fingerprints["prompt_mappings"]
    }
    assert prompt_paths == {
        "reference/prompts/pipeline_analysis.md",
        "reference/prompts/pipeline_planning.md",
        "reference/prompts/pipeline_repair.md",
        "reference/prompts/pipeline_audit.md",
        "reference/prompts/pipeline_correction.md",
        "reference/prompts/pipeline_structural_review.md",
        "reference/prompts/pipeline_output_contract.md",
        "reference/prompts/pipeline_change_rules.md",
        "reference/prompts/connection_test.md",
    }
    assert manifest["agent_runtime"]["type"] == "managed_pipeline_v2"


def _create_run(tmp_path: Path) -> tuple[Path, str]:
    workspace = tmp_path / "workspace"
    module_root = workspace / "ui_schema"
    shutil.copytree(PROJECT_ROOT / "modules/ui_schema/init", module_root)
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
    return module_root, run["run_id"]
