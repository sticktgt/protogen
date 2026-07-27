from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.state import AppState
from backend.modules.ui_schema.files import read_json
from backend.modules.ui_schema.index_builder import rebuild_index
from backend.modules.ui_schema.requirements_source import resolve_requirements
from backend.modules.ui_schema.storage import (
    index_path,
    list_pages,
    module_root,
    normalize_code_links,
    read_app,
    read_code_links,
    read_requirement_links,
    read_schema,
    read_ui_links,
)


def read_summary(state: AppState, workspace_id: str) -> dict[str, Any]:
    root = module_root(state, workspace_id)
    rebuild_index(root)
    requirements, source = resolve_requirements(root)
    return read_summary_from_root(root, requirements=requirements, requirements_source=source)


def read_summary_from_root(
    root: Path,
    *,
    requirements: dict[str, Any] | None = None,
    requirements_source: dict[str, Any] | None = None,
    preview_changes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_requirements = requirements if isinstance(requirements, dict) else {"requirements": []}
    return {
        "schema": read_schema(root),
        "app": read_app(root),
        "ui_links": read_ui_links(root),
        "index": read_json(index_path(root), {"pages": [], "root_elements": []}),
        "pages": list_pages(root),
        "requirement_links": read_requirement_links(root),
        "requirements": resolved_requirements,
        "requirements_source": requirements_source or {"status": "not_configured"},
        "code_links": {"links": normalize_code_links(read_code_links(root))},
        "preview_changes": preview_changes or {},
    }
