from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from backend.modules.ui_schema.agent_events import append_event
from backend.modules.ui_schema.agent_pipeline_output import (
    PipelineOutputEnvelope,
    extract_stage_payload,
    response_transport_summary,
)
from backend.modules.ui_schema.agent_pipeline_settings import (
    pipeline_change_rules_prompt_name,
    pipeline_output_contract_prompt_name,
    pipeline_settings,
    stage_prompt_name,
    stage_tool_name,
)
from backend.modules.ui_schema.agent_prompts import render_prompt

T = TypeVar("T", bound=BaseModel)


class PipelineStageError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        validation_errors: list[str] | None = None,
        previous_output: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.validation_errors = list(validation_errors or [])
        self.previous_output = previous_output


def invoke_structured_stage(
    *,
    model: Any,
    output_model: type[T],
    stage: str,
    context: dict[str, Any],
    module_root,
    run_id: str,
    agent_config: dict[str, Any],
    callback: Any,
    invocation_metadata: dict[str, Any],
    attempts: int | None = None,
    attempt_number: int | None = None,
    attempt_total: int | None = None,
) -> T:
    """Invoke one isolated stage with a minimal tool envelope and JSON fallback."""
    try:
        from langchain_core.tools import StructuredTool
    except ImportError as exc:
        raise RuntimeError("LangChain structured tools are not installed") from exc

    settings = pipeline_settings(agent_config)
    prompt_name = stage_prompt_name(agent_config, stage)
    tool_name = stage_tool_name(agent_config, stage)
    maximum_attempts = int(attempts or settings["stage_attempts"])
    displayed_attempt = int(attempt_number or 1)
    displayed_total = int(attempt_total or maximum_attempts)
    prompt_context = dict(context)
    raw_feedback = prompt_context.pop("validation_feedback", [])
    validation_errors = (
        [str(item) for item in raw_feedback]
        if isinstance(raw_feedback, list)
        else [str(raw_feedback)]
    )
    previous_output: Any = prompt_context.pop("previous_output", None)
    output_schema_json = json.dumps(
        output_model.model_json_schema(),
        ensure_ascii=False,
        separators=(",", ":"),
    )

    def _capture(payload: dict[str, Any]) -> dict[str, Any]:
        return payload

    output_contract = render_prompt(
        agent_config,
        pipeline_output_contract_prompt_name(agent_config),
        output_tool_name=tool_name,
        output_schema_json=output_schema_json,
    )
    change_rules = render_prompt(
        agent_config,
        pipeline_change_rules_prompt_name(agent_config),
    )
    base_prompt = _render_stage_prompt(
        agent_config=agent_config,
        prompt_name=prompt_name,
        prompt_context=prompt_context,
        validation_errors=[],
        previous_output=None,
        output_contract=output_contract,
        change_rules=change_rules,
    )
    description = next(
        (line.strip() for line in base_prompt.splitlines() if line.strip()),
        tool_name,
    )
    output_tool = StructuredTool.from_function(
        func=_capture,
        name=tool_name,
        description=description,
        args_schema=PipelineOutputEnvelope,
    )
    bound_model = model.bind_tools(
        [output_tool],
        tool_choice=settings["tool_choice"],
    )

    for attempt in range(1, maximum_attempts + 1):
        prompt = _render_stage_prompt(
            agent_config=agent_config,
            prompt_name=prompt_name,
            prompt_context=prompt_context,
            validation_errors=validation_errors,
            previous_output=previous_output,
            output_contract=output_contract,
            change_rules=change_rules,
        )
        append_event(
            module_root,
            run_id,
            event_type="pipeline_stage_start",
            message=(
                f"Этап {stage}: попытка {displayed_attempt} "
                f"из {displayed_total}"
            ),
            data={
                "stage": stage,
                "attempt": displayed_attempt,
                "maximum_attempts": displayed_total,
                "structured_attempt": attempt,
            },
        )
        invocation_config = {
            "run_name": f"ui_schema_v2_{stage}_{run_id}_{attempt}",
            "metadata": {**invocation_metadata, "pipeline_stage": stage},
        }
        if callback is not None:
            invocation_config["callbacks"] = [callback]
        response = bound_model.invoke(
            [{"role": "user", "content": prompt}],
            config=invocation_config,
        )
        try:
            raw_args = extract_stage_payload(response, expected_name=tool_name)
        except ValueError as exc:
            validation_errors = [str(exc)]
            append_event(
                module_root,
                run_id,
                event_type="pipeline_stage_output_missing",
                level="warning",
                message=f"Этап {stage} не вернул распознаваемый структурированный ответ",
                data={
                    "stage": stage,
                    "attempt": attempt,
                    "transport": response_transport_summary(response),
                },
            )
            continue
        previous_output = raw_args
        try:
            result = output_model.model_validate(raw_args)
        except ValidationError as exc:
            validation_errors = _validation_messages(exc)
            append_event(
                module_root,
                run_id,
                event_type="pipeline_stage_output_invalid",
                level="warning",
                message=(
                    f"Этап {stage} вернул технически некорректный результат; "
                    f"ошибок: {len(validation_errors)}"
                ),
                data={"stage": stage, "attempt": attempt},
            )
            continue
        append_event(
            module_root,
            run_id,
            event_type="pipeline_stage_completed",
            message=f"Этап {stage} завершён",
            data={
                "stage": stage,
                "attempt": displayed_attempt,
                "maximum_attempts": displayed_total,
                "structured_attempt": attempt,
            },
        )
        return result

    details = "; ".join(validation_errors[:10]) or "structured output was not returned"
    raise PipelineStageError(
        f"Этап {stage} не вернул валидный структурированный результат: {details}",
        validation_errors=validation_errors,
        previous_output=(previous_output if isinstance(previous_output, dict) else None),
    )


def _render_stage_prompt(
    *,
    agent_config: dict[str, Any],
    prompt_name: str,
    prompt_context: dict[str, Any],
    validation_errors: list[str],
    previous_output: Any,
    output_contract: str,
    change_rules: str,
) -> str:
    return render_prompt(
        agent_config,
        prompt_name,
        context_json=json.dumps(
            prompt_context,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        validation_errors_json=json.dumps(
            validation_errors,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        previous_output_json=json.dumps(
            previous_output,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        output_contract=output_contract,
        change_rules=change_rules,
    )


def _validation_messages(exc: ValidationError) -> list[str]:
    messages: list[str] = []
    for item in exc.errors(include_url=False):
        location = ".".join(str(part) for part in item.get("loc", ()))
        message = str(item.get("msg") or item.get("type") or "validation error")
        messages.append(f"{location}: {message}" if location else message)
    return messages
