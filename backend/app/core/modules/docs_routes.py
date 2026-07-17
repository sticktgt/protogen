from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.auth.dependencies import require_user
from backend.app.state import AppState, get_state

router = APIRouter(prefix="/api/docs", tags=["core-docs"])


@router.get("/openapi/{module_id}")
def get_module_openapi(
    module_id: str,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    doc = state.modules.read_doc(module_id, "api")
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API doc not found")
    return doc


@router.get("/interop/{module_id}")
def get_module_interop(
    module_id: str,
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    doc = state.modules.read_doc(module_id, "interop")
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interop doc not found")
    return doc


@router.get("/openapi")
def get_all_module_openapi(
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    return {
        "modules": {
            module["id"]: state.modules.read_doc(module["id"], "api")
            for module in state.modules.enabled_modules()
        }
    }
