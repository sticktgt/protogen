from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_events import append_event
from backend.modules.data_schema.agent_prompts import load_prompt
from backend.modules.data_schema.agent_review_correction_context import (
    build_review_correction_context,
)
from backend.modules.data_schema.agent_runs import update_run
from backend.modules.data_schema.agent_semantic_correction_apply import (
    apply_semantic_correction_plan,
)
from backend.modules.data_schema.agent_semantic_correction_invocation import (
    invoke_semantic_correction_plan,
)
from backend.modules.data_schema.agent_semantic_prompts import (
    render_semantic_correction_prompt,
)


def apply_semantic_correction(
    *,
    root: Path,
    module_root: Path,
    run_id: str,
    review: dict[str, Any],
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
    correction_round: int,
) -> dict[str, Any]:
    """Request and technically apply one structured correction plan."""
    update_run(module_root, run_id, phase="semantic_correction")
    append_event(
        module_root,
        run_id,
        event_type="semantic_correction_start",
        level="warning",
        message=(
            "LLM формирует основной план смысловых исправлений"
            if correction_round == 1
            else "LLM формирует точечный recovery-план для оставшихся blockers"
        ),
        data={
            "source_review_id": review.get("review_id"),
            "correction_round": correction_round,
        },
    )
    correction_context = build_review_correction_context(
        root,
        review,
        correction_round=correction_round,
    )
    prompt = render_semantic_correction_prompt(
        agent_config,
        review,
        correction_context,
    )
    append_event(
        module_root,
        run_id,
        event_type="semantic_correction_context_ready",
        message="Подготовлен сокращённый контекст смысловых исправлений",
        data={
            "context_bytes": len(
                json.dumps(
                    correction_context,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ),
            "requirement_count": len(
                correction_context.get("requirements", {}).get("requirements", [])
            ),
            "removable_target_count": len(
                correction_context.get("removable_added_targets", [])
            ),
        },
    )
    (root / "input" / f"semantic_correction_round_{correction_round}.md").write_text(
        prompt,
        encoding="utf-8",
    )

    plan = invoke_semantic_correction_plan(
        module_root=module_root,
        run_id=run_id,
        run_path=root,
        llm_settings=llm_settings,
        agent_config=agent_config,
        system_prompt=load_prompt(agent_config, "semantic_correction_system"),
        correction_prompt=prompt,
        correction_round=correction_round,
    )
    validation = apply_semantic_correction_plan(
        run_path=root,
        plan=plan,
        correction_round=correction_round,
    )
    applied = validation.get("correction_applied") is True
    append_event(
        module_root,
        run_id,
        event_type="semantic_correction_validation",
        level="info" if applied else "warning",
        message=(
            "Единый план смысловых исправлений применён и прошёл техническую проверку"
            if applied
            else "Единый план исправлений отклонён технически; исходная корректная схема восстановлена"
        ),
        data={
            "error_count": len(validation.get("errors", [])),
            "correction_applied": applied,
            "correction_error": str(validation.get("correction_error") or "")[:500],
            "operation_count": len(validation.get("correction_operations", [])),
            "correction_round": correction_round,
        },
    )
    return validation
