from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_review_correction_context import (
    build_review_relevant_context,
)
from backend.modules.data_schema.files import write_json


def build_semantic_verification_context(
    run_path: Path,
    source_review: dict[str, Any],
    *,
    verification_number: int,
) -> dict[str, Any]:
    issues = [
        item
        for item in source_review.get("issues", [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    expected_issue_ids = [str(item["id"]).strip() for item in issues]
    context = {
        "review_scope": "correction_verification",
        "verification_number": verification_number,
        "source_review": {
            "review_id": str(source_review.get("review_id") or ""),
            "summary": str(source_review.get("summary") or ""),
            "issues": issues,
        },
        "expected_issue_ids": expected_issue_ids,
        "current_relevant_state": build_review_relevant_context(
            run_path,
            source_review,
        ),
    }
    write_json(
        run_path / "input" / f"semantic_verification_context_{verification_number}.json",
        context,
    )
    return context
