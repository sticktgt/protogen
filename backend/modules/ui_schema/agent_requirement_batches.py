from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_requirement_scope import compact_requirements

_DEFAULT_BATCH_SIZE = 28


def configured_requirement_fields(agent_config: dict[str, Any] | None) -> list[str] | None:
    config = agent_config if isinstance(agent_config, dict) else {}
    context = config.get("context", {})
    fields = context.get("requirement_fields") if isinstance(context, dict) else None
    if not isinstance(fields, list):
        return None
    return [str(item) for item in fields if str(item).strip()]


def requirement_batch_size(agent_config: dict[str, Any] | None) -> int:
    config = agent_config if isinstance(agent_config, dict) else {}
    analysis = config.get("requirement_analysis", {})
    value = analysis.get("batch_size", _DEFAULT_BATCH_SIZE) if isinstance(analysis, dict) else _DEFAULT_BATCH_SIZE
    return max(1, int(value))


def build_requirement_batches(
    run_path: Path,
    *,
    agent_config: dict[str, Any] | None,
    fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Split current requirements mechanically, preserving source order.

    The backend does not infer domains or semantics. Batches are fixed-size slices of
    the current requirement list and only bound the amount of content reviewed in one
    model step.
    """
    requirements = compact_requirements(run_path, fields=fields)
    size = requirement_batch_size(agent_config)
    batches: list[dict[str, Any]] = []
    for offset in range(0, len(requirements), size):
        items = requirements[offset : offset + size]
        index = len(batches) + 1
        batches.append(
            {
                "batch_id": f"requirements_{index:02d}",
                "index": index,
                "count": len(items),
                "requirement_ids": [str(item.get("id") or "") for item in items],
            }
        )
    return batches


def batch_by_id(
    run_path: Path,
    *,
    agent_config: dict[str, Any] | None,
    batch_id: str,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    normalized = str(batch_id or "").strip()
    for batch in build_requirement_batches(
        run_path,
        agent_config=agent_config,
        fields=fields,
    ):
        if batch["batch_id"] == normalized:
            return batch
    raise ValueError(f"Unknown requirement batch_id: {normalized}")


def next_batch_id(
    run_path: Path,
    *,
    agent_config: dict[str, Any] | None,
    completed_batch_ids: set[str],
) -> str | None:
    for batch in build_requirement_batches(run_path, agent_config=agent_config):
        if batch["batch_id"] not in completed_batch_ids:
            return str(batch["batch_id"])
    return None


def requirement_batch_context(
    run_path: Path,
    *,
    agent_config: dict[str, Any] | None,
    batch_id: str,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Return one bounded requirement batch with its projected source content."""
    batches = build_requirement_batches(
        run_path,
        agent_config=agent_config,
        fields=fields,
    )
    batch = next(
        (item for item in batches if str(item.get("batch_id") or "") == str(batch_id or "").strip()),
        None,
    )
    if batch is None:
        raise ValueError(f"Unknown requirement batch_id: {str(batch_id or '').strip()}")
    ids = set(str(item) for item in batch.get("requirement_ids", []))
    requirements = [
        item
        for item in compact_requirements(run_path, fields=fields)
        if str(item.get("id") or "") in ids
    ]
    return {
        "batch_id": str(batch["batch_id"]),
        "index": int(batch["index"]),
        "count": len(requirements),
        "total_batches": len(batches),
        "remaining_batches_after_this": max(0, len(batches) - int(batch["index"])),
        "requirement_ids": list(batch["requirement_ids"]),
        "requirements": requirements,
    }


def first_requirement_batch_context(
    run_path: Path,
    *,
    agent_config: dict[str, Any] | None,
    fields: list[str] | None = None,
) -> dict[str, Any] | None:
    batches = build_requirement_batches(
        run_path,
        agent_config=agent_config,
        fields=fields,
    )
    if not batches:
        return None
    return requirement_batch_context(
        run_path,
        agent_config=agent_config,
        batch_id=str(batches[0]["batch_id"]),
        fields=fields,
    )


def requirement_subset_context(
    run_path: Path,
    *,
    agent_config: dict[str, Any] | None,
    batch_id: str,
    requirement_ids: set[str] | list[str],
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Return the current batch context restricted to unresolved IDs.

    Selection is purely by exact requirement ID and preserves source order.
    """

    base = requirement_batch_context(
        run_path,
        agent_config=agent_config,
        batch_id=batch_id,
        fields=fields,
    )
    wanted = {str(item) for item in requirement_ids if str(item).strip()}
    requirements = [
        item
        for item in base.get("requirements", [])
        if isinstance(item, dict) and str(item.get("id") or "") in wanted
    ]
    ordered_ids = [
        str(item.get("id") or "")
        for item in requirements
        if str(item.get("id") or "")
    ]
    return {
        **base,
        "count": len(requirements),
        "requirement_ids": ordered_ids,
        "requirements": requirements,
        "partial_batch": len(ordered_ids) != int(base.get("count", 0)),
    }
