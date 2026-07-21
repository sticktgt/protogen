from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.modules.ui_schema.index_builder import rebuild_index
from backend.modules.ui_schema.storage import read_ui_links, write_ui_links


def add_ui_link(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    links = read_ui_links(root)
    link = {
        "id": payload.get("id") or uuid4().hex,
        "source_type": payload.get("source_type", "ui_element"),
        "source_id": payload["source_id"],
        "target_type": payload.get("target_type", "page"),
        "target_id": payload["target_id"],
        "relation": payload.get("relation", "navigates_to"),
    }
    links.setdefault("links", []).append(link)
    write_ui_links(root, links)
    rebuild_index(root)
    return link


def delete_ui_link(root: Path, link_id: str) -> None:
    links = read_ui_links(root)
    links["links"] = [link for link in links.get("links", []) if link.get("id") != link_id]
    write_ui_links(root, links)
    rebuild_index(root)
