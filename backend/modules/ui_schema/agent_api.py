from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.app.core.auth.dependencies import require_user
from backend.app.state import AppState, get_state
from backend.modules.ui_schema import service
from backend.modules.ui_schema.agent_diagnostics import ensure_diagnostics_archive
from backend.modules.ui_schema.agent_events import read_events
from backend.modules.ui_schema.agent_manual_review import ensure_manual_review_result
from backend.modules.ui_schema.agent_llm import (
    LlmConfigurationError,
    public_llm_settings,
    test_llm_connection,
    user_llm_settings,
)
from backend.modules.ui_schema.agent_prompts import load_prompt
from backend.modules.ui_schema.agent_requirements import (
    RequirementsSourceError,
    load_requirements_from_workspace,
)
from backend.modules.ui_schema.requirements_source import file_sha256
from backend.modules.ui_schema.agent_paths import initial_snapshot_path
from backend.modules.ui_schema.agent_runner import is_run_submitted, submit_run
from backend.modules.ui_schema.agent_runs import (
    RunConflict,
    SchemaLocked,
    apply_run,
    cancel_run,
    complete_cancellation,
    create_run,
    get_active_run,
    get_run,
    latest_snapshot,
    reject_run,
    reset_for_regeneration,
    restore_latest_snapshot,
    result_file,
)
from backend.modules.ui_schema.files import read_json

router = APIRouter(tags=["ui-schema-agent"])


class RunAction(BaseModel):
    workspace_id: str


class StartAgentRun(RunAction):
    requirements_path: str = Field(min_length=1, max_length=2048)
    user_request: str = Field(default="", max_length=10000)
    base_mode: Literal["current", "initial"] = "current"


class RegenerateRun(RunAction):
    comment: str = Field(default="", max_length=10000)


def _module_root(state: AppState, user: dict, workspace_id: str) -> Path:
    if not state.workspaces.user_can_access(user, workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace unavailable")
    return service.module_root(state, workspace_id)


def _agent_config(state: AppState) -> dict[str, Any]:
    config = state.config.read_module_runtime_config("ui_schema") or {}
    return config.get("agent", {}) if isinstance(config, dict) else {}


def _with_observability(root: Path, run: dict[str, Any]) -> dict[str, Any]:
    payload = dict(run)
    data = read_events(root, str(run.get("run_id") or ""), after=0, limit=100)
    payload["metrics"] = data.get("metrics", {})
    payload["recent_events"] = data.get("events", [])
    return payload


@router.post("/agent/llm/test")
def test_agent_llm(
    payload: RunAction,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    _module_root(state, user, payload.workspace_id)
    config = _agent_config(state)
    llm_settings = user_llm_settings(user)
    try:
        prompt = load_prompt(config, "connection_test")
        return test_llm_connection(llm_settings, config, prompt)
    except LlmConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post("/agent-runs")
def start_agent_run(
    payload: StartAgentRun,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = _module_root(state, user, payload.workspace_id)
    config = _agent_config(state)
    if config.get("enabled", True) is False:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="UI Schema agent is disabled")

    requirements_config = config.get("requirements", {})
    max_bytes = int(
        requirements_config.get(
            "max_bytes",
            config.get("requirements_file_max_bytes", 10 * 1024 * 1024),
        )
    )
    try:
        requirements_data, source_file, source_path = load_requirements_from_workspace(
            module_root=root,
            workspace_relative_path=payload.requirements_path,
            max_bytes=max_bytes,
        )
    except RequirementsSourceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if source_path == "ui_schema/requirements.json":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Legacy-файл ui_schema/requirements.json нельзя назначить новым каноническим источником, "
                "поскольку он удаляется после принятия синхронизации. Укажите файл модуля требований."
            ),
        )

    llm_settings = user_llm_settings(user)
    try:
        llm_public = public_llm_settings(llm_settings, config)
    except LlmConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        run = create_run(
            module_root=root,
            workspace_id=payload.workspace_id,
            requirements_data=requirements_data,
            requirements_file_name=source_file.name,
            requirements_source_path=source_path,
            requirements_source_sha256=file_sha256(source_file),
            user_request=payload.user_request,
            base_mode=payload.base_mode,
            llm_public=llm_public,
            config=config,
        )
    except RunConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "run_id": exc.run.get("run_id")},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    submit_run(
        module_root=root,
        run_id=run["run_id"],
        llm_settings=llm_settings,
        agent_config=config,
    )
    return run


