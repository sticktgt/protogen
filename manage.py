from __future__ import annotations

import argparse
import getpass
import os
import subprocess
import sys
from pathlib import Path

import uvicorn

from backend.app.core.config.reader import ConfigReader
from backend.app.core.modules.catalog import ModuleCatalog
from backend.app.core.users.service import UserService
from backend.app.core.workspaces.service import WorkspaceService

ROOT = Path(__file__).resolve().parent
APP_CONFIG = Path(os.environ.get("APP_CONFIG", "config/app.yaml"))


def build_services():
    config = ConfigReader(ROOT, APP_CONFIG)
    return config, UserService(config), WorkspaceService(config), ModuleCatalog(config)


def run_app(_args):
    config, *_ = build_services()
    server = config.app_config["server"]
    uvicorn.run(
        "backend.app.main:app",
        host=server["host"],
        port=int(server["port"]),
        reload=False,
    )


def create_user(args):
    _config, users, _workspaces, _modules = build_services()
    password = args.password or getpass.getpass("Password: ")
    users.create_user(args.username, password, args.display_name, is_admin=args.admin)
    print(f"Created user: {args.username}")


def create_workspace(args):
    _config, users, workspaces, modules = build_services()
    if not users.get_user(args.username):
        raise SystemExit(f"User not found: {args.username}")
    workspace = workspaces.create_workspace(
        username=args.username,
        name=args.name,
        description=args.description or "",
        modules=modules.enabled_modules(),
    )
    users.add_owned_workspace(args.username, workspace["id"])
    users.set_current_workspace(args.username, workspace["id"])
    print(f"Created workspace: {workspace['id']}")


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    run_parser = commands.add_parser("run")
    run_parser.set_defaults(func=run_app)

    user_parser = commands.add_parser("create-user")
    user_parser.add_argument("username")
    user_parser.add_argument("--display-name")
    user_parser.add_argument("--password")
    user_parser.add_argument("--admin", action="store_true")
    user_parser.set_defaults(func=create_user)

    workspace_parser = commands.add_parser("create-workspace")
    workspace_parser.add_argument("username")
    workspace_parser.add_argument("name")
    workspace_parser.add_argument("--description", default="")
    workspace_parser.set_defaults(func=create_workspace)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
