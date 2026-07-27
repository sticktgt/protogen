from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_diagnostics import build_diagnostics_archive
from backend.modules.ui_schema.agent_events import append_event
from backend.modules.ui_schema.agent_execution import (
    record_cancellation,
    record_failure,
    record_limit_stop,
    validate_with_retry,
    validation_retries,
)
from backend.modules.ui_schema.agent_factory import create_ui_schema_agent
from backend.modules.ui_schema.agent_limits import execution_limits
from backend.modules.ui_schema.agent_monitor import (
    AgentRunCancellation,
    AgentRunCompleted,
    AgentRunStopped,
    create_run_callback,
)
from backend.modules.ui_schema.agent_prompts import load_prompt, render_run_prompt
from backend.modules.ui_schema.agent_report import ensure_agent_report
from backend.modules.ui_schema.agent_preview import finalize_preview
from backend.modules.ui_schema.agent_validation_display import validation_errors_for_ui
from backend.modules.ui_schema.agent_runs import (
    get_run,
    is_cancelled,
    run_root,
    update_run,
)
from backend.modules.ui_schema.files import write_json

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ui-schema-agent")
_FUTURES: dict[str, Future[Any]] = {}
_FUTURES_LOCK = threading.Lock()


def submit_run(
    *,
    module_root: Path,
    run_id: str,
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
) -> None:
    future = _EXECUTOR.submit(
        _run_agent_task,
        module_root,
        run_id,
        dict(llm_settings),
        dict(agent_config),
    )
    with _FUTURES_LOCK:
        _FUTURES[run_id] = future
    future.add_done_callback(lambda _: _forget_future(run_id))


def _forget_future(run_id: str) -> None:
    with _FUTURES_LOCK:
        _FUTURES.pop(run_id, None)


def is_run_submitted(run_id: str) -> bool:
    with _FUTURES_LOCK:
        future = _FUTURES.get(run_id)
        return future is not None and not future.done()


def _run_agent_task(
    module_root: Path,
    run_id: str,
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
) -> None:
    try:
        run = get_run(module_root, run_id)
        root = run_root(module_root, run_id)
        limits = execution_limits({"execution": run.get("execution", {})})
        callback = create_run_callback(
            module_root=module_root,
            run_id=run_id,
            limits=limits,
        )
        update_run(module_root, run_id, status="running", phase="analyzing_requirements")
        append_event(
            module_root,
            run_id,
            event_type="phase",
            message="Создание ограниченного агента и подготовка контекста",
            data={"phase": "analyzing_requirements"},
        )
        agent = create_ui_schema_agent(
            run_path=root,
            llm_settings=llm_settings,
            agent_config=agent_config,
        )
        invocation_config = {
            "configurable": {"thread_id": run_id},
            "recursion_limit": limits["recursion_limit"],
            "callbacks": [callback],
            "run_name": f"ui_schema_sync_{run_id}",
            "metadata": {"workspace_id": run.get("workspace_id"), "run_id": run_id},
        }
        append_event(
            module_root,
            run_id,
            event_type="agent_start",
            message="Агент начал анализ требований и изменение временной схемы",
        )
        try:
            response = agent.invoke(
                {
                    "messages": [
                        {"role": "user", "content": render_run_prompt(agent_config, run)}
                    ]
                },
                config=invocation_config,
            )
        except AgentRunCompleted as exc:
            response = {}
            append_event(
                module_root,
                run_id,
                event_type="agent_completed",
                message=str(exc),
            )
        completion_file = root / "result" / "agent_completion.json"
        if not completion_file.is_file():
            append_event(
                module_root,
                run_id,
                event_type="finish_missing",
                level="warning",
                message=(
                    "Агент завершил основной вызов без отметки успешной проверки; "
                    "backend продолжит обязательную структурную проверку"
                ),
            )
        if is_cancelled(module_root, run_id):
            raise AgentRunCancellation("Задача отменена пользователем")

        append_event(
            module_root,
            run_id,
            event_type="agent_result",
            message="Агент завершил основную обработку, начинается проверка результата",
        )
        ensure_agent_report(root, response)
        validation = validate_with_retry(
            agent=agent,
            root=root,
            module_root=module_root,
            run_id=run_id,
            retries=validation_retries(run),
            invocation_config=invocation_config,
            correction_prompt=load_prompt(agent_config, "correction"),
        )
        write_json(root / "result" / "validation.json", validation)
        if not validation["valid"]:
            append_event(
                module_root,
                run_id,
                event_type="validation_failed",
                level="error",
                message=f"Структурная проверка не пройдена: ошибок {len(validation['errors'])}",
            )
            update_run(
                module_root,
                run_id,
                status="failed",
                phase="validating",
                validation_errors=validation_errors_for_ui(validation["errors"]),
                validation_error_count=len(validation["errors"]),
                validation_warnings=validation.get("warnings", []),
            )
            build_diagnostics_archive(module_root, run_id)
            return

        if is_cancelled(module_root, run_id):
            raise AgentRunCancellation("Задача отменена пользователем")
        finalize_preview(module_root, run_id, validation)
    except AgentRunCancellation as exc:
        record_cancellation(module_root, run_id, exc)
    except AgentRunStopped as exc:
        record_limit_stop(module_root, run_id, exc)
    except Exception as exc:
        record_failure(module_root, run_id, exc)

