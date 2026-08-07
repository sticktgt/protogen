from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel

from backend.modules.ui_schema.agent_pipeline_models import PipelineDecision
from backend.modules.ui_schema.agent_preflight_decisions import (
    collect_decision_action_issues,
)
from backend.modules.ui_schema.agent_preflight_elements import (
    collect_move_issues,
    collect_move_target_issues,
    collect_upsert_issues,
)
from backend.modules.ui_schema.agent_preflight_issues import (
    ChangePreflightError,
    deduplicate_preflight_issues,
    preflight_issue,
)
from backend.modules.ui_schema.agent_preflight_links import collect_link_issues
from backend.modules.ui_schema.agent_preflight_state import (
    VirtualSchema,
    collect_page_operation_issues,
)
from backend.modules.ui_schema.agent_target_catalog import build_target_catalog
from backend.modules.ui_schema.agent_upsert_normalization import flatten_upsert_changes

__all__ = ["ChangePreflightError", "validate_plan_preflight"]


def validate_plan_preflight(
    *,
    schema_root: Path,
    decisions: Iterable[PipelineDecision],
    changes: Any,
) -> list[dict[str, Any]]:
    """Collect static decision and change-bundle errors without mutating files."""
    state = VirtualSchema.from_root(schema_root)
    issues: list[dict[str, Any]] = []
    dumped = (
        changes.model_dump(exclude_none=True)
        if isinstance(changes, BaseModel)
        else dict(changes)
    )
    create_pages = list(dumped.get("create_pages") or [])
    update_pages = list(dumped.get("update_pages") or [])
    move_elements = list(dumped.get("move_elements") or [])
    ui_links = list(dumped.get("ui_links") or [])
    raw_upserts = list(dumped.get("upsert_elements") or [])

    try:
        upsert_elements = flatten_upsert_changes(raw_upserts)
    except (TypeError, ValueError) as exc:
        upsert_elements = []
        issues.append(preflight_issue("invalid_upsert_structure", str(exc)))

    collect_page_operation_issues(
        state,
        create_pages=create_pages,
        update_pages=update_pages,
        issues=issues,
    )
    move_map = collect_move_issues(
        state,
        move_elements=move_elements,
        issues=issues,
    )
    collect_upsert_issues(
        state,
        upsert_elements=upsert_elements,
        move_map=move_map,
        issues=issues,
    )
    collect_move_target_issues(state, move_map=move_map, issues=issues)
    collect_link_issues(state, ui_links=ui_links, issues=issues)
    collect_decision_action_issues(
        decisions=list(decisions),
        initial_catalog=build_target_catalog(schema_root),
        final_state=state,
        issues=issues,
    )
    return deduplicate_preflight_issues(issues)
