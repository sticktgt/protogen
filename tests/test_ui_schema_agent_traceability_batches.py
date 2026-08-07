from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

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

from backend.modules.ui_schema.agent_traceability_batches import write_traceability_batch
from backend.modules.ui_schema.agent_traceability_review import review_traceability
from backend.modules.ui_schema.files import read_json, write_json


def _run(tmp_path: Path) -> tuple[Path, dict]:
    run_path = tmp_path / "run"
    config = {
        "requirement_analysis": {
            "batch_size": 1,
            "review_batch_size": 1,
            "traceability_review": {
                "include_classifications": ["no_ui"],
                "include_page_targets": True,
                "include_implemented_empty_groups": True,
                "include_plan_changes": True,
                "include_execution_observations": True,
                "shared_target_min_requirements": 0,
            },
        }
    }
    write_json(
        run_path / "input/requirements.json",
        {
            "requirements": [
                {"id": "R-1", "description": "Visible page"},
                {"id": "R-2", "description": "Internal operation"},
            ]
        },
    )
    write_json(run_path / "working/ui_schema/app.json", {"id": "app", "root_elements": []})
    write_json(
        run_path / "working/ui_schema/schema.json",
        {"schema_version": "0.1", "application": {}, "pages": [{"id": "page.one", "title": "One"}]},
    )
    write_json(
        run_path / "working/ui_schema/pages/page.one.json",
        {"id": "page.one", "title": "One", "elements": []},
    )
    write_json(run_path / "working/ui_schema/links.json", {"links": []})
    write_json(
        run_path / "working/ui_schema/mappings/requirement_ui_links.json",
        {"links": []},
    )
    write_json(
        run_path / "result/coverage_plan.json",
        {
            "items": [
                {
                    "requirement_id": "R-1",
                    "ui_effect": "display",
                    "classification": "direct_ui",
                    "targets": [{"target_type": "page", "target_id": "page.one", "action": "reuse"}],
                    "note": "The existing page is the intended visible target.",
                },
                {
                    "requirement_id": "R-2",
                    "ui_effect": "none",
                    "classification": "no_ui",
                    "targets": [],
                    "note": "No observable interface outcome is required.",
                },
            ]
        },
    )
    write_json(
        run_path / "result/coverage_plan_state.json",
        {
            "completed_batch_ids": ["requirements_01", "requirements_02"],
            "batches_complete": True,
            "review_complete": True,
        },
    )
    write_json(run_path / "result/coverage_plan_execution.json", {"complete": True})
    return run_path, config


def _direct_item() -> dict:
    return {
        "requirement_id": "R-1",
        "ui_effect": "display",
        "classification": "direct_ui",
        "targets": [
            {
                "target_type": "page",
                "target_id": "page.one",
                "implementation_status": "in_progress",
            }
        ],
        "reason": "The page is relevant but the required details are incomplete.",
    }


def _no_ui_item() -> dict:
    return {
        "requirement_id": "R-2",
        "ui_effect": "none",
        "classification": "no_ui",
        "targets": [],
        "reason": "No observable result is required.",
    }


def test_traceability_is_written_in_batches_then_returns_targeted_review(tmp_path: Path) -> None:
    run_path, config = _run(tmp_path)

    first = write_traceability_batch(
        run_path=run_path,
        working_root=run_path / "working/ui_schema",
        result_root=run_path / "result",
        agent_config=config,
        items=[_direct_item()],
        agent_note="",
        warnings=[],
        validate_after_write=True,
    )
    assert first["next_batch_id"] == "requirements_02"
    assert first["next_requirement_batch_context"]["requirement_ids"] == ["R-2"]

    second = write_traceability_batch(
        run_path=run_path,
        working_root=run_path / "working/ui_schema",
        result_root=run_path / "result",
        agent_config=config,
        items=[_no_ui_item()],
        agent_note="",
        warnings=[],
        validate_after_write=True,
    )

    assert second["batches_complete"] is True
    assert second["next_action"] == "review_traceability_candidates"
    assert second["quality_review_context"]["batch_candidate_count"] == 1
    assert second["quality_review_context"]["total_candidate_count"] == 2
    candidate = second["quality_review_context"]["candidates"][0]
    assert "final_traceability" not in candidate
    assert "coverage_plan" not in candidate
    assert candidate["target_facts"][0]["target_id"] == "page.one"
    assert candidate["target_facts"][0]["exists"] is True


