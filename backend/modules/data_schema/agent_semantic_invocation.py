from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from backend.modules.data_schema.agent_events import append_event, reserve_metric_slot
from backend.modules.data_schema.agent_json_arguments import decode_json_argument
from backend.modules.data_schema.agent_limits import execution_limits
from backend.modules.data_schema.agent_llm import create_chat_model
from backend.modules.data_schema.agent_monitor import AgentRunStopped, create_run_callback
from backend.modules.data_schema.agent_paths import now_iso
from backend.modules.data_schema.agent_semantic_models import SemanticReviewPayload
from backend.modules.data_schema.agent_semantic_prompts import (
    positive_int,
    semantic_review_settings,
)
from backend.modules.data_schema.agent_tool_observability import tool_argument_shape
from backend.modules.data_schema.files import write_json

_TOOL_NAME = "submit_data_schema_semantic_review"
ReviewKind = Literal["coverage", "consistency", "correction_verification"]


def invoke_semantic_review(
    *,
    module_root: Path,
    run_id: str,
    run_path: Path,
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
    system_prompt: str,
    review_prompt: str,
    review_id: str,
    review_kind: ReviewKind,
    expected_issue_ids: list[str] | None = None,
) -> dict[str, Any]:
    settings = semantic_review_settings(agent_config)
    model = create_chat_model(llm_settings, agent_config, profile="review")
    tool = _review_submission_tool()
    bound = model.bind_tools([tool], tool_choice="required")
    callback = create_run_callback(
        module_root=module_root,
        run_id=run_id,
        limits=execution_limits(agent_config),
    )
    retries = positive_int(settings, "response_attempts")
    last_error = ""
    for response_attempt in range(1, retries + 1):
        prompt = review_prompt
        if last_error:
            prompt += (
                "\n\nПредыдущий ответ не соответствовал контракту инструмента. "
                f"Исправь только формат ответа. Техническая ошибка: {last_error}"
            )
        response = bound.invoke(
            [("system", system_prompt), ("user", prompt)],
            config={
                "callbacks": [callback],
                "run_name": f"data_schema_semantic_review_{run_id}_{review_id}_{response_attempt}",
                "metadata": {
                    "run_id": run_id,
                    "review_id": review_id,
                    "review_kind": review_kind,
                },
            },
        )
        try:
            args = _review_tool_args(response)
            _record_submission_call(
                module_root=module_root,
                run_id=run_id,
                args=args,
                limits=execution_limits(agent_config),
                review_id=review_id,
                review_kind=review_kind,
            )
            payload = SemanticReviewPayload.model_validate(args)
            review = normalize_semantic_review(
                payload,
                settings,
                review_id=review_id,
                review_kind=review_kind,
                expected_issue_ids=expected_issue_ids or [],
            )
            write_json(run_path / "result" / f"semantic_review_{review_id}.json", review)
            return review
        except (TypeError, ValueError) as exc:
            last_error = str(exc)[:500]
            append_event(
                module_root,
                run_id,
                event_type="semantic_review_response_rejected",
                level="warning",
                message=(
                    "Ответ LLM review не прошёл техническую проверку формата: "
                    f"{last_error}"
                ),
                data={
                    "review_id": review_id,
                    "review_kind": review_kind,
                    "response_attempt": response_attempt,
                },
            )
    raise RuntimeError(
        "LLM review не вернуло корректный структурированный результат: " + last_error
    )


