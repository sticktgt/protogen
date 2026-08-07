from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.modules.ui_schema.agent_workflow_context import build_current_workflow_context
from backend.modules.ui_schema.files import write_json


def test_workflow_context_returns_remaining_coverage_review_candidates(tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    write_json(
        run_path / "input/requirements.json",
        {"requirements": [{"id": "R-1"}, {"id": "R-2"}]},
    )
    write_json(
        run_path / "result/coverage_plan_state.json",
        {
            "completed_batch_ids": ["requirements_01"],
            "batches_complete": True,
            "review_complete": False,
            "review_completed_batch_ids": [],
        },
    )
    pending = {
        "policy": {"original_decision_is_hidden": True},
        "candidates": [
            {"requirement": {"id": "R-1"}},
            {"requirement": {"id": "R-2"}},
        ],
    }
    write_json(run_path / "result/coverage_plan_review_pending.json", pending)
    write_json(
        run_path / "result/coverage_plan_review.json",
        {"reviewed_candidate_ids_by_batch": {"coverage_review_01": ["R-1"]}},
    )

    context = build_current_workflow_context(
        run_path,
        agent_config={
            "requirement_analysis": {"batch_size": 2, "review_batch_size": 2}
        },
    )

    assert context["stage"] == "coverage_plan_review"
    assert context["next_action"] == "review_ui_schema_coverage_plan"
    assert [
        item["requirement"]["id"]
        for item in context["quality_review_context"]["candidates"]
    ] == ["R-2"]
