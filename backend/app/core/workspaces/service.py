from __future__ import annotations

import shutil
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from typing import Any

from backend.app.core.config.reader import ConfigReader
from backend.app.core.workspaces.paths import safe_id


class WorkspaceService:
    def __init__(self, config: ConfigReader):
        self.config = config
        root = config.app_config["paths"]["workspace_root"]
        self.workspace_root = config.resolve_project_path(root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def get_workspace_path(self, workspace_id: str) -> Path:
        return self.workspace_root / safe_id(workspace_id)

    def get_module_path(self, workspace_id: str, module_id: str) -> Path:
        return self.get_workspace_path(workspace_id) / safe_id(module_id)

    def get_module_path_for_manifest(self, workspace_id: str, module: dict[str, Any]) -> Path:
        return self.get_workspace_path(workspace_id) / self.module_workspace_folder(module)

    def module_workspace_folder(self, module: dict[str, Any]) -> str:
        folder = module.get("workspace", {}).get("folder") or module.get("id")
        return safe_id(folder)

    def get_workspace_relative_path(self, workspace_id: str) -> str:
        return safe_id(workspace_id)

    def get_module_relative_path(self, module_id: str) -> str:
        return safe_id(module_id)

    def user_can_access(self, user: dict[str, Any], workspace_id: str) -> bool:
        workspaces = user.get("workspaces", {})
        return workspace_id in workspaces.get("owned", []) or workspace_id in workspaces.get("shared", [])

    def read_workspace_meta(self, workspace_id: str) -> dict[str, Any]:
        return self.config.read_yaml(self.get_workspace_path(workspace_id) / "workspace.yaml")

    def list_for_user(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        result = []
        workspaces = user.get("workspaces", {})
        for access_type in ("owned", "shared"):
            for workspace_id in workspaces.get(access_type, []):
                meta = self.read_workspace_meta(workspace_id)
                if meta:
                    meta["access_type"] = access_type
                    result.append(meta)
        return result

    def create_workspace(
        self,
        username: str,
        name: str,
        modules: list[dict[str, Any]],
        description: str = "",
    ) -> dict[str, Any]:
        safe_workspace_id = self.generate_workspace_id(name)
        workspace_path = self.get_workspace_path(safe_workspace_id)
        workspace_path.mkdir(parents=True, exist_ok=False)
        meta = {
            "id": safe_workspace_id,
            "name": name,
            "owner": username,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "description": description,
        }
        self.config.write_yaml(workspace_path / "workspace.yaml", meta)
        self.config.write_yaml(workspace_path / "settings.yaml", {"settings": {}})
        self.initialize_modules(username, safe_workspace_id, meta, modules)
        return meta

    def generate_workspace_id(self, name: str) -> str:
        base_name = safe_id(name).lower().strip("_") or "workspace"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        candidate = f"ws_{base_name}_{timestamp}"
        if not self.get_workspace_path(candidate).exists():
            return candidate
        suffix = 2
        while self.get_workspace_path(f"{candidate}_{suffix}").exists():
            suffix += 1
        return f"{candidate}_{suffix}"

    def initialize_modules(
        self,
        username: str,
        workspace_id: str,
        workspace: dict[str, Any],
        modules: list[dict[str, Any]],
    ) -> None:
        for module in modules:
            module_id = module.get("id")
            if not module_id:
                continue
            module_path = self.get_module_path_for_manifest(workspace_id, module)
            module_path.mkdir(parents=True, exist_ok=True)
            self._copy_module_init_files(module, module_path)
            self._run_module_init_hook(username, workspace_id, workspace, module, module_path)

    def _copy_module_init_files(self, module: dict[str, Any], module_path: Path) -> None:
        init_config = module.get("workspace", {}).get("init", {})
        init_files = init_config.get("files")
        if not init_files:
            return
        source = self.config.resolve_project_path(init_files)
        if not source.exists():
            return
        if source.is_file():
            shutil.copy2(source, module_path / source.name)
            return
        for item in source.rglob("*"):
            if item.is_dir():
                continue
            relative = item.relative_to(source)
            target = module_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)

    def _run_module_init_hook(
        self,
        username: str,
        workspace_id: str,
        workspace: dict[str, Any],
        module: dict[str, Any],
        module_path: Path,
    ) -> None:
        init_config = module.get("workspace", {}).get("init", {})
        hook_ref = init_config.get("python_hook")
        if not hook_ref:
            return
        module_name, attr_name = hook_ref.split(":", 1)
        hook = getattr(import_module(module_name), attr_name)
        hook(
            config=self.config,
            username=username,
            workspace_id=workspace_id,
            workspace=workspace,
            workspace_path=self.get_workspace_path(workspace_id),
            module=module,
            module_path=module_path,
        )
