from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_requirement_scope import current_requirement_ids
from backend.modules.data_schema.files import read_json, write_json


def build_manual_review_result(
    run_path: Path,
    semantic_review: dict[str, Any],
) -> dict[str, Any]:
    """Build non-blocking information intended only for analyst review."""
    inherited = _inherited_requirement_links(run_path)
    cleanup = [
        dict(item)
        for item in semantic_review.get("cleanup_candidates", [])
        if isinstance(item, dict)
    ]
    return {
        "inherited_requirement_links": inherited,
        "cleanup_candidates": cleanup,
        "counts": {
            "inherited_requirement_ids": len(inherited),
            "inherited_requirement_links": sum(
                len(item.get("links", [])) for item in inherited
            ),
            "cleanup_candidates": len(cleanup),
        },
    }


def write_manual_review_result(
    run_path: Path,
    semantic_review: dict[str, Any],
) -> dict[str, Any]:
    result = build_manual_review_result(run_path, semantic_review)
    write_json(run_path / "result" / "manual_review.json", result)
    return result


def ensure_manual_review_result(
    run_path: Path,
    semantic_review: dict[str, Any],
) -> dict[str, Any]:
    path = run_path / "result" / "manual_review.json"
    stored = read_json(path, {})
    if isinstance(stored, dict) and stored.get("counts"):
        return stored
    return write_manual_review_result(run_path, semantic_review)


def _inherited_requirement_links(run_path: Path) -> list[dict[str, Any]]:
    current_ids = current_requirement_ids(run_path)
    base_links = _read_links(run_path / "base" / "data_schema")
    inherited_ids = {
        str(item.get("requirement_id") or "").strip()
        for item in base_links
        if str(item.get("requirement_id") or "").strip() not in current_ids
    }
    working_links = _read_links(run_path / "working" / "data_schema")
    grouped: dict[str, list[dict[str, str]]] = {}
    for item in working_links:
        requirement_id = str(item.get("requirement_id") or "").strip()
        if requirement_id not in inherited_ids:
            continue
        link = {
            key: str(item.get(key) or "").strip()
            for key in ("target_type", "target_id", "relation")
            if str(item.get(key) or "").strip()
        }
        grouped.setdefault(requirement_id, []).append(link)
    return [
        {"requirement_id": requirement_id, "links": grouped[requirement_id]}
        for requirement_id in sorted(grouped)
    ]


def _read_links(schema_root: Path) -> list[dict[str, Any]]:
    document = read_json(
        schema_root / "mappings" / "requirement_data_links.json",
        {"links": []},
    )
    links = document.get("links", []) if isinstance(document, dict) else []
    return [item for item in links if isinstance(item, dict)]