@router.get("/agent-runs/active")
def read_active_agent_run(
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = _module_root(state, user, workspace_id)
    run = get_active_run(root)
    return {"run": _with_observability(root, run) if run else None}


@router.get("/agent-runs/{run_id}")
def read_agent_run(
    run_id: str,
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = _module_root(state, user, workspace_id)
    try:
        return _with_observability(root, get_run(root, run_id))
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/agent-runs/{run_id}/events")
def read_agent_events(
    run_id: str,
    workspace_id: str = Query(...),
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = _module_root(state, user, workspace_id)
    try:
        get_run(root, run_id)
        return read_events(root, run_id, after=after, limit=limit)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/agent-runs/{run_id}/diagnostics")
def download_agent_diagnostics(
    run_id: str,
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = _module_root(state, user, workspace_id)
    try:
        get_run(root, run_id)
        archive = ensure_diagnostics_archive(root, run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return FileResponse(
        path=archive,
        media_type="application/zip",
        filename=f"ui-schema-agent-{run_id}-diagnostics.zip",
    )


@router.get("/agent-runs/{run_id}/changes")
def read_agent_changes(
    run_id: str,
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = _module_root(state, user, workspace_id)
    path = result_file(root, run_id, "changes.json")
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change report is not ready")
    payload = read_json(path, {})
    payload["file_diff"] = read_json(result_file(root, run_id, "file_diff.json"), {})
    payload["manual_review"] = ensure_manual_review_result(
        result_file(root, run_id, "manual_review.json").parent.parent
    )
    return payload


@router.get("/agent-runs/{run_id}/requirements-ui-result")
def read_requirements_ui_result(
    run_id: str,
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = _module_root(state, user, workspace_id)
    path = result_file(root, run_id, "requirements_ui_result.json")
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirements UI result is not ready")
    return read_json(path, {})


@router.post("/agent-runs/{run_id}/regenerate")
def regenerate_agent_run(
    run_id: str,
    payload: RegenerateRun,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = _module_root(state, user, payload.workspace_id)
    config = _agent_config(state)
    llm_settings = user_llm_settings(user)
    try:
        public_llm_settings(llm_settings, config)
    except LlmConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    try:
        existing = get_run(root, run_id)
        max_bytes = int(config.get("requirements", {}).get("max_bytes", 10 * 1024 * 1024))
        requirements_data, source_file, _ = load_requirements_from_workspace(
            module_root=root,
            workspace_relative_path=str(existing.get("requirements_source_path") or ""),
            max_bytes=max_bytes,
        )
        run = reset_for_regeneration(
            root,
            run_id,
            payload.comment,
            config=config,
            requirements_data=requirements_data,
            requirements_source_sha256=file_sha256(source_file),
        )
    except (FileNotFoundError, ValueError, RequirementsSourceError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    submit_run(
        module_root=root,
        run_id=run_id,
        llm_settings=llm_settings,
        agent_config=config,
    )
    return run


@router.post("/agent-runs/{run_id}/apply")
def apply_agent_run(
    run_id: str,
    payload: RunAction,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = _module_root(state, user, payload.workspace_id)
    config = _agent_config(state)
    keep_last = int(config.get("snapshots", {}).get("keep_last", 10))
    try:
        return apply_run(
            root,
            run_id,
            keep_last=keep_last,
            requirements_max_bytes=int(
                config.get("requirements", {}).get("max_bytes", 10 * 1024 * 1024)
            ),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/agent-runs/{run_id}/reject")
def reject_agent_run(
    run_id: str,
    payload: RunAction,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = _module_root(state, user, payload.workspace_id)
    try:
        return reject_run(root, run_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/agent-runs/{run_id}/cancel")
def cancel_agent_run(
    run_id: str,
    payload: RunAction,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = _module_root(state, user, payload.workspace_id)
    try:
        run = cancel_run(root, run_id)
        if not is_run_submitted(run_id):
            return complete_cancellation(
                root,
                run_id,
                message="Задача отменена. Активный worker не найден, возможно backend был перезапущен.",
            )
        return run
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/history/latest")
def read_latest_history(
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = _module_root(state, user, workspace_id)
    snapshot = latest_snapshot(root)
    if snapshot:
        snapshot = {key: value for key, value in snapshot.items() if key != "path"}
    return {
        "snapshot": snapshot,
        "initial_snapshot_available": initial_snapshot_path(root).is_file(),
    }


@router.post("/history/restore-latest")
def restore_latest_history(
    payload: RunAction,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = _module_root(state, user, payload.workspace_id)
    try:
        snapshot = restore_latest_snapshot(root)
    except SchemaLocked as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "run_id": exc.run.get("run_id")},
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"restored": True, "snapshot": snapshot}


@router.get("/exports/requirements-ui/{run_id}")
def read_requirements_ui_export(
    run_id: str,
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    root = _module_root(state, user, workspace_id)
    path = root / "exports" / "requirements_ui" / f"{run_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirements UI export not found")
    return read_json(path, {})
