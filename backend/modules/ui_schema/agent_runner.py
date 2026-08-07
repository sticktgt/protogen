from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_completion import validate_agent_working_schema
from backend.modules.ui_schema.agent_diagnostics import build_diagnostics_archive
from backend.modules.ui_schema.agent_events import append_event
from backend.modules.ui_schema.agent_execution import (
    record_cancellation,
    record_failure,
    record_limit_stop,
)
from backend.modules.ui_schema.agent_limits import execution_limits
from backend.modules.ui_schema.agent_monitor import (
    AgentRunCancellation,
    AgentRunStopped,
    create_run_callback,
)
from backend.modules.ui_schema.agent_pipeline import run_managed_pipeline
from backend.modules.ui_schema.agent_preview import finalize_preview
from backend.modules.ui_schema.agent_runs import (
    get_run,
    is_cancelled,
    run_root,
    update_run,
)
from backend.modules.ui_schema.agent_validation_display import validation_errors_for_ui
from backend.modules.ui_schema.agent_validation_history import record_validation_attempt
from backend.modules.ui_schema.files import read_json, write_json

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
            event_type="pipeline_start",
            message="Запущена управляемая синхронизация UI-схемы",
            data={"pipeline_version": 2},
        )
        run_managed_pipeline(
            module_root=module_root,
            run_id=run_id,
            run_path=root,
            llm_settings=llm_settings,
            agent_config=agent_config,
            callback=callback,
        )
        if is_cancelled(module_root, run_id):
            raise AgentRunCancellation("Задача отменена пользователем")

        update_run(module_root, run_id, phase="validating")
        append_event(
            module_root,
            run_id,
            event_type="validation_start",
            message="Запущена финальная структурная проверка временной UI-схемы",
        )
        validation = validate_agent_working_schema(root)
        record_validation_attempt(root, validation, source="pipeline_v2_final")
        write_json(root / "result" / "validation.json", validation)
        if not validation.get("valid"):
            errors = list(validation.get("errors", []))
            append_event(
                module_root,
                run_id,
                event_type="validation_failed",
                level="error",
                message=f"Структурная проверка не пройдена: ошибок {len(errors)}",
            )
            update_run(
                module_root,
                run_id,
                status="failed",
                phase="validating",
                validation_errors=validation_errors_for_ui(errors),
                validation_error_count=len(errors),
                validation_warnings=validation.get("warnings", []),
            )
            build_diagnostics_archive(module_root, run_id)
            return

        state_path = root / "result" / "pipeline_state.json"
        pipeline_state = read_json(state_path, {})
        if pipeline_state.get("version") == 2:
            write_json(
                state_path,
                {**pipeline_state, "status": "completed", "phase": "completed"},
            )
        finalize_preview(module_root, run_id, validation)
    except AgentRunCancellation as exc:
        record_cancellation(module_root, run_id, exc)
    except AgentRunStopped as exc:
        record_limit_stop(module_root, run_id, exc)
    except Exception as exc:
        record_failure(module_root, run_id, exc)
