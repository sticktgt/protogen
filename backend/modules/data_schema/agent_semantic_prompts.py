from __future__ import annotations

import json
from typing import Any

from backend.modules.data_schema.agent_prompts import load_prompt


def render_semantic_coverage_review_prompt(
    agent_config: dict[str, Any],
    context: dict[str, Any],
    *,
    review_number: int,
) -> str:
    return _render_review_prompt(
        agent_config=agent_config,
        prompt_name="semantic_coverage_review",
        context=context,
        review_number=review_number,
        error_label="Контекст проверки покрытия требований",
    )


def render_semantic_consistency_review_prompt(
    agent_config: dict[str, Any],
    context: dict[str, Any],
    *,
    review_number: int,
) -> str:
    return _render_review_prompt(
        agent_config=agent_config,
        prompt_name="semantic_consistency_review",
        context=context,
        review_number=review_number,
        error_label="Контекст проверки согласованности схемы",
    )


def render_semantic_verification_prompt(
    agent_config: dict[str, Any],
    context: dict[str, Any],
    *,
    verification_number: int,
) -> str:
    settings = semantic_review_settings(agent_config)
    return _render_context_prompt(
        agent_config=agent_config,
        prompt_name="semantic_verification",
        context=context,
        values={
            "verification_number": verification_number,
            "max_issues": positive_int(settings, "max_issues"),
        },
        error_label="Контекст проверки исправлений",
    )


def render_semantic_correction_prompt(
    agent_config: dict[str, Any],
    review: dict[str, Any],
    context: dict[str, Any],
) -> str:
    template = load_prompt(agent_config, "semantic_correction")
    correction_review = {
        "review_id": review.get("review_id"),
        "issue_counts": review.get("issue_counts", {}),
        "issues": review.get("issues", []),
    }
    review_json = json.dumps(
        correction_review, ensure_ascii=False, separators=(",", ":")
    )
    context_json = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    maximum = positive_int(semantic_review_settings(agent_config), "max_context_bytes")
    if len(context_json.encode("utf-8")) > maximum:
        raise ValueError(
            "Контекст исправления по результатам review превышает "
            "agent.semantic_review.max_context_bytes"
        )
    return template.format_map(
        {
            "semantic_review_json": review_json,
            "correction_context_json": context_json,
        }
    ).strip()


def semantic_review_settings(agent_config: dict[str, Any]) -> dict[str, Any]:
    value = agent_config.get("semantic_review", {}) if isinstance(agent_config, dict) else {}
    if not isinstance(value, dict):
        raise ValueError("agent.semantic_review must be an object")
    return value


def semantic_review_enabled(agent_config: dict[str, Any]) -> bool:
    settings = semantic_review_settings(agent_config)
    if "enabled" not in settings:
        raise ValueError("agent.semantic_review.enabled must be configured")
    return bool(settings["enabled"])


def non_negative_int(settings: dict[str, Any], key: str) -> int:
    try:
        value = int(settings[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"agent.semantic_review.{key} must be a non-negative integer") from exc
    if value < 0:
        raise ValueError(f"agent.semantic_review.{key} must be a non-negative integer")
    return value


def positive_int(settings: dict[str, Any], key: str) -> int:
    value = non_negative_int(settings, key)
    if value <= 0:
        raise ValueError(f"agent.semantic_review.{key} must be a positive integer")
    return value


def _render_review_prompt(
    *,
    agent_config: dict[str, Any],
    prompt_name: str,
    context: dict[str, Any],
    review_number: int,
    error_label: str,
) -> str:
    settings = semantic_review_settings(agent_config)
    return _render_context_prompt(
        agent_config=agent_config,
        prompt_name=prompt_name,
        context=context,
        values={
            "review_number": review_number,
            "max_issues": positive_int(settings, "max_issues"),
        },
        error_label=error_label,
    )


def _render_context_prompt(
    *,
    agent_config: dict[str, Any],
    prompt_name: str,
    context: dict[str, Any],
    values: dict[str, Any],
    error_label: str,
) -> str:
    template = load_prompt(agent_config, prompt_name)
    context_json = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    maximum = positive_int(semantic_review_settings(agent_config), "max_context_bytes")
    if len(context_json.encode("utf-8")) > maximum:
        raise ValueError(
            f"{error_label} превышает agent.semantic_review.max_context_bytes"
        )
    return template.format_map({**values, "context_json": context_json}).strip()