def test_traceability_batch_preserves_partial_classification_and_returns_remaining(tmp_path: Path) -> None:
    run_path, _config = _run(tmp_path)

    result = write_traceability_batch(
        run_path=run_path,
        working_root=run_path / "working/ui_schema",
        result_root=run_path / "result",
        agent_config={"requirement_analysis": {"batch_size": 2}},
        items=[_no_ui_item()],
        agent_note="",
        warnings=[],
        validate_after_write=True,
    )

    assert result["accepted_in_call"] == 1
    assert result["remaining_in_batch"] == 1
    assert result["current_requirement_batch_context"]["requirement_ids"] == ["R-1"]
    assert result["next_action"] == "write_remaining_traceability_items"


def test_traceability_review_returns_fresh_items_and_validates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_path, config = _run(tmp_path)
    write_traceability_batch(
        run_path=run_path,
        working_root=run_path / "working/ui_schema",
        result_root=run_path / "result",
        agent_config=config,
        items=[_direct_item()],
        agent_note="",
        warnings=[],
        validate_after_write=True,
    )
    write_traceability_batch(
        run_path=run_path,
        working_root=run_path / "working/ui_schema",
        result_root=run_path / "result",
        agent_config=config,
        items=[_no_ui_item()],
        agent_note="",
        warnings=[],
        validate_after_write=True,
    )

    from backend.modules.ui_schema import agent_traceability_review as target

    monkeypatch.setattr(
        target,
        "validate_and_mark_completion",
        lambda *_args, **_kwargs: {"valid": True, "errors": [], "warnings": []},
    )
    first_review = review_traceability(
        run_path,
        working_root=run_path / "working/ui_schema",
        result_root=run_path / "result",
        agent_config=config,
        items=[_direct_item()],
        agent_note="Reviewed independently.",
    )
    assert first_review["review_complete"] is False
    assert first_review["completed"] is False

    result = review_traceability(
        run_path,
        working_root=run_path / "working/ui_schema",
        result_root=run_path / "result",
        agent_config=config,
        items=[_no_ui_item()],
        agent_note="Reviewed independently.",
    )

    assert result["accepted_in_call"] == 1
    assert result["changed_requirements"] == 0
    assert result["completed"] is True
    assert read_json(run_path / "result/traceability_state.json", {})["review_complete"] is True


def test_traceability_review_accepts_multiple_fresh_items_in_one_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_path, config = _run(tmp_path)
    config["requirement_analysis"]["review_batch_size"] = 2
    write_traceability_batch(
        run_path=run_path,
        working_root=run_path / "working/ui_schema",
        result_root=run_path / "result",
        agent_config=config,
        items=[_direct_item()],
        agent_note="",
        warnings=[],
        validate_after_write=True,
    )
    write_traceability_batch(
        run_path=run_path,
        working_root=run_path / "working/ui_schema",
        result_root=run_path / "result",
        agent_config=config,
        items=[_no_ui_item()],
        agent_note="",
        warnings=[],
        validate_after_write=True,
    )

    from backend.modules.ui_schema import agent_traceability_review as target

    monkeypatch.setattr(
        target,
        "validate_and_mark_completion",
        lambda *_args, **_kwargs: {"valid": True, "errors": [], "warnings": []},
    )
    result = review_traceability(
        run_path,
        working_root=run_path / "working/ui_schema",
        result_root=run_path / "result",
        agent_config=config,
        items=[_direct_item(), _no_ui_item()],
        agent_note="Reviewed independently.",
    )

    assert result["review_complete"] is True
    assert result["completed"] is True
    assert result["accepted_in_call"] == 2


def test_traceability_batch_keeps_valid_items_when_another_item_is_inconsistent(
    tmp_path: Path,
) -> None:
    run_path, _config = _run(tmp_path)
    config = {"requirement_analysis": {"batch_size": 2}}

    result = write_traceability_batch(
        run_path=run_path,
        working_root=run_path / "working/ui_schema",
        result_root=run_path / "result",
        agent_config=config,
        items=[
            _direct_item(),
            {
                "requirement_id": "R-2",
                "ui_effect": "display",
                "classification": "no_ui",
                "targets": [],
                "reason": "Inconsistent fields should be returned for correction.",
            },
        ],
        agent_note="",
        warnings=[],
        validate_after_write=True,
    )

    assert result["accepted_in_call"] == 1
    assert result["remaining_in_batch"] == 1
    assert result["item_errors"] == [
        {"requirement_id": "R-2", "error": "no_ui requires ui_effect=none"}
    ]
    assert result["current_requirement_batch_context"]["requirement_ids"] == ["R-2"]