def normalize_semantic_review(
    payload: SemanticReviewPayload,
    settings: dict[str, Any],
    *,
    review_id: str,
    review_kind: ReviewKind,
    expected_issue_ids: list[str],
) -> dict[str, Any]:
    maximum = positive_int(settings, "max_issues")
    if len(payload.issues) > maximum:
        raise ValueError(f"semantic review contains more than {maximum} issues")

    summary = payload.summary.strip()
    if not summary:
        raise ValueError("semantic review summary must not be blank")

    issues: list[dict[str, Any]] = []
    counts = {"must_fix": 0, "advisory": 0}
    for index, item in enumerate(payload.issues, start=1):
        disposition = item.disposition.strip().lower()
        category = item.category.strip()
        message = item.message.strip()
        recommendation = item.recommendation.strip()
        if disposition not in counts:
            raise ValueError(f"unsupported semantic review disposition: {disposition}")
        if not category or not message or not recommendation:
            raise ValueError(
                "semantic review issue category, message and recommendation must not be blank"
            )
        counts[disposition] += 1
        issues.append(
            {
                "id": f"{review_id}_issue_{index}",
                "source_review_id": review_id,
                "disposition": disposition,
                "category": category,
                "message": message,
                "recommendation": recommendation,
                "requirement_ids": _unique_strings(item.requirement_ids),
                "targets": _unique_strings(item.targets),
            }
        )

    decision = payload.decision.strip().lower()
    has_must_fix = counts["must_fix"] > 0
    if decision == "approve" and has_must_fix:
        raise ValueError("semantic review decision approve conflicts with must_fix issues")
    if decision == "revise" and not has_must_fix:
        raise ValueError("semantic review decision revise requires at least one must_fix issue")
    if decision == "approve" and not payload.coverage_complete:
        raise ValueError("semantic review cannot approve when coverage_complete is false")

    verified_issue_ids = _unique_strings(payload.verified_issue_ids)
    if review_kind in {"coverage", "consistency"}:
        if verified_issue_ids:
            raise ValueError("independent review must not return verified_issue_ids")
    else:
        expected = set(_unique_strings(expected_issue_ids))
        actual = set(verified_issue_ids)
        if actual != expected:
            missing = sorted(expected - actual)
            unexpected = sorted(actual - expected)
            details: list[str] = []
            if missing:
                details.append("missing=" + ",".join(missing))
            if unexpected:
                details.append("unexpected=" + ",".join(unexpected))
            raise ValueError(
                "correction verification must cover every expected issue"
                + (": " + "; ".join(details) if details else "")
            )

    blocking = decision == "revise"
    return {
        "status": "needs_revision" if blocking else "approved",
        "decision": decision,
        "blocking": blocking,
        "review_id": review_id,
        "review_kind": review_kind,
        "coverage_complete": bool(payload.coverage_complete),
        "verified_issue_ids": verified_issue_ids,
        "reviewed_at": now_iso(),
        "summary": summary,
        "review_note": payload.review_note.strip(),
        "strengths": _unique_strings(payload.strengths),
        "issue_counts": counts,
        "issues": issues,
    }


def _review_submission_tool():
    try:
        from langchain_core.tools import tool
    except ImportError as exc:
        raise RuntimeError("LangChain core tools are not installed") from exc

    @tool(args_schema=SemanticReviewPayload)
    def submit_data_schema_semantic_review(
        decision: str,
        coverage_complete: bool,
        verified_issue_ids: list[str] | None = None,
        summary: str = "",
        issues: list[dict[str, Any]] | None = None,
        strengths: list[str] | None = None,
        review_note: str = "",
    ) -> str:
        """Submit the requested semantic review of the candidate logical data schema."""
        return "accepted"

    return submit_data_schema_semantic_review


def _review_tool_args(response: Any) -> dict[str, Any]:
    calls = getattr(response, "tool_calls", None)
    if calls is None and isinstance(response, dict):
        calls = response.get("tool_calls")
    if not isinstance(calls, list) or not calls:
        raise ValueError("semantic review response did not call the required submission tool")
    for call in calls:
        name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
        if name != _TOOL_NAME:
            continue
        args = call.get("args") if isinstance(call, dict) else getattr(call, "args", None)
        decoded = decode_json_argument(args, label="semantic review tool arguments")
        if not isinstance(decoded, dict):
            raise ValueError("semantic review tool arguments must be an object")
        return decoded
    raise ValueError(f"semantic review response did not call {_TOOL_NAME}")


def _record_submission_call(
    *,
    module_root: Path,
    run_id: str,
    args: dict[str, Any],
    limits: dict[str, int],
    review_id: str,
    review_kind: ReviewKind,
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
    safe_data = {
        "tool": _TOOL_NAME,
        "tool_call": metrics.get("tool_calls", 0),
        "review_id": review_id,
        "review_kind": review_kind,
        "argument_shape": tool_argument_shape(args),
    }
    append_event(
        module_root,
        run_id,
        event_type="tool_end",
        message="LLM review передало структурированный результат",
        data=safe_data,
    )


def _unique_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
