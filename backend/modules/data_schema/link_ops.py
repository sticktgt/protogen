from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from backend.modules.data_schema import storage

ReadFunc = Callable[[Path], dict[str, Any]]
WriteFunc = Callable[[Path, dict[str, Any]], None]


def add_requirement_link(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return _add_link(root, storage.read_requirement_links, storage.write_requirement_links, {
        "id": storage.make_id("req_data_link"),
        "requirement_id": payload["requirement_id"],
        "target_type": payload["target_type"],
        "target_id": payload["target_id"],
        "relation": payload.get("relation", "defines"),
        "implementation_status": payload.get("implementation_status", "planned"),
    })


def delete_requirement_link(root: Path, link_id: str) -> None:
    _delete_link(root, storage.read_requirement_links, storage.write_requirement_links, link_id)


def add_ui_link(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return _add_external_link(root, storage.read_ui_links, storage.write_ui_links, payload, "ui_schema")


def delete_ui_link(root: Path, link_id: str) -> None:
    _delete_link(root, storage.read_ui_links, storage.write_ui_links, link_id)


def add_api_link(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return _add_external_link(root, storage.read_api_links, storage.write_api_links, payload, "api_schema")


def delete_api_link(root: Path, link_id: str) -> None:
    _delete_link(root, storage.read_api_links, storage.write_api_links, link_id)


def add_code_link(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return _add_link(root, storage.read_code_links, storage.write_code_links, {
        "id": storage.make_id("code_data_link"),
        "target_type": payload["target_type"],
        "target_id": payload["target_id"],
        "code_type": payload.get("code_type", "model"),
        "path": payload.get("path", ""),
        "status": payload.get("status", "planned"),
    })


def delete_code_link(root: Path, link_id: str) -> None:
    _delete_link(root, storage.read_code_links, storage.write_code_links, link_id)


def _add_external_link(
    root: Path,
    read_func: ReadFunc,
    write_func: WriteFunc,
    payload: dict[str, Any],
    schema_name: str,
) -> dict[str, Any]:
    return _add_link(root, read_func, write_func, {
        "id": storage.make_id(f"{schema_name}_data_link"),
        "data_target_type": payload["data_target_type"],
        "data_target_id": payload["data_target_id"],
        "external_schema": schema_name,
        "external_target_type": payload["external_target_type"],
        "external_target_id": payload["external_target_id"],
        "relation": payload.get("relation", "uses"),
    })


def _add_link(root: Path, read_func: ReadFunc, write_func: WriteFunc, link: dict[str, Any]) -> dict[str, Any]:
    data = read_func(root)
    data.setdefault("links", []).append(link)
    write_func(root, data)
    return link


def _delete_link(root: Path, read_func: ReadFunc, write_func: WriteFunc, link_id: str) -> None:
    data = read_func(root)
    data["links"] = [item for item in data.get("links", []) if item.get("id") != link_id]
    write_func(root, data)
