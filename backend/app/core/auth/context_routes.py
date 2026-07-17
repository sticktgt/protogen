from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.core.auth.dependencies import require_user
from backend.app.state import AppState, get_state

router = APIRouter(prefix="/api/session", tags=["core-session"])


@router.get("/context")
def get_context(user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    current_workspace = None
    workspace_id = user.get("current_workspace_id")
    if workspace_id and state.workspaces.user_can_access(user, workspace_id):
        current_workspace = state.workspaces.read_workspace_meta(workspace_id)
    public_config = state.config.public_app_config()
    return {
        "app": public_config.get("app", {}),
        "user": state.users.public_user(user),
        "workspace": current_workspace,
        "menu": state.modules.menu(),
        "pages": state.modules.pages(),
        "api": {"base_url": "api"},
        "ui": public_config.get("ui", {}),
    }
