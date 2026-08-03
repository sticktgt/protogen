from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_diagnostics import build_diagnostics_archive
from backend.modules.data_schema.agent_events import append_event
from backend.modules.data_schema.agent_execution import (
    record_cancellation,
    record_failure,
    record_limit_stop,
    validate_with_retry,
    validation_retries,
)
from backend.modules.data_schema.agent_factory import create_data_schema_agent
from backend.modules.data_schema.agent_limits import execution_limits
from backend.modules.data_schema.agent_monitor import (
    AgentRunCancellation,
    AgentRunStopped,
    create_run_callback,
)
from backend.modules.data_schema.agent_preview import finalize_preview
from backend.modules.data_schema.agent_semantic_review import review_and_correct_semantics
from backend.modules.data_schema.agent_prompts import load_prompt, render_run_prompt
from backend.modules.data_schema.agent_report import ensure_agent_report
from backend.modules.data_schema.agent_runs import (
    get_run,
    is_cancelled,
    run_root,
    update_run,
)
from backend.modules.data_schema.agent_validation_display import validation_errors_for_ui
from backend.modules.data_schema.files import write_json

_EXECUTOR: ThreadPoolExecutor | None = None
_EXECUTOR_WORKERS: int | None = None
_EXECUTOR_LOCK = threading.Lock()
_FUTURES: dict[str, Future[Any]] = {}
_FUTURES_LOCK = threading.Lock()


def submit_run(
    *,
    module_root: Path,
    run_id: str,
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
) -> None:
    future = _executor(agent_config).submit(
        _run_agent_task,
        module_root,
        run_id,
        dict(llm_settings),
        dict(agent_config),
    )
    with _FUTURES_LOCK:
        _FUTURES[run_id] = future
    future.add_done_callback(lambda _: _forget_future(run_id))


def _executor(agent_config: dict[str, Any]) -> ThreadPoolExecutor:
    global _EXECUTOR, _EXECUTOR_WORKERS
    try:
        workers = int(agent_config["worker_pool_size"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("agent.worker_pool_size must be a positive integer") from exc
    if workers <= 0:
        raise ValueError("agent.worker_pool_size must be a positive integer")
    with _EXECUTOR_LOCK:
        if _EXECUTOR is None:
            _EXECUTOR = ThreadPoolExecutor(
                max_workers=workers,
                thread_name_prefix="data-schema-agent",
            )
            _EXECUTOR_WORKERS = workers
        elif _EXECUTOR_WORKERS != workers:
            raise ValueError(
                "agent.worker_pool_size cannot change after the agent executor starts"
            )
        return _EXECUTOR


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
        update_run(module_root, run_id, status="running", phase="synchronizing")
        append_event(
            module_root,
            run_id,
            event_type="phase",
            message="Создание логической схемы и прямой трассировки требований",
            data={"phase": "synchronizing"},
        )

        agent = create_data_schema_agent(
            module_root=module_root,
            run_id=run_id,
            run_path=root,
            llm_settings=llm_settings,
            agent_config=agent_config,
        )
        invocation_config = {
            "configurable": {"thread_id": run_id},
            "recursion_limit": limits["recursion_limit"],
            "callbacks": [callback],
            "run_name": f"data_schema_sync_{run_id}",
            "metadata": {
                "workspace_id": run.get("workspace_id"),
                "run_id": run_id,
            },
        }
        append_event(
            module_root,
            run_id,
            event_type="agent_start",
            message="Агент начал синхронизацию схемы данных",
        )
        response = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": render_run_prompt(agent_config, run),
                    }
                ]
            },
            config=invocation_config,
        )
        if is_cancelled(module_root, run_id):
            raise AgentRunCancellation("Задача отменена пользователем")

        append_event(
            module_root,
            run_id,
            event_type="agent_result",
            message="Основная синхронизация завершена, начинается техническая проверка",
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

        validation, semantic_review = review_and_correct_semantics(
            root=root,
            module_root=module_root,
            run_id=run_id,
            validation=validation,
            llm_settings=llm_settings,
            agent_config=agent_config,
        )
        write_json(root / "result" / "validation.json", validation)
        if not validation["valid"]:
            append_event(
                module_root,
                run_id,
                event_type="semantic_correction_validation_failed",
                level="error",
                message=(
                    "После смысловых исправлений остались технические ошибки: "
                    f"{len(validation['errors'])}"
                ),
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
        finalize_preview(
            module_root,
            run_id,
            validation,
            semantic_review=semantic_review,
        )
    except AgentRunCancellation as exc:
        record_cancellation(module_root, run_id, exc)
    except AgentRunStopped as exc:
        record_limit_stop(module_root, run_id, exc)
    except Exception as exc:
        record_failure(module_root, run_id, exc)
