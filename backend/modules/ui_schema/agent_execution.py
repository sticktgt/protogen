from __future__ import annotations

import logging
import traceback
from pathlib import Path
from typing import Any
from copy import deepcopy

from backend.modules.ui_schema.agent_diagnostics import build_diagnostics_archive
from backend.modules.ui_schema.agent_events import append_event
from backend.modules.ui_schema.agent_paths import run_root
from backend.modules.ui_schema.agent_monitor import AgentRunCompleted
from backend.modules.ui_schema.agent_report import ensure_agent_report
from backend.modules.ui_schema.agent_completion import validate_agent_working_schema
from backend.modules.ui_schema.agent_preview import finalize_preview
from backend.modules.ui_schema.agent_runs import clear_active_run, is_cancelled, update_run
from backend.modules.ui_schema.agent_validation_display import validation_errors_for_ui
from backend.modules.ui_schema.agent_validation_history import record_validation_attempt
from backend.modules.ui_schema.files import read_json, write_json

_LOGGER = logging.getLogger(__name__)


def validate_with_retry(
    *,
    agent,
    root: Path,
    module_root: Path,
    run_id: str,
    retries: int,
    invocation_config: dict[str, Any],
    correction_prompt: str,
) -> dict[str, Any]:
    update_run(module_root, run_id, phase="validating")
    append_event(
        module_root,
        run_id,
        event_type="validation_start",
        message="Запущена структурная проверка временной UI-схемы",
    )
    validation = validate_agent_working_schema(root)
    record_validation_attempt(root, validation, source="backend_post_run")
    for retry_index in range(retries):
        if validation["valid"] or is_cancelled(module_root, run_id):
            break
        write_json(root / "result" / "validation_errors.json", validation)
        append_event(
            module_root,
            run_id,
            event_type="validation_retry",
            level="warning",
            message=(
                f"Обнаружено ошибок: {len(validation['errors'])}. "
                f"Автоматическая попытка исправления {retry_index + 1} из {retries}"
            ),
        )
        (root / "result" / "agent_completion.json").unlink(missing_ok=True)
        correction_config = deepcopy(invocation_config)
        configurable = dict(correction_config.get("configurable", {}))
        # MemorySaver considers a completed thread finished. A fresh thread is
        # required for each automatic correction attempt.
        configurable["thread_id"] = f"{run_id}_validation_{retry_index + 1}"
        correction_config["configurable"] = configurable
        correction_config["run_name"] = f"ui_schema_validation_fix_{run_id}_{retry_index + 1}"
        correction_message = (
            correction_prompt.rstrip()
            + "\n\nТекущий список ошибок валидации:\n"
            + "\n".join(f"- {item}" for item in validation.get("errors", []))
        )
        try:
            response = agent.invoke(
                {"messages": [{"role": "user", "content": correction_message}]},
                config=correction_config,
            )
        except AgentRunCompleted as exc:
            response = {}
            append_event(
                module_root,
                run_id,
                event_type="validation_correction_completed",
                message=str(exc),
            )
        ensure_agent_report(root, response)
        validation = validate_agent_working_schema(root)
        record_validation_attempt(
            root,
            validation,
            source="backend_retry",
            retry_index=retry_index + 1,
        )
        if not (root / "result" / "agent_completion.json").is_file():
            append_event(
                module_root,
                run_id,
                event_type="validation_finish_missing",
                level="warning",
                message=(
                    "Исправление завершилось без отметки успешной проверки; "
                    "backend выполнил проверку результата самостоятельно"
                ),
            )
    if validation["valid"]:
        append_event(
            module_root,
            run_id,
            event_type="validation_success",
            message=f"Структурная проверка пройдена, предупреждений: {len(validation.get('warnings', []))}",
        )
    return validation


def validation_retries(run: dict[str, Any]) -> int:
    value = int(run.get("config", {}).get("validation_retries", 1))
    return max(0, min(value, 2))


