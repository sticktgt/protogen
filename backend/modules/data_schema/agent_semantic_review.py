from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from backend.modules.data_schema.agent_events import append_event
from backend.modules.data_schema.agent_paths import now_iso
from backend.modules.data_schema.agent_prompts import load_prompt
from backend.modules.data_schema.agent_runs import is_cancelled, update_run
from backend.modules.data_schema.agent_semantic_context import build_semantic_review_context
from backend.modules.data_schema.agent_semantic_correction_workflow import (
    run_semantic_correction_rounds,
)
from backend.modules.data_schema.agent_semantic_invocation import invoke_semantic_review
from backend.modules.data_schema.agent_semantic_prompts import (
    render_semantic_consistency_review_prompt,
    render_semantic_coverage_review_prompt,
    semantic_review_enabled,
)
from backend.modules.data_schema.agent_semantic_review_state import (
    record_review_completion,
    record_review_event,
)

ReviewScope = Literal["coverage", "consistency"]


def review_and_correct_semantics(
    *,
    root: Path,
    module_root: Path,
    run_id: str,
    validation: dict[str, Any],
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run focused reviews, one broad correction and bounded recovery rounds."""
    if not semantic_review_enabled(agent_config):
        review = _skipped_review()
        record_review_completion(
            root=root,
            module_root=module_root,
            run_id=run_id,
            review=review,
            completed_message="Смысловой контроль",
        )
        return validation, review

    coverage_review = _run_focused_review(
        scope="coverage",
        root=root,
        module_root=module_root,
        run_id=run_id,
        llm_settings=llm_settings,
        agent_config=agent_config,
    )
    if is_cancelled(module_root, run_id):
        return validation, coverage_review

    consistency_review = _run_focused_review(
        scope="consistency",
        root=root,
        module_root=module_root,
        run_id=run_id,
        llm_settings=llm_settings,
        agent_config=agent_config,
    )
    combined_review = _combine_reviews(coverage_review, consistency_review)
    record_review_completion(
        root=root,
        module_root=module_root,
        run_id=run_id,
        review=combined_review,
        completed_message="Сводный смысловой контроль",
    )
    if not combined_review.get("issues") or is_cancelled(module_root, run_id):
        return validation, combined_review

    return run_semantic_correction_rounds(
        root=root,
        module_root=module_root,
        run_id=run_id,
        validation=validation,
        source_review=combined_review,
        llm_settings=llm_settings,
        agent_config=agent_config,
    )


def _skipped_review() -> dict[str, Any]:
    return {
        "status": "skipped",
        "decision": "approve",
        "blocking": False,
        "review_id": "skipped",
        "review_kind": "combined",
        "coverage_complete": True,
        "verified_issue_ids": [],
        "summary": "LLM review отключено конфигурацией модуля.",
        "review_note": "",
        "strengths": [],
        "issue_counts": {"must_fix": 0, "advisory": 0},
        "issues": [],
        "source_reviews": [],
        "correction_pending": False,
    }


def _run_focused_review(
    *,
    scope: ReviewScope,
    root: Path,
    module_root: Path,
    run_id: str,
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
) -> dict[str, Any]:
    review_id = f"{scope}_1"
    title = (
        "покрытия требований"
        if scope == "coverage"
        else "внутренней согласованности схемы"
    )
    update_run(module_root, run_id, phase=f"semantic_{scope}_review")
    append_event(
        module_root,
        run_id,
        event_type="semantic_review_start",
        message=f"Запущена независимая проверка {title}",
        data={"review_id": review_id, "review_kind": scope},
    )
    context = build_semantic_review_context(
        root,
        review_scope=scope,
        review_number=1,
    )
    prompt = (
        render_semantic_coverage_review_prompt(
            agent_config,
            context,
            review_number=1,
        )
        if scope == "coverage"
        else render_semantic_consistency_review_prompt(
            agent_config,
            context,
            review_number=1,
        )
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
        review_kind=scope,
    )
    record_review_event(
        module_root=module_root,
        run_id=run_id,
        review=review,
        completed_message=f"Проверка {title}",
    )
    return review


def _combine_reviews(*reviews: dict[str, Any]) -> dict[str, Any]:
    issues = [
        issue
        for review in reviews
        for issue in review.get("issues", [])
        if isinstance(issue, dict)
    ]
    counts = {
        "must_fix": sum(
            1 for issue in issues if issue.get("disposition") == "must_fix"
        ),
        "advisory": sum(
            1 for issue in issues if issue.get("disposition") == "advisory"
        ),
    }
    blocking = counts["must_fix"] > 0
    summaries = [
        str(review.get("summary") or "").strip()
        for review in reviews
        if str(review.get("summary") or "").strip()
    ]
    notes = [
        str(review.get("review_note") or "").strip()
        for review in reviews
        if str(review.get("review_note") or "").strip()
    ]
    strengths: list[str] = []
    seen_strengths: set[str] = set()
    for review in reviews:
        for value in review.get("strengths", []):
            text = str(value).strip()
            if text and text not in seen_strengths:
                seen_strengths.add(text)
                strengths.append(text)
    return {
        "status": "needs_revision" if blocking else "approved",
        "decision": "revise" if blocking else "approve",
        "blocking": blocking,
        "review_id": "combined_1",
        "review_kind": "combined",
        "coverage_complete": all(
            review.get("coverage_complete") is True for review in reviews
        ),
        "verified_issue_ids": [],
        "reviewed_at": now_iso(),
        "summary": " ".join(summaries),
        "review_note": " ".join(notes),
        "strengths": strengths,
        "issue_counts": counts,
        "issues": issues,
        "source_reviews": [
            {
                "review_id": review.get("review_id"),
                "review_kind": review.get("review_kind"),
                "decision": review.get("decision"),
                "coverage_complete": review.get("coverage_complete"),
                "issue_counts": review.get("issue_counts", {}),
            }
            for review in reviews
        ],
        "correction_pending": False,
    }
