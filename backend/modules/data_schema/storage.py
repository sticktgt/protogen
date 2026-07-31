from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.app.state import AppState
from backend.modules.data_schema.files import read_json, write_json

MODULE_ID = "data_schema"

DEFAULT_SCHEMA = {
    "schema_version": "0.1",
    "title": "Логическая схема данных прототипа",
    "description": "",
    "entities": [],
}
DEFAULT_RELATIONS = {"relations": []}
DEFAULT_DICTIONARIES = {"dictionaries": []}
DEFAULT_INDEX = {"entities": [], "relations": [], "dictionaries": []}
DEFAULT_LINKS = {"links": []}
DEFAULT_REQUIREMENTS = {"projects": [], "groups": [], "requirements": []}
DEFAULT_REQUIREMENTS_SOURCE = {"type": "workspace_file", "path": ""}


def module_root(state: AppState, workspace_id: str) -> Path:
    return state.workspaces.get_module_path(workspace_id, MODULE_ID)


def schema_path(root: Path) -> Path:
    return root / "schema.json"


def index_path(root: Path) -> Path:
    return root / "index.json"


def entity_path(root: Path, entity_id: str) -> Path:
    return root / "entities" / f"{entity_id}.json"


def relations_path(root: Path) -> Path:
    return root / "relations.json"


def dictionaries_path(root: Path) -> Path:
    return root / "dictionaries.json"


def requirement_links_path(root: Path) -> Path:
    return root / "mappings" / "requirement_data_links.json"


def ui_links_path(root: Path) -> Path:
    return root / "mappings" / "ui_data_links.json"


def api_links_path(root: Path) -> Path:
    return root / "mappings" / "api_data_links.json"


def code_links_path(root: Path) -> Path:
    return root / "code_links.json"


def requirements_path(root: Path) -> Path:
    return root / "requirements.json"


def requirements_source_path(root: Path) -> Path:
    return root / "requirements_source.json"


def read_schema(root: Path) -> dict[str, Any]:
    return read_json(schema_path(root), dict(DEFAULT_SCHEMA))


def write_schema(root: Path, schema: dict[str, Any]) -> None:
    write_json(schema_path(root), schema)


def read_index(root: Path) -> dict[str, Any]:
    return read_json(index_path(root), dict(DEFAULT_INDEX))


def write_index(root: Path, index: dict[str, Any]) -> None:
    write_json(index_path(root), index)


def read_entity(root: Path, entity_id: str) -> dict[str, Any] | None:
    path = entity_path(root, entity_id)
    if not path.exists():
        return None
    return read_json(path, {})


def write_entity(root: Path, entity: dict[str, Any]) -> None:
    write_json(entity_path(root, entity["id"]), entity)


def list_entities(root: Path) -> list[dict[str, Any]]:
    schema = read_schema(root)
    result = []
    for item in schema.get("entities", []):
        entity = read_entity(root, item.get("id", "")) or {}
        result.append({**item, "details": entity})
    return result


def delete_entity_file(root: Path, entity_id: str) -> None:
    path = entity_path(root, entity_id)
    if path.exists():
        path.unlink()


def read_relations(root: Path) -> dict[str, Any]:
    return read_json(relations_path(root), dict(DEFAULT_RELATIONS))


def write_relations(root: Path, relations: dict[str, Any]) -> None:
    write_json(relations_path(root), relations)


def read_dictionaries(root: Path) -> dict[str, Any]:
    return read_json(dictionaries_path(root), dict(DEFAULT_DICTIONARIES))


def write_dictionaries(root: Path, dictionaries: dict[str, Any]) -> None:
    write_json(dictionaries_path(root), dictionaries)


def read_requirement_links(root: Path) -> dict[str, Any]:
    return read_json(requirement_links_path(root), dict(DEFAULT_LINKS))


def write_requirement_links(root: Path, links: dict[str, Any]) -> None:
    write_json(requirement_links_path(root), links)


def read_ui_links(root: Path) -> dict[str, Any]:
    return read_json(ui_links_path(root), dict(DEFAULT_LINKS))


def write_ui_links(root: Path, links: dict[str, Any]) -> None:
    write_json(ui_links_path(root), links)


def read_api_links(root: Path) -> dict[str, Any]:
    return read_json(api_links_path(root), dict(DEFAULT_LINKS))


def write_api_links(root: Path, links: dict[str, Any]) -> None:
    write_json(api_links_path(root), links)


def read_code_links(root: Path) -> dict[str, Any]:
    return read_json(code_links_path(root), dict(DEFAULT_LINKS))


def write_code_links(root: Path, links: dict[str, Any]) -> None:
    write_json(code_links_path(root), links)


def read_requirements(root: Path, *, max_bytes: int) -> dict[str, Any]:
    from backend.modules.data_schema.requirements_source import resolve_requirements

    data, _ = resolve_requirements(root, max_bytes=max_bytes)
    return data


def read_requirements_source(root: Path) -> dict[str, Any]:
    return read_json(requirements_source_path(root), dict(DEFAULT_REQUIREMENTS_SOURCE))


def write_requirements_source(root: Path, source: dict[str, Any]) -> None:
    write_json(requirements_source_path(root), source)


def make_id(prefix: str = "item") -> str:
    return f"{prefix}.{uuid4().hex[:10]}"
