from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.core.auth.dependencies import require_user
from backend.app.state import AppState, get_state
from backend.modules.demo_hello.schemas import MessageUpdate
from backend.modules.demo_hello.service import read_message, save_message

router = APIRouter(tags=["demo-hello"])


@router.get("/message")
def get_message(
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    if not state.workspaces.user_can_access(user, workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace unavailable")
    return read_message(state, workspace_id)


@router.put("/message")
def put_message(
    payload: MessageUpdate,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    if not state.workspaces.user_can_access(user, payload.workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace unavailable")
    return save_message(state, payload.workspace_id, user["username"], payload.message)
