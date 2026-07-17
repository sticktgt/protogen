from __future__ import annotations

from dataclasses import dataclass

from backend.app.core.config.reader import ConfigReader
from backend.app.core.modules.catalog import ModuleCatalog
from backend.app.core.users.service import UserService
from backend.app.core.workspaces.service import WorkspaceService


@dataclass
class AppState:
    config: ConfigReader
    users: UserService
    workspaces: WorkspaceService
    modules: ModuleCatalog


_STATE: AppState | None = None


def set_state(state: AppState) -> None:
    global _STATE
    _STATE = state


def get_state() -> AppState:
    if _STATE is None:
        raise RuntimeError("Application state is not initialized")
    return _STATE
