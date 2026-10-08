from __future__ import annotations

from typing import Any

from backend.modules.ui_schema.agent_pipeline_models import PipelineDecision
from backend.modules.ui_schema.agent_preflight_issues import preflight_issue
from backend.modules.ui_schema.agent_preflight_state import VirtualSchema


def collect_decision_action_issues(
    *,
    decisions: list[PipelineDecision],
    initial_catalog: dict[tuple[str, str], dict[str, Any]],
    final_state: VirtualSchema,
    issues: list[dict[str, Any]],
) -> None:
    for decision in decisions:
        for target in decision.targets:
            key = (target.target_type, target.target_id)
            existed = key in initial_catalog
            final_exists = final_state.target_exists(
                target.target_type,
                target.target_id,
            )
            if target.action in {"reuse", "extend"} and not existed:
                alternates = sorted(
                    f"{candidate_type}:{candidate_id}"
                    for candidate_type, candidate_id in initial_catalog
                    if candidate_id == target.target_id
                )
                alternate_note = (
                    f" Точный ID существует как {', '.join(alternates)}."
                    if alternates
                    else ""
                )
                issues.append(
                    preflight_issue(
                        "missing_target_for_existing_action",
                        (
                            f"{decision.requirement_id}: action={target.action} требует существующую цель "
                            f"{target.target_type}:{target.target_id}.{alternate_note} Используй точный существующий ID "
                            "либо action=create и операцию создания"
                        ),
                        requirement_id=decision.requirement_id,
                        target_type=target.target_type,
                        target_id=target.target_id,
                        target_status="missing",
                        allowed_actions=["create"],
                        alternate_targets=alternates,
                    )
                )
            elif target.action == "create" and existed:
                issues.append(
                    preflight_issue(
                        "existing_target_with_create",
                        (
                            f"{decision.requirement_id}: цель {target.target_type}:{target.target_id} уже существует, "
                            "поэтому action=create недопустим. Используй action=reuse без изменений цели "
                            "либо action=extend, если пакет обновляет существующую цель"
                        ),
                        requirement_id=decision.requirement_id,
                        target_type=target.target_type,
                        target_id=target.target_id,
                        target_status="existing",
                        allowed_actions=["reuse", "extend"],
                    )
                )
            elif target.action == "create" and not final_exists:
                issues.append(
                    preflight_issue(
                        "create_target_not_created",
                        (
                            f"{decision.requirement_id}: action=create указывает на "
                            f"{target.target_type}:{target.target_id}, но пакет не создаёт эту цель"
                        ),
                        requirement_id=decision.requirement_id,
                        target_type=target.target_type,
                        target_id=target.target_id,
                        target_status="missing",
                        allowed_actions=["create"],
                    )
                )
