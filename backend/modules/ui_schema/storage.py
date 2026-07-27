from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.app.state import AppState
from backend.modules.ui_schema.files import read_json, write_json
from backend.modules.ui_schema.workspace_migration import remove_obsolete_requirements_copy

MODULE_ID = "ui_schema"

DEFAULT_SCHEMA = {
    "schema_version": "0.1",
    "application": {
        "name": "Generated Prototype",
        "description": "Демонстрационная UI-схема прототипа",
    },
    "pages": [],
}
DEFAULT_APP = {
    "id": "app",
    "title": "Generated Prototype",
    "root_elements": [],
}
DEFAULT_LINKS = {"links": []}
DEFAULT_CODE_LINKS = {"links": []}
DEFAULT_UI_LINKS = {"links": []}
DEFAULT_REQUIREMENTS_SOURCE = {"type": "workspace_file", "path": ""}


def module_root(state: AppState, workspace_id: str) -> Path:
    root = state.workspaces.get_module_path(workspace_id, MODULE_ID)
    remove_obsolete_requirements_copy(root)
    return root


def schema_path(root: Path) -> Path:
    return root / "schema.json"


def app_path(root: Path) -> Path:
    return root / "app.json"



def index_path(root: Path) -> Path:
    return root / "index.json"


def links_path(root: Path) -> Path:
    return root / "mappings" / "requirement_ui_links.json"


def ui_links_path(root: Path) -> Path:
    return root / "links.json"


def code_links_path(root: Path) -> Path:
    return root / "code_links.json"


def requirements_source_path(root: Path) -> Path:
    return root / "requirements_source.json"


def page_path(root: Path, page_id: str) -> Path:
    return root / "pages" / f"{page_id}.json"


def read_schema(root: Path) -> dict[str, Any]:
    return read_json(schema_path(root), dict(DEFAULT_SCHEMA))


def write_schema(root: Path, schema: dict[str, Any]) -> None:
    write_json(schema_path(root), schema)


def read_app(root: Path) -> dict[str, Any]:
    return read_json(app_path(root), dict(DEFAULT_APP))


def write_app(root: Path, app: dict[str, Any]) -> None:
    write_json(app_path(root), app)



def read_requirement_links(root: Path) -> dict[str, Any]:
    return read_json(links_path(root), dict(DEFAULT_LINKS))


def write_requirement_links(root: Path, links: dict[str, Any]) -> None:
    write_json(links_path(root), links)


def read_ui_links(root: Path) -> dict[str, Any]:
    return read_json(ui_links_path(root), dict(DEFAULT_UI_LINKS))


def write_ui_links(root: Path, links: dict[str, Any]) -> None:
    write_json(ui_links_path(root), links)


def read_requirements_source(root: Path) -> dict[str, Any]:
    return read_json(requirements_source_path(root), dict(DEFAULT_REQUIREMENTS_SOURCE))


def write_requirements_source(root: Path, source: dict[str, Any]) -> None:
    write_json(requirements_source_path(root), source)


def read_code_links(root: Path) -> dict[str, Any]:
    return read_json(code_links_path(root), dict(DEFAULT_CODE_LINKS))


def write_code_links(root: Path, code_links: dict[str, Any]) -> None:
    write_json(code_links_path(root), code_links)


def normalize_code_links(code_links: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for item in code_links.get("links", []):
        if "code_refs" in item:
            result.extend(normalize_code_refs(item))
        else:
            result.append(normalize_code_link(item))
    return result


def normalize_code_refs(item: dict[str, Any]) -> list[dict[str, Any]]:
    target_type = item.get("target_type", "page")
    target_id = item.get("target_id", "")
    return [
        {
            "id": ref.get("id") or item.get("id") or f"{target_type}:{target_id}:{index}",
            "target_type": target_type,
            "target_id": target_id,
            "kind": ref.get("kind", "frontend_file"),
            "path": ref.get("path", ""),
        }
        for index, ref in enumerate(item.get("code_refs", []))
    ]


def normalize_code_link(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or uuid4().hex,
        "target_type": item.get("target_type", "page"),
        "target_id": item.get("target_id", ""),
        "kind": item.get("kind", "frontend_file"),
        "path": item.get("path", ""),
    }


def read_page(root: Path, page_id: str) -> dict[str, Any] | None:
    path = page_path(root, page_id)
    if not path.exists():
        return None
    return read_json(path, {})


def write_page(root: Path, page: dict[str, Any]) -> None:
    write_json(page_path(root, page["id"]), page)


def list_pages(root: Path) -> list[dict[str, Any]]:
    schema = read_schema(root)
    result = []
    for item in schema.get("pages", []):
        page = read_page(root, item.get("id", "")) or {}
        result.append({**item, "details": page})
    return result
