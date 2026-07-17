from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.core.auth.dependencies import require_user
from backend.app.state import AppState, get_state

router = APIRouter(prefix="/api/config", tags=["core-config"])


@router.get("/app")
def get_app_config(
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    return state.config.public_app_config()


@router.get("/modules/{module_id}")
def get_module_config(
    module_id: str,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    return state.config.read_module_runtime_config(module_id)
