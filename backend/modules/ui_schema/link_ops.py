from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.modules.ui_schema.index_builder import rebuild_index
from backend.modules.ui_schema.storage import (
    normalize_code_links,
    read_code_links,
    read_requirement_links,
    write_code_links,
    write_requirement_links,
)


def add_requirement_link(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    links = read_requirement_links(root)
    link = {
        "id": payload.get("id") or uuid4().hex,
        "requirement_id": payload["requirement_id"],
        "target_type": payload["target_type"],
        "target_id": payload["target_id"],
        "relation": payload.get("relation", "implemented_by"),
        "implementation_status": payload.get("implementation_status", "planned"),
    }
    links.setdefault("links", []).append(link)
    write_requirement_links(root, links)
    rebuild_index(root)
    return link


def delete_requirement_link(root: Path, link_id: str) -> None:
    links = read_requirement_links(root)
    links["links"] = [link for link in links.get("links", []) if link.get("id") != link_id]
    write_requirement_links(root, links)
    rebuild_index(root)


def add_code_link(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    code_links = {"links": normalize_code_links(read_code_links(root))}
    link = {
        "id": payload.get("id") or uuid4().hex,
        "target_type": payload["target_type"],
        "target_id": payload["target_id"],
        "kind": payload.get("kind", "frontend_file"),
        "path": payload.get("path", ""),
    }
    code_links.setdefault("links", []).append(link)
    write_code_links(root, code_links)
    return link


def delete_code_link(root: Path, link_id: str) -> None:
    code_links = {"links": normalize_code_links(read_code_links(root))}
    code_links["links"] = [link for link in code_links.get("links", []) if link.get("id") != link_id]
    write_code_links(root, code_links)
