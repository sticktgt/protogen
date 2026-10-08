from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from backend.modules.ui_schema.files import read_json

_DEFAULT_COMPACT_FIELDS = (
    "id",
    "code",
    "name",
    "description",
    "acceptanceCriteria",
    "types",
    "status",
    "priority",
    "domainId",
    "groupId",
    "formIds",
    "relations",
)


def current_requirement_ids(run_path: Path) -> set[str]:
    document = read_json(run_path / "input" / "requirements.json", {"requirements": []})
    records = document.get("requirements", []) if isinstance(document, dict) else []
    return {
        str(item.get("id") or "").strip()
        for item in records
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }


def compact_requirements(
    run_path: Path,
    *,
    fields: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Project requirements to the configured fields without changing their meaning."""
    document = read_json(run_path / "input" / "requirements.json", {"requirements": []})
    records = document.get("requirements", []) if isinstance(document, dict) else []
    allowed = tuple(
        key.strip()
        for key in (fields or _DEFAULT_COMPACT_FIELDS)
        if isinstance(key, str) and key.strip()
    )
    if "id" not in allowed:
        allowed = ("id", *allowed)

    result: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, dict) or not str(item.get("id") or "").strip():
            continue
        compact = {
            key: item[key]
            for key in allowed
            if key in item and item[key] not in (None, "", [], {})
        }
        result.append(compact)
    return result
