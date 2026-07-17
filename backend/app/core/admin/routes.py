from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.app.core.auth.dependencies import require_user
from backend.app.state import AppState, get_state

router = APIRouter(prefix="/api/admin", tags=["core-admin"])


class UserCreateRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    is_admin: bool = False


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
