from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.core.config.reader import ConfigReader
from backend.app.core.users.security import hash_password


class UserService:
    def __init__(self, config: ConfigReader):
        self.config = config
        users_dir = config.app_config["paths"]["users_dir"]
        self.users_dir = config.resolve_project_path(users_dir)
        self.users_dir.mkdir(parents=True, exist_ok=True)

    def user_path(self, username: str) -> Path:
        safe_username = username.strip().replace("/", "_").replace("\\", "_")
        return self.users_dir / f"{safe_username}.yaml"

    def get_user(self, username: str) -> dict[str, Any] | None:
        path = self.user_path(username)
        if not path.exists():
            return None
        return self.config.read_yaml(path)

    def save_user(self, user: dict[str, Any]) -> None:
        self.config.write_yaml(self.user_path(user["username"]), user)

    def create_user(
        self,
        username: str,
        password: str,
        display_name: str | None = None,
        is_admin: bool = False,
    ) -> dict[str, Any]:
        user = {
            "username": username,
            "display_name": display_name or username,
            "password_hash": hash_password(password),
            "is_admin": is_admin,
            "current_workspace_id": None,
            "settings": {},
            "workspaces": {"owned": [], "shared": []},
        }
        self.save_user(user)
        return user

    def public_user(self, user: dict[str, Any]) -> dict[str, Any]:
        return {
            "username": user.get("username"),
            "display_name": user.get("display_name"),
            "settings": user.get("settings", {}),
            "current_workspace_id": user.get("current_workspace_id"),
            "workspaces": user.get("workspaces", {"owned": [], "shared": []}),
            "is_admin": bool(user.get("is_admin", False)),
        }

    def list_public_users(self) -> list[dict[str, Any]]:
        users = []
        for path in sorted(self.users_dir.glob("*.yaml")):
            user = self.config.read_yaml(path)
            users.append(self.public_user(user))
        return users

    def set_current_workspace(self, username: str, workspace_id: str) -> None:
        user = self.get_user(username)
        if not user:
            return
        user["current_workspace_id"] = workspace_id
        self.save_user(user)

    def update_settings(self, username: str, settings: dict[str, Any]) -> dict[str, Any]:
        user = self.get_user(username)
        if not user:
            raise ValueError("User not found")
        user["settings"] = settings
        self.save_user(user)
        return settings

    def update_user_account(
        self,
        username: str,
        display_name: str | None = None,
        password: str | None = None,
    ) -> dict[str, Any]:
        user = self.get_user(username)
        if not user:
            raise ValueError("User not found")
        if display_name is not None:
            cleaned_name = display_name.strip()
            user["display_name"] = cleaned_name or username
        if password:
            user["password_hash"] = hash_password(password)
        self.save_user(user)
        return user

    def add_owned_workspace(self, username: str, workspace_id: str) -> None:
        user = self.get_user(username)
        if not user:
            raise ValueError("User not found")
        workspaces = user.setdefault("workspaces", {"owned": [], "shared": []})
        owned = workspaces.setdefault("owned", [])
        if workspace_id not in owned:
            owned.append(workspace_id)
        if not user.get("current_workspace_id"):
            user["current_workspace_id"] = workspace_id
        self.save_user(user)

    def set_shared_workspaces(self, username: str, workspace_ids: list[str]) -> dict[str, Any]:
        user = self.get_user(username)
        if not user:
            raise ValueError("User not found")
        workspaces = user.setdefault("workspaces", {"owned": [], "shared": []})
        owned = set(workspaces.setdefault("owned", []))
        shared = []
        for workspace_id in workspace_ids:
            if workspace_id in owned or workspace_id in shared:
                continue
            shared.append(workspace_id)
        workspaces["shared"] = shared
        if user.get("current_workspace_id") not in owned and user.get("current_workspace_id") not in shared:
            user["current_workspace_id"] = self._first_accessible_workspace(user)
        self.save_user(user)
        return user

    def remove_workspace_from_all(self, workspace_id: str) -> None:
        for path in sorted(self.users_dir.glob("*.yaml")):
            user = self.config.read_yaml(path)
            workspaces = user.setdefault("workspaces", {"owned": [], "shared": []})
            changed = False
            for access_type in ("owned", "shared"):
                items = workspaces.setdefault(access_type, [])
                if workspace_id in items:
                    workspaces[access_type] = [item for item in items if item != workspace_id]
                    changed = True
            if user.get("current_workspace_id") == workspace_id:
                user["current_workspace_id"] = self._first_accessible_workspace(user)
                changed = True
            if changed:
                self.save_user(user)

    def _first_accessible_workspace(self, user: dict[str, Any]) -> str | None:
        workspaces = user.get("workspaces", {})
        for access_type in ("owned", "shared"):
            items = workspaces.get(access_type, [])
            if items:
                return items[0]
        return None
