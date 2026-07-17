from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.core.auth.dependencies import require_user
from backend.app.state import AppState, get_state
from backend.modules.demo_links.service import read_hello_summary

router = APIRouter(tags=["demo-links"])


@router.get("/info")
def info(
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    if not state.workspaces.user_can_access(user, workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace unavailable")
    return {
        "module": "demo_links",
        "workspace_id": workspace_id,
        "hello_summary": read_hello_summary(state, workspace_id),
    }
