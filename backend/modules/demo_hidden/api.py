from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.core.auth.dependencies import require_user
from backend.app.state import AppState, get_state
from backend.modules.demo_hidden.schemas import NoteSaveRequest
from backend.modules.demo_hidden.service import read_status, save_note

router = APIRouter(tags=["demo-hidden"])


@router.get("/status")
def status(
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    if not state.workspaces.user_can_access(user, workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace unavailable")
    return read_status(state, workspace_id)


@router.put("/note")
def update_note(
    payload: NoteSaveRequest,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    if not state.workspaces.user_can_access(user, payload.workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace unavailable")
    return save_note(state, payload.workspace_id, payload.note)
