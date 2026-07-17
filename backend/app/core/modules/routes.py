from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.auth.dependencies import require_user
from backend.app.state import AppState, get_state

router = APIRouter(prefix="/api/modules", tags=["core-modules"])


@router.get("")
def get_modules(user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    return {"modules": state.modules.enabled_modules()}


@router.get("/menu")
def get_menu(user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    return {"menu": state.modules.menu()}


@router.get("/pages")
def get_pages(user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    return {"pages": state.modules.pages()}


@router.get("/pages/{page_id:path}")
def get_page(page_id: str, user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    for page in state.modules.pages():
        if page["id"] == page_id:
            return {"page": page}
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
