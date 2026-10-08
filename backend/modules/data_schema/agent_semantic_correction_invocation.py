from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_events import append_event, reserve_metric_slot
from backend.modules.data_schema.agent_json_arguments import decode_json_argument
from backend.modules.data_schema.agent_limits import execution_limits
from backend.modules.data_schema.agent_llm import create_chat_model
from backend.modules.data_schema.agent_llm_retry import invoke_with_transient_llm_retry
from backend.modules.data_schema.agent_monitor import AgentRunStopped, create_run_callback
from backend.modules.data_schema.agent_semantic_correction_models import (
    SemanticCorrectionPlanPayload,
)
from backend.modules.data_schema.agent_semantic_prompts import (
    positive_int,
    semantic_review_settings,
)
from backend.modules.data_schema.agent_tool_observability import tool_argument_shape
from backend.modules.data_schema.files import write_json

_TOOL_NAME = "submit_data_schema_semantic_correction"


def invoke_semantic_correction_plan(
    *,
    module_root: Path,
    run_id: str,
    run_path: Path,
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
    system_prompt: str,
    correction_prompt: str,
    correction_round: int,
) -> SemanticCorrectionPlanPayload:
    """Request one complete correction plan in a single structured LLM response."""
    settings = semantic_review_settings(agent_config)
    model = create_chat_model(llm_settings, agent_config, profile="correction")
    tool = _correction_submission_tool()
    bound = model.bind_tools([tool], tool_choice="required")
    limits = execution_limits(agent_config)
    callback = create_run_callback(
        module_root=module_root,
        run_id=run_id,
        limits=limits,
    )
    attempts = positive_int(settings, "response_attempts")
    last_error = ""
    for response_attempt in range(1, attempts + 1):
        prompt = correction_prompt
        if last_error:
            prompt += (
                "\n\nПредыдущий ответ не соответствовал контракту инструмента. "
                f"Исправь только формат полного плана. Техническая ошибка: {last_error}"
            )
        response = invoke_with_transient_llm_retry(
            lambda: bound.invoke(
                [("system", system_prompt), ("user", prompt)],
                config={
                    "callbacks": [callback],
                    "run_name": (
                        "data_schema_semantic_correction_"
                        f"{run_id}_{correction_round}_{response_attempt}"
                    ),
                    "metadata": {
                        "run_id": run_id,
                        "semantic_correction_round": correction_round,
                        "response_attempt": response_attempt,
                    },
                },
            ),
            agent_config=agent_config,
            module_root=module_root,
            run_id=run_id,
            operation_name=f"LLM correction round {correction_round}",
        )
        try:
            args = _correction_tool_args(response)
            _record_submission_call(
                module_root=module_root,
                run_id=run_id,
                args=args,
                limits=limits,
                correction_round=correction_round,
            )
            plan = SemanticCorrectionPlanPayload.model_validate(args)
            write_json(
                run_path / "result" / f"semantic_correction_plan_{correction_round}.json",
                plan.model_dump(exclude_none=True),
            )
            return plan
        except (TypeError, ValueError) as exc:
            last_error = str(exc)[:500]
            append_event(
                module_root,
                run_id,
                event_type="semantic_correction_response_rejected",
                level="warning",
                message=(
                    "План смысловых исправлений не прошёл техническую проверку "
                    f"формата: {last_error}"
                ),
                data={
                    "response_attempt": response_attempt,
                    "correction_round": correction_round,
                },
            )
    raise RuntimeError(
        "LLM correction не вернуло корректный структурированный план: " + last_error
    )


def _correction_submission_tool():
    try:
        from langchain_core.tools import tool
    except ImportError as exc:
        raise RuntimeError("LangChain core tools are not installed") from exc

    @tool(args_schema=SemanticCorrectionPlanPayload)
    def submit_data_schema_semantic_correction(
        summary: str,
        write_schema_document: dict[str, Any] | None = None,
        write_dictionaries: list[dict[str, Any]] | None = None,
        write_entities: list[dict[str, Any]] | None = None,
        write_relations: list[dict[str, Any]] | None = None,
        patch_schema: dict[str, Any] | None = None,
        patch_dictionaries: list[dict[str, Any]] | None = None,
        patch_entities: list[dict[str, Any]] | None = None,
        patch_relations: list[dict[str, Any]] | None = None,
        remove_targets: list[str] | None = None,
        requirement_updates: list[dict[str, Any]] | None = None,
        agent_note: str | None = None,
        warnings: list[str] | None = None,
    ) -> str:
        """Submit one complete executable correction plan for all review issues."""
        return "accepted"

    return submit_data_schema_semantic_correction


def _correction_tool_args(response: Any) -> dict[str, Any]:
    calls = getattr(response, "tool_calls", None)
    if calls is None and isinstance(response, dict):
        calls = response.get("tool_calls")
    if not isinstance(calls, list) or not calls:
        raise ValueError(
            "semantic correction response did not call the required submission tool"
        )
    for call in calls:
        name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
        if name != _TOOL_NAME:
            continue
        args = call.get("args") if isinstance(call, dict) else getattr(call, "args", None)
        decoded = decode_json_argument(args, label="semantic correction tool arguments")
        if not isinstance(decoded, dict):
            raise ValueError("semantic correction tool arguments must be an object")
        return decoded
    raise ValueError(f"semantic correction response did not call {_TOOL_NAME}")


def _record_submission_call(
    *,
    module_root: Path,
    run_id: str,
    args: dict[str, Any],
    limits: dict[str, int],
    correction_round: int = 1,
) -> None:
    maximum = limits["max_tool_calls"]
    metrics = reserve_metric_slot(
        module_root,
        run_id,
        "tool_calls",
        maximum=maximum,
        last_tool=_TOOL_NAME,
    )
    if metrics is None:
        raise AgentRunStopped(f"Достигнут лимит вызовов инструментов: {maximum}")
    append_event(
        module_root,
        run_id,
        event_type="tool_end",
        message="LLM correction передало единый структурированный план",
        data={
            "tool": _TOOL_NAME,
            "tool_call": metrics.get("tool_calls", 0),
            "argument_shape": tool_argument_shape(args),
            "correction_round": correction_round,
        },
    )
