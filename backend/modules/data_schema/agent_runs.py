from __future__ import annotations

import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.modules.data_schema.agent_context import write_compact_agent_inputs
from backend.modules.data_schema.agent_events import append_event, initialize_observability
from backend.modules.data_schema.agent_limits import execution_limits
from backend.modules.data_schema.agent_paths import (
    ACTIVE_STATUSES,
    active_run_path,
    initial_snapshot_path,
    legacy_completed_run_file,
    now_iso,
    run_file,
    run_root,
)
from backend.modules.data_schema.agent_runtime_layout import (
    compact_terminal_run_directory,
    ensure_runtime_layout,
)
from backend.modules.data_schema.agent_prompts import (
    load_prompt,
    prompt_files,
    reference_files,
    render_run_prompt,
)
from backend.modules.data_schema.agent_snapshots import (
    ensure_initial_snapshot,
    extract_zip,
    latest_snapshot,
    restore_latest_snapshot,
)
from backend.modules.data_schema.files import read_json, write_json
from backend.modules.data_schema.requirements_source import source_reference

PROCESS_LOCK = threading.RLock()


def create_run(
    *,
    module_root: Path,
    workspace_id: str,
    requirements_data: dict[str, Any],
    requirements_file_name: str,
    requirements_source_path: str,
    requirements_source_sha256: str,
    user_request: str,
    base_mode: str,
    llm_public: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    if base_mode not in {"current", "initial"}:
        raise ValueError("base_mode must be 'current' or 'initial'")

    with PROCESS_LOCK:
        ensure_runtime_layout(module_root)
        active = get_active_run(module_root)
        if active and active.get("status") in ACTIVE_STATUSES:
            raise RunConflict(active)
        if active:
            clear_active_run(module_root, active.get("run_id"))

        ensure_initial_snapshot(module_root)
        run_id = f"run_{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
        root = run_root(module_root, run_id)
        input_path = root / "input"
        base_path = root / "base" / "data_schema"
        working_path = root / "working" / "data_schema"
        reference_path = root / "reference"
        result_path = root / "result"
        for path in (input_path, base_path.parent, working_path.parent, reference_path, result_path):
            path.mkdir(parents=True, exist_ok=True)

        if base_mode == "initial":
            extract_zip(initial_snapshot_path(module_root), base_path)
        else:
            shutil.copytree(module_root, base_path, dirs_exist_ok=True)
        shutil.copytree(base_path, working_path, dirs_exist_ok=True)

        write_json(input_path / "requirements.json", requirements_data)
        write_json(
            working_path / "requirements_source.json",
            source_reference(requirements_source_path, sha256=requirements_source_sha256),
        )
        (working_path / "requirements.json").unlink(missing_ok=True)
        _copy_reference_files(reference_path, config)

        started_at = now_iso()
        run = {
            "run_id": run_id,
            "workspace_id": workspace_id,
            "status": "running",
            "phase": "preparing",
            "attempt": 1,
            "base_mode": base_mode,
            "requirements_file_name": requirements_file_name,
            "requirements_source_path": requirements_source_path,
            "requirements_source_sha256": requirements_source_sha256,
            "user_request": user_request.strip(),
            "regeneration_comments": [],
            "created_at": started_at,
            "started_at": started_at,
            "updated_at": started_at,
            "statistics": {},
            "agent_report": "",
            "agent_note": "",
            "validation_errors": [],
            "validation_error_count": 0,
            "validation_warnings": [],
            "config": {
                "validation_retries": int(config["validation_retries"]),
                "semantic_review": dict(config.get("semantic_review", {})),
                "domain": dict(config.get("domain", {})),
            },
            "execution": dict(config.get("execution", {})) if isinstance(config.get("execution"), dict) else {},
            "retention": dict(config.get("retention", {})) if isinstance(config.get("retention"), dict) else {},
            "llm": {
                key: value
                for key, value in dict(llm_public or {}).items()
                if key in {"provider", "model", "base_url"} and value
            },
        }
        write_json(root / "run.json", run)
        _write_task_file(root, run)
        write_compact_agent_inputs(run_root=root)
        _write_prompt_snapshots(root, run, config)
        initialize_observability(
            module_root,
            run_id,
            limits=execution_limits(config),
            started_at=started_at,
        )
        append_event(
            module_root,
            run_id,
            event_type="run_created",
            message="Задача создана, временная копия схемы данных подготовлена",
            data={"base_mode": base_mode, "requirements_source_path": requirements_source_path},
        )
        write_json(active_run_path(module_root), {"run_id": run_id, "workspace_id": workspace_id})
        return run


def get_run(module_root: Path, run_id: str) -> dict[str, Any]:
    ensure_runtime_layout(module_root)
    path = run_file(module_root, run_id)
    if path.is_file():
        return read_json(path, {})
    legacy = legacy_completed_run_file(module_root, run_id)
    if legacy.is_file():
        return read_json(legacy, {})
    raise FileNotFoundError(f"Agent run not found: {run_id}")


def update_run(module_root: Path, run_id: str, **updates: Any) -> dict[str, Any]:
    with PROCESS_LOCK:
        run = get_run(module_root, run_id)
        run.update(updates)
        run["updated_at"] = now_iso()
        write_json(run_file(module_root, run_id), run)
        return run


def get_active_run(module_root: Path) -> dict[str, Any] | None:
    pointer = read_json(active_run_path(module_root), {})
    run_id = pointer.get("run_id")
    if not isinstance(run_id, str):
        return None
    try:
        run = get_run(module_root, run_id)
    except FileNotFoundError:
        active_run_path(module_root).unlink(missing_ok=True)
        return None
    if run.get("status") not in ACTIVE_STATUSES:
        active_run_path(module_root).unlink(missing_ok=True)
        return None
    return run


def clear_active_run(module_root: Path, run_id: str | None = None) -> None:
    path = active_run_path(module_root)
    if run_id and path.is_file() and read_json(path, {}).get("run_id") != run_id:
        return
    path.unlink(missing_ok=True)


def ensure_schema_writable(module_root: Path) -> None:
    active = get_active_run(module_root)
    if active and active.get("status") in ACTIVE_STATUSES:
        raise SchemaLocked(active)


def resolve_preview_root(module_root: Path, run_id: str) -> Path:
    run = get_run(module_root, run_id)
    if run.get("status") not in {"preview_ready", "failed"}:
        raise ValueError("Preview is not available for this run")
    path = run_root(module_root, run_id) / "working" / "data_schema"
    if not path.is_dir():
        raise FileNotFoundError("Preview data schema is missing")
    return path


def reset_for_regeneration(
    module_root: Path,
    run_id: str,
    comment: str,
    *,
    config: dict[str, Any],
    requirements_data: dict[str, Any] | None = None,
    requirements_source_sha256: str | None = None,
    llm_public: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with PROCESS_LOCK:
        run = get_run(module_root, run_id)
        if run.get("status") not in {"preview_ready", "failed"}:
            raise ValueError("Only preview-ready or failed runs can be regenerated")
        root = run_root(module_root, run_id)
        if isinstance(requirements_data, dict):
            write_json(root / "input" / "requirements.json", requirements_data)
        if requirements_source_sha256:
            run["requirements_source_sha256"] = requirements_source_sha256
        working = root / "working" / "data_schema"
        result = root / "result"
        shutil.rmtree(working, ignore_errors=True)
        shutil.copytree(root / "base" / "data_schema", working)
        write_json(
            working / "requirements_source.json",
            source_reference(
                str(run.get("requirements_source_path") or ""),
                sha256=str(run.get("requirements_source_sha256") or "") or None,
            ),
        )
        (working / "requirements.json").unlink(missing_ok=True)
        shutil.rmtree(result, ignore_errors=True)
        result.mkdir(parents=True, exist_ok=True)
        comments = list(run.get("regeneration_comments") or [])
        if comment.strip():
            comments.append(comment.strip())
        attempt_started_at = now_iso()
        run.update(
            {
                "status": "running",
                "phase": "preparing",
                "attempt": int(run.get("attempt", 1)) + 1,
                "started_at": attempt_started_at,
                "regeneration_comments": comments,
                "statistics": {},
                "agent_report": "",
                "agent_note": "",
                "validation_errors": [],
                "validation_error_count": 0,
                "validation_warnings": [],
                "error": "",
                "stop_reason": "",
                "config": {
                    "validation_retries": int(config["validation_retries"]),
                    "semantic_review": dict(config.get("semantic_review", {})),
                    "domain": dict(config.get("domain", {})),
                },
                "execution": (
                    dict(config.get("execution", {}))
                    if isinstance(config.get("execution"), dict)
                    else {}
                ),
                "retention": (
                    dict(config.get("retention", {}))
                    if isinstance(config.get("retention"), dict)
                    else {}
                ),
                "llm": (
                    {
                        key: value
                        for key, value in dict(llm_public).items()
                        if key in {"provider", "model", "base_url"} and value
                    }
                    if isinstance(llm_public, dict)
                    else dict(run.get("llm") or {})
                ),
                "updated_at": now_iso(),
            }
        )
        write_json(root / "run.json", run)
        _write_task_file(root, run)
        write_compact_agent_inputs(run_root=root)
        shutil.rmtree(root / "reference", ignore_errors=True)
        (root / "reference").mkdir(parents=True, exist_ok=True)
        _copy_reference_files(root / "reference", config)
        _write_prompt_snapshots(root, run, config)
        initialize_observability(
            module_root,
            run_id,
            limits=execution_limits({"execution": run.get("execution", {})}),
            started_at=attempt_started_at,
        )
        append_event(
            module_root,
            run_id,
            event_type="regeneration_started",
            message=f"Перегенерация запущена, попытка {run.get('attempt', 1)}",
            data={"llm": dict(run.get("llm") or {})},
        )
        write_json(active_run_path(module_root), {"run_id": run_id, "workspace_id": run["workspace_id"]})
        return run


def reject_run(module_root: Path, run_id: str) -> dict[str, Any]:
    run = get_run(module_root, run_id)
    if run.get("status") not in {"preview_ready", "failed"}:
        raise ValueError("Only preview-ready or failed runs can be rejected")
    run = update_run(module_root, run_id, status="rejected", phase="completed")
    append_event(
        module_root,
        run_id,
        event_type="rejected",
        level="warning",
        message="Пользователь отклонил предложенные изменения схемы данных",
    )
    clear_active_run(module_root, run_id)
    return archive_and_remove_run(module_root, run_id, run=run)


def cancel_run(module_root: Path, run_id: str) -> dict[str, Any]:
    run = get_run(module_root, run_id)
    if run.get("status") != "running":
        raise ValueError("Only a running task can be cancelled")
    run = update_run(module_root, run_id, status="cancelling", phase="cancelling")
    append_event(
        module_root,
        run_id,
        event_type="cancellation_requested",
        level="warning",
        message="Пользователь запросил отмену. Задача остановится после текущего вызова LLM или инструмента.",
    )
    return run


def complete_cancellation(module_root: Path, run_id: str, *, message: str = "Задача отменена") -> dict[str, Any]:
    run = update_run(module_root, run_id, status="cancelled", phase="completed", error="")
    append_event(
        module_root,
        run_id,
        event_type="cancelled",
        level="warning",
        message=message,
    )
    clear_active_run(module_root, run_id)
    return archive_and_remove_run(module_root, run_id, run=run)


def is_cancelled(module_root: Path, run_id: str) -> bool:
    try:
        return get_run(module_root, run_id).get("status") in {"cancelling", "cancelled"}
    except FileNotFoundError:
        return True


def apply_run(
    module_root: Path,
    run_id: str,
    *,
    keep_last: int,
    requirements_max_bytes: int,
) -> dict[str, Any]:
    from backend.modules.data_schema.agent_apply import apply_run as apply_impl

    return apply_impl(
        module_root,
        run_id,
        keep_last=keep_last,
        requirements_max_bytes=requirements_max_bytes,
    )


def archive_and_remove_run(
    module_root: Path,
    run_id: str,
    *,
    run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Keep one compact run directory and remove its heavy working files."""
    from backend.modules.data_schema.agent_diagnostics import persist_diagnostics_archive
    from backend.modules.data_schema.agent_events import read_events

    current = dict(run or get_run(module_root, run_id))
    retention = current.get("retention", {}) if isinstance(current.get("retention"), dict) else {}
    try:
        completed_event_limit = int(retention["completed_event_limit"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "agent.retention.completed_event_limit must be configured as a positive integer"
        ) from exc
    if completed_event_limit <= 0:
        raise ValueError(
            "agent.retention.completed_event_limit must be configured as a positive integer"
        )
    observability = read_events(module_root, run_id, after=0, limit=completed_event_limit)
    archive = persist_diagnostics_archive(module_root, run_id)
    current["archived"] = True
    current["diagnostics_available"] = True
    current["diagnostics_file_name"] = archive.name
    current["metrics"] = observability.get("metrics", {})
    current["recent_events"] = observability.get("events", [])
    compact_terminal_run_directory(module_root, run_id, current)
    return current


def result_file(module_root: Path, run_id: str, name: str) -> Path:
    allowed = {
        "changes.json",
        "requirements_data_result.json",
        "agent_report.json",
        "validation.json",
    }
    if name not in allowed:
        raise ValueError("Unsupported result file")
    return run_root(module_root, run_id) / "result" / name


def _write_prompt_snapshots(root: Path, run: dict[str, Any], config: dict[str, Any]) -> None:
    prompts_target = root / "reference" / "prompts"
    prompts_target.mkdir(parents=True, exist_ok=True)
    for destination_name, source in prompt_files(config).items():
        shutil.copy2(source, prompts_target / destination_name)
    (root / "input" / "system_prompt.md").write_text(
        load_prompt(config, "system"), encoding="utf-8"
    )
    (root / "input" / "run_prompt.md").write_text(
        render_run_prompt(config, run), encoding="utf-8"
    )
    (root / "input" / "correction_prompt.md").write_text(
        load_prompt(config, "correction"), encoding="utf-8"
    )


def _write_rendered_run_prompt_from_snapshot(root: Path, run: dict[str, Any]) -> None:
    template_path = root / "reference" / "prompts" / "run.md"
    if not template_path.is_file():
        return
    template = template_path.read_text(encoding="utf-8")
    user_request = str(run.get("user_request") or "").strip()
    comments = [
        str(item).strip()
        for item in run.get("regeneration_comments", [])
        if str(item).strip()
    ]
    rendered = template.format_map(
        {
            "user_request_section": (
                f"Первоначальное указание аналитика:\n{user_request}" if user_request else ""
            ),
            "regeneration_section": (
                "Комментарии к перегенерации:\n"
                + "\n".join(f"- {item}" for item in comments)
                if comments
                else ""
            ),
        }
    ).strip()
    (root / "input" / "run_prompt.md").write_text(rendered, encoding="utf-8")


def _copy_reference_files(target: Path, config: dict[str, Any]) -> None:
    for destination_name, source in reference_files(config).items():
        shutil.copy2(source, target / destination_name)


def _write_task_file(root: Path, run: dict[str, Any]) -> None:
    write_json(
        root / "input" / "task.json",
        {
            "operation": "synchronize",
            "base_mode": run.get("base_mode", "current"),
            "user_request": run.get("user_request", ""),
            "regeneration_comments": run.get("regeneration_comments", []),
            "synchronization_context_file": "/input/synchronization_context.json",
            "requirements_file": "/input/requirements.agent.json",
            "data_schema_context_file": "/input/data_schema_context.json",
            "data_schema_path": "/working/data_schema",
            "result_path": "/result",
            "attempt": run.get("attempt", 1),
        },
    )



class RunConflict(RuntimeError):
    def __init__(self, run: dict[str, Any]):
        super().__init__("Data Schema agent run is already active")
        self.run = run


class SchemaLocked(RuntimeError):
    def __init__(self, run: dict[str, Any]):
        super().__init__("Data schema is locked by an active agent run")
        self.run = run
