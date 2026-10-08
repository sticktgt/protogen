from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_events import append_event
from backend.modules.data_schema.agent_paths import now_iso
from backend.modules.data_schema.agent_runs import update_run
from backend.modules.data_schema.files import write_json


def correction_application_failure_review(
    *,
    source_review: dict[str, Any],
    validation: dict[str, Any],
    correction_round: int,
) -> dict[str, Any]:
    error = str(validation.get("correction_error") or "").strip()
    message = "План автоматических исправлений не прошёл техническую проверку."
    if error:
        message += f" Причина: {error}"
    review_id = f"correction_application_{correction_round}"
    return {
        "status": "needs_revision",
        "decision": "revise",
        "blocking": True,
        "review_id": review_id,
        "review_kind": "correction_application",
        "coverage_complete": True,
        "verified_issue_ids": [],
        "reviewed_at": now_iso(),
        "summary": message,
        "review_note": "",
        "strengths": [],
        "issue_counts": {"must_fix": 1, "advisory": 0},
        "issues": [
            {
                "id": f"{review_id}_issue_1",
                "source_review_id": review_id,
                "disposition": "must_fix",
                "category": "technical_correction_plan",
                "message": message,
                "recommendation": (
                    "Повторно сформировать самодостаточный план с явными точными ID "
                    "и согласованными ссылками внутри плана."
                ),
                "requirement_ids": [],
                "targets": [],
            }
        ],
        "source_reviews": source_review.get("source_reviews", []),
        "correction_pending": False,
    }


def record_review_event(
    *,
    module_root: Path,
    run_id: str,
    review: dict[str, Any],
    completed_message: str,
) -> None:
    append_event(
        module_root,
        run_id,
        event_type="semantic_review_completed",
        level="warning" if review.get("blocking") else "info",
        message=(
            f"{completed_message}: найдены обязательные замечания"
            if review.get("blocking")
            else f"{completed_message}: обязательных замечаний нет"
        ),
        data={
            "review_id": review.get("review_id"),
            "review_kind": review.get("review_kind"),
            "issue_counts": review.get("issue_counts", {}),
            "coverage_complete": review.get("coverage_complete"),
        },
    )


def record_review_completion(
    *,
    root: Path,
    module_root: Path,
    run_id: str,
    review: dict[str, Any],
    completed_message: str,
) -> None:
    record_review_event(
        module_root=module_root,
        run_id=run_id,
        review=review,
        completed_message=completed_message,
    )
    write_json(root / "result" / "semantic_review.json", review)
    update_run(
        module_root,
        run_id,
        semantic_review=review,
        apply_blocked=bool(review.get("blocking") or review.get("correction_pending")),
    )
