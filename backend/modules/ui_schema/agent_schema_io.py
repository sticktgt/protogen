from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from backend.modules.ui_schema.agent_schema_merge import merge_preserving_agent_content
from backend.modules.ui_schema.files import read_json, write_json

_PAGE_FILE = re.compile(r"^[a-zA-Z0-9_.-]+\.json$")
_DEFAULT_MAX_PAGE_FILES = 8


def write_ui_schema_bundle(
    *,
    working_root: Path,
    result_root: Path,
    files: list[dict[str, Any]],
    maximum_files: int,
) -> dict[str, Any]:
    if not isinstance(files, list) or not files:
        raise ValueError("files must be a non-empty list")
    if len(files) > maximum_files:
        raise ValueError(
            f"A bundle may contain at most {maximum_files} files; split it into a few larger batches"
        )

    prepared: list[tuple[str, Path, dict[str, Any]]] = []
    seen: set[str] = set()
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise ValueError(f"files[{index}] must be an object")
        file_path = item.get("file_path")
        content = item.get("content")
        if not isinstance(file_path, str) or not file_path.strip():
            raise ValueError(f"files[{index}].file_path must be a non-empty string")
        normalized = normalize_write_path(file_path)
        if normalized in seen:
            raise ValueError(f"Duplicate path in bundle: {normalized}")
        seen.add(normalized)
        if normalized == "index.json":
            raise ValueError(
                "index.json is derived; write source schema files and validate the schema"
            )
        target = _resolve_write_target(working_root, result_root, normalized)
        _validate_top_level_shape(normalized, content)
        prepared_content = content
        if normalized in {"app.json", "schema.json"} or normalized.startswith("pages/"):
            current = read_json(target, {})
            prepared_content = merge_preserving_agent_content(normalized, current, content)
        prepared.append((normalized, target, prepared_content))

    for _, target, content in prepared:
        write_json(target, content)
    paths = [path for path, _, _ in prepared]
    return {
        "ok": True,
        "message": f"Written {len(paths)} UI Schema JSON files",
        "file_count": len(paths),
        "paths": paths,
    }


def delete_page_file(*, working_root: Path, file_path: str, base_root: Path | None = None) -> dict[str, Any]:
    normalized = normalize_write_path(file_path)
    if not normalized.startswith("pages/"):
        raise ValueError("Only pages/*.json can be deleted")
    name = normalized.removeprefix("pages/")
    if not _PAGE_FILE.fullmatch(name):
        raise ValueError("Invalid page file name")
    if base_root is not None and (base_root / "pages" / name).is_file():
        raise ValueError(
            "Existing base pages cannot be deleted by synchronization: " + normalized
        )
    _ensure_new_page_is_unregistered_and_unreferenced(working_root, normalized)
    (working_root / "pages" / name).unlink(missing_ok=True)
    return {"ok": True, "message": f"Deleted {normalized}", "path": normalized}


def recoverable_tool_result(operation: Callable[[], dict[str, Any]]) -> str:
    try:
        result = operation()
    except (OSError, TypeError, ValueError) as exc:
        result = {
            "ok": False,
            "error": str(exc),
            "hint": (
                "Correct the tool arguments and continue. Use native JSON with "
                "write_ui_schema_core, write_ui_schema_pages or "
                "write_ui_schema_traceability according to the affected document."
            ),
        }
    return json.dumps(result, ensure_ascii=False)


def max_page_files(agent_config: dict[str, Any]) -> int:
    return _positive_execution_int(
        agent_config,
        key="write_pages_max_files",
        default=_DEFAULT_MAX_PAGE_FILES,
    )


def normalize_write_path(file_path: str) -> str:
    normalized = file_path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    for prefix in ("/working/ui_schema/", "working/ui_schema/"):
        if normalized.startswith(prefix):
            return normalized[len(prefix):]
    for prefix in ("/result/", "result/"):
        if normalized.startswith(prefix):
            return "result/" + normalized[len(prefix):]
    return normalized.lstrip("/")



def _ensure_new_page_is_unregistered_and_unreferenced(
    working_root: Path,
    normalized_path: str,
) -> None:
    target = working_root / normalized_path
    page = read_json(target, {})
    page_id = str(page.get("id") or Path(normalized_path).stem)
    element_ids: set[str] = set()
    _collect_element_ids(page.get("elements", []), element_ids)

    schema = read_json(working_root / "schema.json", {})
    registrations = schema.get("pages", []) if isinstance(schema, dict) else []
    registered = any(
        isinstance(item, dict)
        and (
            item.get("id") == page_id
            or normalize_write_path(str(item.get("file") or "")) == normalized_path
        )
        for item in registrations
    )
    if registered:
        raise ValueError(
            f"Cannot delete {normalized_path}: it is still registered in schema.json. "
            "Create or repair the page file, or first remove its registration "
            "and related links in one correction bundle."
        )

    protected_targets = {page_id, *element_ids}
    ui_links = read_json(working_root / "links.json", {}).get("links", [])
    requirement_links = read_json(
        working_root / "mappings" / "requirement_ui_links.json", {}
    ).get("links", [])
    referenced = [
        str(item.get("id") or "<without id>")
        for item in [*(ui_links or []), *(requirement_links or [])]
        if isinstance(item, dict)
        and (
            item.get("source_id") in protected_targets
            or item.get("target_id") in protected_targets
        )
    ]
    if referenced:
        raise ValueError(
            f"Cannot delete {normalized_path}: related links still reference "
            "the page or its elements: "
            + ", ".join(referenced[:10])
        )


def _collect_element_ids(items: Any, target: set[str]) -> None:
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id:
            target.add(item_id)
        _collect_element_ids(item.get("children", []), target)


def _resolve_write_target(working_root: Path, result_root: Path, file_path: str) -> Path:
    normalized = normalize_write_path(file_path)
    exact = {
        "app.json": working_root / "app.json",
        "schema.json": working_root / "schema.json",
        "links.json": working_root / "links.json",
        "mappings/requirement_ui_links.json": (
            working_root / "mappings" / "requirement_ui_links.json"
        ),
        "result/agent_report.json": result_root / "agent_report.json",
    }
    if normalized in exact:
        return exact[normalized]
    if normalized.startswith("pages/"):
        name = normalized.removeprefix("pages/")
        if _PAGE_FILE.fullmatch(name):
            return working_root / "pages" / name
    raise ValueError(
        "Writing this path is not allowed: "
        f"{file_path}. Use app.json, schema.json, links.json, "
        "mappings/requirement_ui_links.json, pages/*.json or result/agent_report.json"
    )


def _validate_top_level_shape(file_path: str, content: Any) -> None:
    if not isinstance(content, dict):
        raise ValueError(f"{file_path} must contain a JSON object")


def _positive_execution_int(
    agent_config: dict[str, Any],
    *,
    key: str,
    default: int,
) -> int:
    execution = agent_config.get("execution", {}) if isinstance(agent_config, dict) else {}
    value = execution.get(key) if isinstance(execution, dict) else None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
