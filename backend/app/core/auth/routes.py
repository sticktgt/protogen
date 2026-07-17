from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from backend.app.core.auth.dependencies import get_cookie_name, get_signer, require_user
from backend.app.core.users.security import verify_password
from backend.app.state import AppState, get_state

router = APIRouter(prefix="/api/auth", tags=["core-auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(payload: LoginRequest, response: Response, state: AppState = Depends(get_state)):
    user = state.users.get_user(payload.username)
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = get_signer(state).sign({"username": payload.username})
    response.set_cookie(
        key=get_cookie_name(state),
        value=token,
        httponly=True,
        samesite="lax",
        max_age=int(state.config.app_config["auth"]["session_ttl_minutes"]) * 60,
    )
    return {"user": state.users.public_user(user)}


@router.post("/logout")
def logout(response: Response, state: AppState = Depends(get_state)):
    response.delete_cookie(get_cookie_name(state))
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(require_user), state: AppState = Depends(get_state)):
    return {"user": state.users.public_user(user)}
