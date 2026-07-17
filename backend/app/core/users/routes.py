from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.app.core.auth.dependencies import require_user
from backend.app.state import AppState, get_state

router = APIRouter(prefix="/api/users", tags=["core-users"])


class UserSettingsUpdate(BaseModel):
    settings: dict[str, Any]


@router.get("/me/settings")
def get_my_settings(user: dict = Depends(require_user)):
    return {"settings": user.get("settings", {})}


@router.put("/me/settings")
def update_my_settings(
    payload: UserSettingsUpdate,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    settings = state.users.update_settings(user["username"], payload.settings)
    return {"settings": settings}
