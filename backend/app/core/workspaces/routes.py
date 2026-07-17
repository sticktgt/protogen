from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.core.auth.dependencies import require_user
from backend.app.state import AppState, get_state

router = APIRouter(prefix="/api/workspaces", tags=["core-workspaces"])


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""


@router.get("")
def list_workspaces(user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    return {
        "workspaces": state.workspaces.list_for_user(user),
        "current_workspace_id": user.get("current_workspace_id"),
    }


@router.post("")
def create_workspace(
    payload: WorkspaceCreate,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    workspace = state.workspaces.create_workspace(
        username=user["username"],
        name=payload.name,
        description=payload.description,
        modules=state.modules.enabled_modules(),
    )
    state.users.add_owned_workspace(user["username"], workspace["id"])
    state.users.set_current_workspace(user["username"], workspace["id"])
    return {"workspace": workspace, "current_workspace_id": workspace["id"]}


@router.post("/{workspace_id}/open")
def open_workspace(
    workspace_id: str,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    if not state.workspaces.user_can_access(user, workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace unavailable")
    state.users.set_current_workspace(user["username"], workspace_id)
    return {"current_workspace_id": workspace_id}


@router.get("/{workspace_id}/path")
def get_workspace_path(
    workspace_id: str,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    if not state.workspaces.user_can_access(user, workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace unavailable")
    return {
        "workspace_id": workspace_id,
        "workspace_path": state.workspaces.get_workspace_relative_path(workspace_id),
        "module_paths": {
            module["id"]: state.workspaces.module_workspace_folder(module)
            for module in state.modules.enabled_modules()
        },
    }
