from __future__ import annotations

from importlib import import_module
from typing import Any

from fastapi import FastAPI

from backend.app.core.config.reader import ConfigReader


class ModuleCatalog:
    """Reads module manifests. It does not validate module business settings."""

    def __init__(self, config: ConfigReader):
        self.config = config
        self._modules = self._load_modules()

    def _load_modules(self) -> list[dict[str, Any]]:
        config_path = self.config.resolve_project_path(self.config.app_config["paths"]["module_list"])
        raw = self.config.read_yaml(config_path)
        modules = []
        for item in raw.get("modules", []):
            if not item.get("enabled", False):
                continue
            manifest_path = item.get("manifest")
            manifest = self.config.read_yaml(manifest_path)
            manifest["manifest_path"] = manifest_path
            modules.append(manifest)
        return modules

    def enabled_modules(self) -> list[dict[str, Any]]:
        return list(self._modules)

    def get_module(self, module_id: str) -> dict[str, Any] | None:
        for module in self._modules:
            if module.get("id") == module_id:
                return module
        return None

    def menu(self) -> list[dict[str, Any]]:
        result = []
        for module in self._modules:
            for page in module.get("frontend", {}).get("pages", []):
                menu_config = self._page_menu_config(page)
                if not menu_config.get("show"):
                    continue
                result.append({
                    "id": f"{module['id']}.{page['id']}",
                    "module_id": module["id"],
                    "module_name": module.get("name", module["id"]),
                    "title": menu_config.get("title") or page.get("title", page["id"]),
                    "path": self.page_path(module, page),
                    "icon": menu_config.get("icon", page.get("icon", "")),
                    "order": menu_config.get("order", page.get("order", 1000)),
                })
        return sorted(result, key=lambda item: (item.get("order", 1000), item["title"]))

    def pages(self) -> list[dict[str, Any]]:
        result = []
        for module in self._modules:
            for page in module.get("frontend", {}).get("pages", []):
                result.append({
                    "id": f"{module['id']}.{page['id']}",
                    "module_id": module["id"],
                    "title": page.get("title", page["id"]),
                    "path": self.page_path(module, page),
                    "params": page.get("params", []),
                    "menu": self._page_menu_config(page),
                })
        return result

    def page_path(self, module: dict[str, Any], page: dict[str, Any]) -> str:
        base_path = module.get("frontend", {}).get("base_path", "")
        return "/".join(part.strip("/") for part in [base_path, page.get("path", "")] if part)

    def include_backend_routers(self, app: FastAPI) -> None:
        for module in self._modules:
            backend = module.get("backend", {})
            router_ref = backend.get("router")
            if not router_ref:
                continue
            module_name, attr_name = router_ref.split(":", 1)
            router = getattr(import_module(module_name), attr_name)
            prefix = backend.get("api_prefix", "")
            app.include_router(router, prefix=prefix)

    def read_doc(self, module_id: str, doc_key: str) -> dict[str, Any]:
        module = self.get_module(module_id)
        if not module:
            return {}
        path = module.get("docs", {}).get(doc_key)
        if not path:
            return {}
        return self.config.read_yaml(path)

    @staticmethod
    def _page_menu_config(page: dict[str, Any]) -> dict[str, Any]:
        raw = page.get("menu", False)
        if isinstance(raw, dict):
            return {"show": bool(raw.get("show", False)), **raw}
        return {"show": bool(raw)}
