from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException, Request, status

from backend.app.core.auth.session import SessionSigner
from backend.app.state import AppState, get_state


def get_cookie_name(state: AppState) -> str:
    return state.config.app_config["auth"]["session_cookie_name"]


def get_signer(state: AppState) -> SessionSigner:
    auth_config = state.config.app_config["auth"]
    return SessionSigner(
        secret_key=auth_config["secret_key"],
        ttl_minutes=int(auth_config["session_ttl_minutes"]),
    )


def require_user(request: Request, state: AppState = Depends(get_state)) -> dict:
    cookie_name = get_cookie_name(state)
    token = request.cookies.get(cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = get_signer(state).unsign(token)
    if not payload or "username" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    user = state.users.get_user(payload["username"])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
