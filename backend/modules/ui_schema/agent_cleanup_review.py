from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_cleanup_context import build_cleanup_review_context
from backend.modules.ui_schema.agent_cleanup_review_models import CleanupReviewPayload
from backend.modules.ui_schema.agent_events import append_event
from backend.modules.ui_schema.agent_llm import create_chat_model
from backend.modules.ui_schema.agent_prompts import load_prompt
from backend.modules.ui_schema.agent_tool_payloads import decode_json_argument


def cleanup_review_settings(agent_config: dict[str, Any]) -> dict[str, Any]:
    manual = agent_config.get("manual_review", {}) if isinstance(agent_config, dict) else {}
    cleanup = manual.get("cleanup_candidates", {}) if isinstance(manual, dict) else {}
    return cleanup if isinstance(cleanup, dict) else {}


def run_optional_cleanup_review(
    *,
    root: Path,
    module_root: Path,
    run_id: str,
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
    callback: Any,
) -> dict[str, Any]:
    """Run a read-only, non-blocking review that never changes the working schema."""
    settings = cleanup_review_settings(agent_config)
    if settings.get("enabled") is not True:
        return {
            "status": "disabled",
            "summary": "Проверка отключена конфигурацией.",
            "cleanup_candidates": [],
        }

    max_candidates = max(1, int(settings.get("max_candidates", 5)))
    max_context_bytes = max(1024, int(settings.get("max_context_bytes", 524288)))
    response_attempts = max(1, int(settings.get("response_attempts", 2)))
    try:
        context = build_cleanup_review_context(root, max_bytes=max_context_bytes)
        if not context.get("base_objects"):
            return {
                "status": "not_applicable",
                "summary": "В базовой схеме нет объектов для проверки ручной очистки.",
                "cleanup_candidates": [],
            }
        append_event(
            module_root,
            run_id,
            event_type="cleanup_review_start",
            message="Запущена необязательная проверка кандидатов на ручную очистку",
        )
        result = _invoke_cleanup_review(
            context=context,
            llm_settings=llm_settings,
            agent_config=agent_config,
            callback=callback,
            response_attempts=response_attempts,
            max_candidates=max_candidates,
            module_root=module_root,
            run_id=run_id,
        )
        append_event(
            module_root,
            run_id,
            event_type="cleanup_review_completed",
            message=(
                "Проверка ручной очистки завершена: "
                f"кандидатов {len(result['cleanup_candidates'])}"
            ),
        )
        return result
    except Exception as exc:
        if exc.__class__.__name__ == "AgentRunCancellation":
            raise
        warning = f"Необязательная проверка кандидатов на очистку не выполнена: {str(exc)[:500]}"
        append_event(
            module_root,
            run_id,
            event_type="cleanup_review_failed",
            level="warning",
            message=warning,
        )
        return {
            "status": "failed",
            "summary": "Проверка не выполнена; основной результат не изменён.",
            "warning": warning,
            "cleanup_candidates": [],
        }


def _invoke_cleanup_review(
    *,
    context: dict[str, Any],
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
    callback: Any,
    response_attempts: int,
    max_candidates: int,
    module_root: Path,
    run_id: str,
) -> dict[str, Any]:
    tool = _cleanup_submission_tool()
    model = create_chat_model(llm_settings, agent_config)
    bound = model.bind_tools([tool], tool_choice="required")
    prompt = load_prompt(agent_config, "cleanup_review").format(
        max_candidates=max_candidates,
        context_json=_json_text(context),
    )
    system_prompt = load_prompt(agent_config, "cleanup_review_system")
    last_error = ""
    for attempt in range(1, response_attempts + 1):
        current_prompt = prompt
        if last_error:
            current_prompt += (
                "\n\nПредыдущий ответ нарушил контракт. Исправь только формат "
                "и верни один tool call. "
                f"Ошибка: {last_error}"
            )
        invocation_config = {
            "run_name": f"ui_schema_cleanup_review_{run_id}_{attempt}",
            "metadata": {"run_id": run_id, "review_kind": "cleanup_candidates"},
        }
        if callback is not None:
            invocation_config["callbacks"] = [callback]
        response = bound.invoke(
            [("system", system_prompt), ("user", current_prompt)],
            config=invocation_config,
        )
        try:
            args = _tool_args(response)
            payload = CleanupReviewPayload.model_validate(args)
            return _normalize_payload(
                payload,
                allowed_targets=set(context.get("allowed_targets", [])),
                max_candidates=max_candidates,
            )
        except (TypeError, ValueError) as exc:
            last_error = str(exc)[:500]
            append_event(
                module_root,
                run_id,
                event_type="cleanup_review_response_rejected",
                level="warning",
                message=f"Ответ проверки очистки отклонён: {last_error}",
                data={"response_attempt": attempt},
            )
    raise RuntimeError("LLM не вернула корректный результат ручной проверки: " + last_error)


def _cleanup_submission_tool():
    try:
        from langchain_core.tools import tool
    except ImportError as exc:
        raise RuntimeError("LangChain core tools are not installed") from exc

    @tool(args_schema=CleanupReviewPayload)
    def submit_ui_schema_cleanup_review(
        summary: str,
        cleanup_candidates: list[dict[str, Any]] | None = None,
    ) -> str:
        """Передать неблокирующие рекомендации по ручной очистке UI-схемы."""
        return "принято"

    return submit_ui_schema_cleanup_review


def _tool_args(response: Any) -> dict[str, Any]:
    calls = getattr(response, "tool_calls", None)
    if calls is None and isinstance(response, dict):
        calls = response.get("tool_calls")
    if not isinstance(calls, list) or len(calls) != 1:
        raise ValueError("ожидался ровно один tool call")
    call = calls[0]
    name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
    if name != "submit_ui_schema_cleanup_review":
        raise ValueError(f"неожиданный инструмент: {name or '<unknown>'}")
    args = call.get("args") if isinstance(call, dict) else getattr(call, "args", None)
    decoded = decode_json_argument(args, label="аргументы инструмента ручной проверки")
    if not isinstance(decoded, dict):
        raise ValueError("аргументы проверки должны быть JSON-объектом")
    return decoded


def _normalize_payload(
    payload: CleanupReviewPayload,
    *,
    allowed_targets: set[str],
    max_candidates: int,
) -> dict[str, Any]:
    if len(payload.cleanup_candidates) > max_candidates:
        raise ValueError(f"получено более {max_candidates} кандидатов")
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for index, item in enumerate(payload.cleanup_candidates, start=1):
        targets = sorted({str(value).strip() for value in item.targets if str(value).strip()})
        unknown = [target for target in targets if target not in allowed_targets]
        if unknown:
            raise ValueError(
                "кандидат ссылается на неизвестные базовые объекты: "
                + ", ".join(unknown)
            )
        key = tuple(targets)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "id": f"cleanup_{index}",
                "category": item.category.strip(),
                "message": item.message.strip(),
                "recommendation": item.recommendation.strip(),
                "requirement_ids": sorted(
                    {str(value).strip() for value in item.requirement_ids if str(value).strip()}
                ),
                "targets": targets,
            }
        )
    return {
        "status": "completed",
        "summary": payload.summary.strip(),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "cleanup_candidates": candidates,
    }


def _json_text(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
