from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ConfigReader:
    """Small YAML/JSON reader. It does not validate module-owned settings."""

    def __init__(self, project_root: Path, app_config_path: Path):
        self.project_root = project_root.resolve()
        self.app_config_path = app_config_path
        self.app_config = self.read_yaml(app_config_path)

    def resolve_project_path(self, relative_path: str | Path) -> Path:
        return (self.project_root / relative_path).resolve()

    def read_yaml(self, path: str | Path) -> dict[str, Any]:
        target = Path(path)
        if not target.is_absolute():
            target = self.project_root / target
        if not target.exists():
            return {}
        with target.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        return data

    def write_yaml(self, path: str | Path, data: dict[str, Any]) -> None:
        target = Path(path)
        if not target.is_absolute():
            target = self.project_root / target
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as file:
            yaml.safe_dump(data, file, sort_keys=False, allow_unicode=True)


    def write_app_config(self, data: dict[str, Any]) -> None:
        self.write_yaml(self.app_config_path, data)
        self.app_config = data

    def read_module_runtime_config(self, module_id: str) -> dict[str, Any]:
        modules_dir = self.app_config["paths"]["modules_dir"]
        return self.read_yaml(Path(modules_dir) / module_id / "config.yaml")

    def public_app_config(self) -> dict[str, Any]:
        public_config = dict(self.app_config)
        auth = dict(public_config.get("auth", {}))
        auth.pop("secret_key", None)
        public_config["auth"] = auth
        return public_config
