from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.core.auth.dependencies import require_user
from backend.app.state import AppState, get_state

router = APIRouter(prefix="/api/admin", tags=["core-admin"])


class UserCreateRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    is_admin: bool = False


class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    password: str | None = None


class SharedWorkspacesUpdateRequest(BaseModel):
    workspace_ids: list[str] = Field(default_factory=list)


class AppConfigUpdateRequest(BaseModel):
    config: dict[str, Any]


def require_admin(user: dict = Depends(require_user)) -> dict:
    if not user.get("is_admin", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


@router.get("/users")
def list_users(
    admin: dict = Depends(require_admin),
    state: AppState = Depends(get_state),
):
    return {"users": state.users.list_public_users()}


@router.post("/users")
def create_user(
    payload: UserCreateRequest,
    admin: dict = Depends(require_admin),
    state: AppState = Depends(get_state),
):
    if state.users.get_user(payload.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")
    user = state.users.create_user(
        username=payload.username,
        password=payload.password,
        display_name=payload.display_name,
        is_admin=payload.is_admin,
    )
    return {"user": state.users.public_user(user)}


@router.put("/users/{username}")
def update_user(
    username: str,
    payload: UserUpdateRequest,
    admin: dict = Depends(require_admin),
    state: AppState = Depends(get_state),
):
    try:
        user = state.users.update_user_account(
            username=username,
            display_name=payload.display_name,
            password=payload.password,
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"user": state.users.public_user(user)}


@router.get("/workspace-access")
def get_workspace_access(
    admin: dict = Depends(require_admin),
    state: AppState = Depends(get_state),
):
    return {
        "users": state.users.list_public_users(),
        "workspaces": state.workspaces.list_all(),
    }


@router.put("/users/{username}/shared-workspaces")
def update_shared_workspaces(
    username: str,
    payload: SharedWorkspacesUpdateRequest,
    admin: dict = Depends(require_admin),
    state: AppState = Depends(get_state),
):
    if not state.users.get_user(username):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    available_ids = {workspace["id"] for workspace in state.workspaces.list_all()}
    unknown = [workspace_id for workspace_id in payload.workspace_ids if workspace_id not in available_ids]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown workspace: {', '.join(unknown)}",
        )
    user = state.users.set_shared_workspaces(username, payload.workspace_ids)
    return {"user": state.users.public_user(user)}


@router.delete("/workspaces/{workspace_id}")
def delete_workspace(
    workspace_id: str,
    admin: dict = Depends(require_admin),
    state: AppState = Depends(get_state),
):
    try:
        result = state.workspaces.archive_and_delete_workspace(workspace_id)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    state.users.remove_workspace_from_all(workspace_id)
    return {
        "ok": True,
        "workspace_id": workspace_id,
        "archive": result["archive"],
    }


@router.get("/app-config")
def get_app_config(
    admin: dict = Depends(require_admin),
    state: AppState = Depends(get_state),
):
    return {"config": state.config.app_config}


@router.put("/app-config")
def update_app_config(
    payload: AppConfigUpdateRequest,
    admin: dict = Depends(require_admin),
    state: AppState = Depends(get_state),
):
    state.config.write_app_config(payload.config)
    return {
        "ok": True,
        "note": "Config file was saved. Restart the application to apply startup-level changes.",
    }
