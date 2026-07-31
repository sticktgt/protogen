from __future__ import annotations

from typing import Any

_REQUIREMENT_KEYS = (
    "id",
    "code",
    "name",
    "description",
    "acceptanceCriteria",
    "relations",
    "types",
    "domainId",
    "groupId",
    "projectId",
)


def compact_requirements(document: dict[str, Any]) -> dict[str, Any]:
    """Keep only requirement fields needed by the synchronization agent."""
    requirements: list[dict[str, Any]] = []
    for item in document.get("requirements", []):
        if not isinstance(item, dict):
            continue
        requirements.append(
            {
                key: item[key]
                for key in _REQUIREMENT_KEYS
                if key in item and item[key] not in (None, "", [], {})
            }
        )
    return {
        "projects": _compact_named_items(document.get("projects", []), ("id", "name")),
        "groups": _compact_named_items(
            document.get("groups", []),
            ("id", "name", "projectId"),
        ),
        "clusters": _compact_named_items(
            document.get("clusters", []),
            ("id", "name", "groupId", "projectId"),
        ),
        "requirements": requirements,
    }


def _compact_named_items(items: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    return [
        {
            key: item[key]
            for key in keys
            if key in item and item[key] not in (None, "", [], {})
        }
        for item in items
        if isinstance(item, dict)
    ]
