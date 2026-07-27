from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_validation_rules import (
    validate_element,
    validate_requirement_links,
    validate_ui_links,
)
from backend.modules.ui_schema.index_builder import rebuild_index
from backend.modules.ui_schema.requirements_source import resolve_requirements
from backend.modules.ui_schema.storage import (
    code_links_path,
    page_path,
    read_app,
    read_requirement_links,
    read_schema,
    read_ui_links,
)

PAGE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
MANDATORY_FILES = (
    "app.json",
    "schema.json",
    "links.json",
    "code_links.json",
    "mappings/requirement_ui_links.json",
)


def validate_ui_schema(
    root: Path,
    *,
    rebuild: bool = True,
    requirements_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not root.exists() or not root.is_dir():
        return {"valid": False, "errors": [f"UI schema folder does not exist: {root}"], "warnings": []}

    for relative_path in MANDATORY_FILES:
        path = root / relative_path
        if not path.is_file():
            errors.append(f"Missing required file: {relative_path}")
            continue
        try:
            _read_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"Invalid JSON in {relative_path}: {exc}")

    source_path = root / "requirements_source.json"
    legacy_requirements_path = root / "requirements.json"
    if source_path.is_file():
        try:
            _read_json(source_path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"Invalid JSON in requirements_source.json: {exc}")
    elif not legacy_requirements_path.is_file():
        errors.append("Missing required file: requirements_source.json")
    else:
        warnings.append(
            "Legacy requirements.json is still present; it will be replaced by requirements_source.json after accepted synchronization"
        )

    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings}

    try:
        schema = read_schema(root)
        app = read_app(root)
        requirements_source = None
        if isinstance(requirements_data, dict):
            requirements = requirements_data
        else:
            requirements, requirements_source = resolve_requirements(root)
        requirement_links = read_requirement_links(root)
        ui_links = read_ui_links(root)
        _read_json(code_links_path(root))
    except (OSError, json.JSONDecodeError) as exc:
        return {"valid": False, "errors": [str(exc)], "warnings": warnings}

    object_ids: set[str] = set()
    page_ids: set[str] = set()
    element_ids: set[str] = set()
    element_types: dict[str, str] = {}

    app_id = app.get("id")
    if app_id != "app":
        errors.append("app.json field id must be 'app'")

    root_elements = app.get("root_elements")
    if not isinstance(root_elements, list):
        errors.append("app.json root_elements must be a list")
        root_elements = []

    for element in root_elements:
        validate_element(
            element,
            scope="app",
            parent_type=None,
            object_ids=object_ids,
            element_ids=element_ids,
            element_types=element_types,
            errors=errors,
            path="app.root_elements",
        )

    raw_pages = schema.get("pages")
    if not isinstance(raw_pages, list):
        errors.append("schema.json pages must be a list")
        raw_pages = []

    for index, page_ref in enumerate(raw_pages):
        if not isinstance(page_ref, dict):
            errors.append(f"schema.pages[{index}] must be an object")
            continue
        page_id = page_ref.get("id")
        if not isinstance(page_id, str) or not PAGE_ID_PATTERN.fullmatch(page_id):
            errors.append(f"Invalid page id in schema.pages[{index}]: {page_id!r}")
            continue
        if page_id in page_ids or page_id in object_ids:
            errors.append(f"Duplicate UI object id: {page_id}")
            continue
        page_ids.add(page_id)
        object_ids.add(page_id)

        expected_file = f"pages/{page_id}.json"
        if page_ref.get("file") != expected_file:
            errors.append(f"Page {page_id} must reference file {expected_file}")

        path = page_path(root, page_id)
        if not path.is_file():
            errors.append(f"Page file does not exist: {expected_file}")
            continue
        try:
            page = _read_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"Invalid JSON in {expected_file}: {exc}")
            continue

        if page.get("id") != page_id:
            errors.append(f"Page id mismatch in {expected_file}: expected {page_id}")
        if not isinstance(page.get("title"), str) or not page.get("title", "").strip():
            errors.append(f"Page {page_id} must have a non-empty title")
        elements = page.get("elements")
        if not isinstance(elements, list):
            errors.append(f"Page {page_id} elements must be a list")
            elements = []
        for element in elements:
            validate_element(
                element,
                scope="page",
                parent_type=None,
                object_ids=object_ids,
                element_ids=element_ids,
                element_types=element_types,
                errors=errors,
                path=f"pages/{page_id}.elements",
            )

    pages_folder = root / "pages"
    if pages_folder.exists():
        for path in pages_folder.glob("*.json"):
            if path.stem not in page_ids:
                errors.append(f"Unregistered page file: pages/{path.name}")

    validate_ui_links(
        ui_links,
        page_ids=page_ids,
        element_ids=element_ids,
        element_types=element_types,
        errors=errors,
    )

    requirement_ids = {
        item.get("id")
        for item in requirements.get("requirements", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if requirements_source and requirements_source.get("status") != "available":
        warnings.append(
            "Requirements source is unavailable; requirement identifiers could not be verified: "
            + str(requirements_source.get("error") or requirements_source.get("status"))
        )
    validate_requirement_links(
        requirement_links,
        requirement_ids=requirement_ids,
        page_ids=page_ids,
        element_ids=element_ids,
        errors=errors,
        warnings=warnings,
    )

    if rebuild and not errors:
        try:
            rebuild_index(root)
        except Exception as exc:  # deterministic validation boundary
            errors.append(f"Could not rebuild index.json: {exc}")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "pages": len(page_ids),
            "elements": len(element_ids),
            "ui_links": len(ui_links.get("links", [])),
            "requirement_links": len(requirement_links.get("links", [])),
        },
    }


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise json.JSONDecodeError("Top-level JSON value must be an object", "", 0)
    return data
