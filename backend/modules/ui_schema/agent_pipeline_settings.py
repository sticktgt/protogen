from __future__ import annotations

from typing import Any


class PipelineConfigurationError(RuntimeError):
    pass


def pipeline_settings(agent_config: dict[str, Any]) -> dict[str, Any]:
    value = agent_config.get("pipeline", {}) if isinstance(agent_config, dict) else {}
    if not isinstance(value, dict):
        raise PipelineConfigurationError("agent.pipeline must be an object")

    required_positive = (
        "analysis_batch_size",
        "planning_batch_size",
        "audit_batch_size",
        "correction_batch_size",
        "stage_attempts",
        "apply_repair_attempts",
        "validation_repair_attempts",
    )
    result = dict(value)
    for key in required_positive:
        result[key] = _positive_int(value.get(key), key)

    result["correction_rounds"] = _positive_int(
        value.get("correction_rounds", 2),
        "correction_rounds",
    )
    result["structural_review_candidate_limit"] = _positive_int(
        value.get("structural_review_candidate_limit", 24),
        "structural_review_candidate_limit",
    )

    output_contract_prompt = str(value.get("output_contract_prompt") or "").strip()
    if not output_contract_prompt:
        raise PipelineConfigurationError("agent.pipeline.output_contract_prompt is required")
    result["output_contract_prompt"] = output_contract_prompt

    change_rules_prompt = str(value.get("change_rules_prompt") or "").strip()
    if not change_rules_prompt:
        raise PipelineConfigurationError("agent.pipeline.change_rules_prompt is required")
    result["change_rules_prompt"] = change_rules_prompt

    tool_choice = str(value.get("tool_choice") or "").strip()
    if not tool_choice:
        raise PipelineConfigurationError("agent.pipeline.tool_choice is required")
    result["tool_choice"] = tool_choice

    return result


def pipeline_output_contract_prompt_name(agent_config: dict[str, Any]) -> str:
    return str(pipeline_settings(agent_config)["output_contract_prompt"])


def pipeline_change_rules_prompt_name(agent_config: dict[str, Any]) -> str:
    return str(pipeline_settings(agent_config)["change_rules_prompt"])


def stage_prompt_name(agent_config: dict[str, Any], stage: str) -> str:
    settings = pipeline_settings(agent_config)
    stages = settings.get("stages", {})
    if not isinstance(stages, dict):
        raise PipelineConfigurationError("agent.pipeline.stages must be an object")
    stage_config = stages.get(stage)
    if not isinstance(stage_config, dict):
        raise PipelineConfigurationError(f"agent.pipeline.stages.{stage} is not configured")
    prompt_name = str(stage_config.get("prompt") or "").strip()
    if not prompt_name:
        raise PipelineConfigurationError(
            f"agent.pipeline.stages.{stage}.prompt is required"
        )
    return prompt_name


def stage_tool_name(agent_config: dict[str, Any], stage: str) -> str:
    settings = pipeline_settings(agent_config)
    stages = settings.get("stages", {})
    if not isinstance(stages, dict):
        raise PipelineConfigurationError("agent.pipeline.stages must be an object")
    stage_config = stages.get(stage)
    if not isinstance(stage_config, dict):
        raise PipelineConfigurationError(f"agent.pipeline.stages.{stage} is not configured")
    tool_name = str(stage_config.get("tool_name") or "").strip()
    if not tool_name:
        raise PipelineConfigurationError(
            f"agent.pipeline.stages.{stage}.tool_name is required"
        )
    return tool_name


def _positive_int(value: Any, key: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PipelineConfigurationError(
            f"agent.pipeline.{key} must be a positive integer"
        ) from exc
    if parsed <= 0:
        raise PipelineConfigurationError(
            f"agent.pipeline.{key} must be a positive integer"
        )
    return parsed
