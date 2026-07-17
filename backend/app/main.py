from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.app.core.admin.routes import router as admin_router
from backend.app.core.auth.context_routes import router as context_router
from backend.app.core.auth.routes import router as auth_router
from backend.app.core.config.reader import ConfigReader
from backend.app.core.config.routes import router as config_router
from backend.app.core.modules.catalog import ModuleCatalog
from backend.app.core.modules.docs_routes import router as docs_router
from backend.app.core.modules.routes import router as modules_router
from backend.app.core.users.routes import router as users_router
from backend.app.core.users.service import UserService
from backend.app.core.workspaces.routes import router as workspaces_router
from backend.app.core.workspaces.service import WorkspaceService
from backend.app.state import AppState, set_state

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_CONFIG = Path(os.environ.get("APP_CONFIG", "config/app.yaml"))


def create_app() -> FastAPI:
    config = ConfigReader(PROJECT_ROOT, APP_CONFIG)
    users = UserService(config)
    workspaces = WorkspaceService(config)
    modules = ModuleCatalog(config)
    state = AppState(config=config, users=users, workspaces=workspaces, modules=modules)
    set_state(state)

    app = FastAPI(title=config.app_config["app"]["name"])
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(context_router)
    app.include_router(users_router)
    app.include_router(workspaces_router)
    app.include_router(modules_router)
    app.include_router(config_router)
    app.include_router(docs_router)
    modules.include_backend_routers(app)

    frontend_dir = config.resolve_project_path(config.app_config["paths"]["frontend_dir"])
    app.mount("/base", StaticFiles(directory=frontend_dir / "base"), name="base")
    app.mount("/modules", StaticFiles(directory=frontend_dir / "modules"), name="frontend-modules")

    @app.get("/")
    def root():
        default_page = config.app_config["ui"]["default_page"]
        return FileResponse(frontend_dir / default_page)

    @app.get("/login")
    def login_page():
        login_target = config.app_config["ui"]["login_page"]
        return FileResponse(frontend_dir / login_target)

    return app


app = create_app()
