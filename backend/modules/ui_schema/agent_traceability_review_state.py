from __future__ import annotations

from pathlib import Path

from backend.modules.ui_schema.files import read_json, write_json

_STATE_FILE = "traceability_state.json"


def mark_traceability_review_complete(
    run_path: Path,
    *,
    candidate_count: int,
) -> None:
    path = run_path / "result" / _STATE_FILE
    state = read_json(path, {})
    write_json(
        path,
        {
            **state,
            "review_complete": True,
            "review_candidate_count": max(0, int(candidate_count)),
        },
    )


def traceability_review_errors(run_path: Path) -> list[str]:
    state = read_json(run_path / "result" / _STATE_FILE, {})
    if not bool(state.get("initial_batches_complete")):
        return []
    if not bool(state.get("review_complete")):
        return [
            "Traceability quality review is not completed: review the formal candidates returned after the last traceability batch"
        ]
    return []
