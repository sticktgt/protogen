from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_events import append_event
from backend.modules.data_schema.agent_prompts import load_prompt
from backend.modules.data_schema.agent_runs import is_cancelled, update_run
from backend.modules.data_schema.agent_semantic_correction import apply_semantic_correction
from backend.modules.data_schema.agent_semantic_invocation import invoke_semantic_review
from backend.modules.data_schema.agent_semantic_prompts import (
    non_negative_int,
    render_semantic_verification_prompt,
    semantic_review_settings,
)
from backend.modules.data_schema.agent_semantic_review_state import (
    correction_application_failure_review,
    record_review_completion,
)
from backend.modules.data_schema.agent_semantic_verification_context import (
    build_semantic_verification_context,
)
from backend.modules.data_schema.files import write_json


def run_semantic_correction_rounds(
    *,
    root: Path,
    module_root: Path,
    run_id: str,
    validation: dict[str, Any],
    source_review: dict[str, Any],
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply one broad correction and bounded targeted recovery rounds.

    The backend routes only LLM-declared issues. It does not infer semantic fixes:
    the first round receives the combined review, while later rounds receive only
    the remaining issues whose disposition is still ``must_fix``.
    """
    maximum_rounds = non_negative_int(
        semantic_review_settings(agent_config),
        "max_correction_rounds",
    )
    if maximum_rounds == 0:
        return validation, source_review

    correction_source = source_review
    final_review = source_review
    for correction_round in range(1, maximum_rounds + 1):
        pending_review = {**correction_source, "correction_pending": True}
        write_json(root / "result" / "semantic_review.json", pending_review)
        update_run(
            module_root,
            run_id,
            semantic_review=pending_review,
            apply_blocked=True,
        )

        validation = apply_semantic_correction(
            root=root,
            module_root=module_root,
            run_id=run_id,
            review=correction_source,
            llm_settings=llm_settings,
            agent_config=agent_config,
            correction_round=correction_round,
        )
        if not validation.get("valid") or is_cancelled(module_root, run_id):
            return validation, pending_review
        if validation.get("correction_applied") is not True:
            failed_review = correction_application_failure_review(
                source_review=correction_source,
                validation=validation,
                correction_round=correction_round,
            )
            record_review_completion(
                root=root,
                module_root=module_root,
                run_id=run_id,
                review=failed_review,
                completed_message="Применение автоматических исправлений",
            )
            return validation, failed_review

        final_review = _run_correction_verification(
            root=root,
            module_root=module_root,
            run_id=run_id,
            llm_settings=llm_settings,
            agent_config=agent_config,
            source_review=correction_source,
            verification_number=correction_round,
        )
        if is_cancelled(module_root, run_id) or not final_review.get("blocking"):
            return validation, final_review
        if correction_round >= maximum_rounds:
            return validation, final_review

        correction_source = _remaining_blockers_review(
            final_review,
            recovery_round=correction_round + 1,
        )
        if not correction_source.get("issues"):
            return validation, final_review
        append_event(
            module_root,
            run_id,
            event_type="semantic_recovery_scheduled",
            level="warning",
            message="Запланирован точечный раунд исправления оставшихся blockers",
            data={
                "correction_round": correction_round + 1,
                "remaining_issue_count": len(correction_source["issues"]),
            },
        )

    return validation, final_review


def _run_correction_verification(
    *,
    root: Path,
    module_root: Path,
    run_id: str,
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
    source_review: dict[str, Any],
    verification_number: int,
) -> dict[str, Any]:
    review_id = f"verification_{verification_number}"
    expected_issue_ids = [
        str(item.get("id") or "").strip()
        for item in source_review.get("issues", [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    update_run(module_root, run_id, phase="semantic_verification")
    append_event(
        module_root,
        run_id,
        event_type="semantic_verification_start",
        message="Запущена целевая проверка автоматических исправлений",
        data={
            "review_id": review_id,
            "review_kind": "correction_verification",
            "source_review_id": source_review.get("review_id"),
            "expected_issue_count": len(expected_issue_ids),
            "verification_number": verification_number,
        },
    )
    context = build_semantic_verification_context(
        root,
        source_review,
        verification_number=verification_number,
    )
    prompt = render_semantic_verification_prompt(
        agent_config,
        context,
        verification_number=verification_number,
    )
    (root / "input" / f"semantic_review_prompt_{review_id}.md").write_text(
        prompt,
        encoding="utf-8",
    )
    review = invoke_semantic_review(
        module_root=module_root,
        run_id=run_id,
        run_path=root,
        llm_settings=llm_settings,
        agent_config=agent_config,
        system_prompt=load_prompt(agent_config, "semantic_review_system"),
        review_prompt=prompt,
        review_id=review_id,
        review_kind="correction_verification",
        expected_issue_ids=expected_issue_ids,
    )
    review["correction_pending"] = False
    review["source_reviews"] = source_review.get("source_reviews", [])
    record_review_completion(
        root=root,
        module_root=module_root,
        run_id=run_id,
        review=review,
        completed_message="Проверка автоматических исправлений",
    )
    return review


def _remaining_blockers_review(
    review: dict[str, Any],
    *,
    recovery_round: int,
) -> dict[str, Any]:
    issues = [
        dict(issue)
        for issue in review.get("issues", [])
        if isinstance(issue, dict) and issue.get("disposition") == "must_fix"
    ]
    return {
        "status": "needs_revision" if issues else "approved",
        "decision": "revise" if issues else "approve",
        "blocking": bool(issues),
        "review_id": f"recovery_{recovery_round}_source",
        "review_kind": "correction_recovery",
        "coverage_complete": True,
        "verified_issue_ids": [],
        "summary": (
            "Точечно исправить только blockers, оставшиеся после предыдущей verification."
        ),
        "review_note": "",
        "strengths": [],
        "issue_counts": {"must_fix": len(issues), "advisory": 0},
        "issues": issues,
        "source_reviews": review.get("source_reviews", []),
        "correction_pending": False,
    }
