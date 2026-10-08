from __future__ import annotations

from typing import Any



def build_review_batches(
    context: dict[str, Any],
    *,
    agent_config: dict[str, Any] | None,
    prefix: str,
) -> list[dict[str, Any]]:
    candidates = context.get("candidates", []) if isinstance(context, dict) else []
    candidates = [item for item in candidates if isinstance(item, dict)]
    size = _review_batch_size(agent_config)
    result: list[dict[str, Any]] = []
    for offset in range(0, len(candidates), size):
        index = len(result) + 1
        result.append(
            {
                "review_batch_id": f"{prefix}_{index:02d}",
                "index": index,
                "candidates": candidates[offset : offset + size],
            }
        )
    return result


def next_review_batch_id(
    batches: list[dict[str, Any]],
    *,
    completed_batch_ids: set[str],
) -> str | None:
    for batch in batches:
        batch_id = str(batch.get("review_batch_id") or "")
        if batch_id and batch_id not in completed_batch_ids:
            return batch_id
    return None


def review_batch_by_id(
    batches: list[dict[str, Any]],
    *,
    review_batch_id: str,
) -> dict[str, Any]:
    normalized = str(review_batch_id or "").strip()
    for batch in batches:
        if str(batch.get("review_batch_id") or "") == normalized:
            return batch
    raise ValueError(f"Unknown review_batch_id: {normalized}")


def public_review_batch_context(
    context: dict[str, Any],
    *,
    batches: list[dict[str, Any]],
    review_batch_id: str,
    completed_batch_ids: set[str],
    reviewed_candidate_ids: set[str] | None = None,
) -> dict[str, Any]:
    batch = review_batch_by_id(batches, review_batch_id=review_batch_id)
    reviewed = reviewed_candidate_ids or set()
    visible_candidates = [
        item
        for item in batch.get("candidates", [])
        if isinstance(item, dict) and candidate_id(item) not in reviewed
    ]
    next_id = _next_after_current(
        batches,
        current_id=review_batch_id,
        completed_batch_ids=completed_batch_ids,
    )
    return {
        "policy": dict(context.get("policy", {})) if isinstance(context, dict) else {},
        "review_batch_id": review_batch_id,
        "batch_candidate_count": len(visible_candidates),
        "original_batch_candidate_count": len(batch.get("candidates", [])),
        "total_candidate_count": sum(len(item.get("candidates", [])) for item in batches),
        "remaining_review_batches": sum(
            1
            for item in batches
            if str(item.get("review_batch_id") or "") not in completed_batch_ids
            and str(item.get("review_batch_id") or "") != review_batch_id
        ),
        "next_review_batch_id": next_id,
        "candidates": [_public_candidate(item) for item in visible_candidates],
    }


def _public_candidate(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if key not in {"selection_signals", "related_target_summaries"}
        and not str(key).startswith("_")
    }


def candidate_id(item: dict[str, Any]) -> str:
    requirement = item.get("requirement", {})
    if isinstance(requirement, dict) and str(requirement.get("id") or "").strip():
        return str(requirement.get("id") or "").strip()
    return ""


def _next_after_current(
    batches: list[dict[str, Any]],
    *,
    current_id: str,
    completed_batch_ids: set[str],
) -> str | None:
    seen_current = False
    for batch in batches:
        batch_id = str(batch.get("review_batch_id") or "")
        if batch_id == current_id:
            seen_current = True
            continue
        if seen_current and batch_id not in completed_batch_ids:
            return batch_id
    return None


def _review_batch_size(agent_config: dict[str, Any] | None) -> int:
    config = agent_config if isinstance(agent_config, dict) else {}
    analysis = config.get("requirement_analysis", {})
    value = analysis.get("review_batch_size", 32) if isinstance(analysis, dict) else 32
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 32
    return max(1, parsed)
