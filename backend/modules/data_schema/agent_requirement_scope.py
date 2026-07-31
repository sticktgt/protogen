from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.files import read_json


def requirement_ids(document: dict[str, Any]) -> set[str]:
    return {
        str(item.get("id") or "").strip()
        for item in document.get("requirements", [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }


def requirement_link_ids(schema_root: Path) -> set[str]:
    document = read_json(
        schema_root / "mappings" / "requirement_data_links.json",
        {"links": []},
    )
    return {
        str(item.get("requirement_id") or "").strip()
        for item in document.get("links", [])
        if isinstance(item, dict)
        and str(item.get("requirement_id") or "").strip()
    }


def current_requirement_ids(run_path: Path) -> set[str]:
    return requirement_ids(
        read_json(run_path / "input" / "requirements.json", {"requirements": []})
    )


def inherited_requirement_ids(run_path: Path) -> set[str]:
    return requirement_link_ids(run_path / "base" / "data_schema")


def allowed_requirement_ids(run_path: Path) -> set[str]:
    return current_requirement_ids(run_path) | inherited_requirement_ids(run_path)