def record_cancellation(module_root: Path, run_id: str, exc: Exception) -> None:
    try:
        append_event(
            module_root,
            run_id,
            event_type="cancelled",
            level="warning",
            message=str(exc) or "Задача отменена пользователем",
        )
        run = update_run(module_root, run_id, status="cancelled", phase="completed", error="")
        clear_active_run(module_root, run_id)
        from backend.modules.ui_schema.agent_runs import archive_and_remove_run
        archive_and_remove_run(module_root, run_id, run=run)
    except Exception:
        pass


def record_limit_stop(module_root: Path, run_id: str, exc: Exception) -> None:
    try:
        if not is_cancelled(module_root, run_id):
            append_event(
                module_root,
                run_id,
                event_type="limit_reached",
                level="error",
                message=str(exc),
            )
            validation = _validation_at_stop(module_root, run_id)
            if validation.get("valid"):
                append_event(
                    module_root,
                    run_id,
                    event_type="limit_boundary_valid",
                    level="warning",
                    message=(
                        "Лимит достигнут, но локальная нормализация и проверка уже дали "
                        "валидный результат; формируется preview без нового вызова LLM"
                    ),
                )
                finalize_preview(
                    module_root,
                    run_id,
                    validation,
                    event_message=(
                        "Результат прошёл локальную проверку на границе лимита; "
                        "формируется preview"
                    ),
                )
                return
            errors = list(validation.get("errors", []))
            message = str(exc)
            if errors:
                message += f". На момент остановки осталось ошибок валидации: {len(errors)}"
            update_run(
                module_root,
                run_id,
                status="failed",
                phase="stopped_by_limit",
                error=message,
                stop_reason="limit",
                validation_errors=validation_errors_for_ui(errors),
                validation_error_count=len(errors),
                validation_warnings=validation.get("warnings", []),
            )
            _build_diagnostics_safely(module_root, run_id)
    except Exception:
        pass


def record_failure(module_root: Path, run_id: str, exc: Exception) -> None:
    try:
        if not is_cancelled(module_root, run_id):
            message, phase = _friendly_failure(exc)
            _LOGGER.error(
                "[ui_schema_agent][%s] Unhandled agent run error",
                run_id,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            result_root = run_root(module_root, run_id) / "result"
            write_json(
                result_root / "error.json",
                {
                    "error_type": exc.__class__.__name__,
                    "message": message,
                    "phase": phase,
                },
            )
            (result_root / "traceback.txt").write_text(
                "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
                encoding="utf-8",
            )
            append_event(
                module_root,
                run_id,
                event_type="run_failed",
                level="error",
                message=f"Задача завершилась ошибкой: {message}",
                data={"error_type": exc.__class__.__name__, "phase": phase},
            )
            update_run(
                module_root,
                run_id,
                status="failed",
                phase=phase,
                error=message,
                validation_errors=[],
                validation_error_count=0,
            )
            _build_diagnostics_safely(module_root, run_id)
    except Exception:
        _LOGGER.exception(
            "[ui_schema_agent][%s] Failed to persist agent run error", run_id
        )


def _validation_at_stop(module_root: Path, run_id: str) -> dict[str, Any]:
    try:
        root = run_root(module_root, run_id)
        validation = validate_agent_working_schema(root)
        record_validation_attempt(root, validation, source="limit_boundary")
        write_json(root / "result" / "validation_preview.json", validation)
        return validation
    except Exception:
        return {"valid": False, "errors": [], "warnings": []}


def _build_diagnostics_safely(module_root: Path, run_id: str) -> None:
    try:
        build_diagnostics_archive(module_root, run_id)
    except Exception:
        _LOGGER.exception(
            "[ui_schema_agent][%s] Failed to create diagnostics archive", run_id
        )


def _friendly_failure(exc: Exception) -> tuple[str, str]:
    text = str(exc).strip() or exc.__class__.__name__
    if exc.__class__.__name__ == "GraphRecursionError" or "Recursion limit" in text:
        return (
            "Агент остановлен после слишком большого числа внутренних шагов. "
            "Повышать recursion_limit не рекомендуется: вероятен повторяющийся цикл. "
            "Проверьте журнал вызовов LLM и инструментов.",
            "stopped_by_limit",
        )
    return text[:1000], "completed"
