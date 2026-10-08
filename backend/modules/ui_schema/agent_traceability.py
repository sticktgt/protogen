from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_manual_review import merge_traceability_with_inherited_links
from backend.modules.ui_schema.agent_requirement_scope import current_requirement_ids
from backend.modules.ui_schema.agent_schema_io import write_ui_schema_bundle
from backend.modules.ui_schema.agent_tool_payloads import normalize_traceability_argument
from backend.modules.ui_schema.files import read_json, write_json
from backend.modules.ui_schema.agent_traceability_dirty import clear_traceability_dirty

_ASSESSMENT_KEYS = ("cross_cutting_ui", "no_ui", "unclear")


def write_traceability_chunk(
    *,
    run_path: Path,
    working_root: Path,
    result_root: Path,
    requirement_ui_links: dict[str, Any],
    agent_report: dict[str, Any],
) -> dict[str, Any]:
    """Mechanically replace traceability for requirement IDs present in one chunk."""
    state_path = result_root / "traceability_state.json"
    state = read_json(state_path, {})
    first_chunk = not bool(state.get("initialized"))
    should_reset = first_chunk
    current_ids = current_requirement_ids(run_path)

    incoming_links_document = merge_traceability_with_inherited_links(
        run_path, requirement_ui_links
    )
    incoming_links = _prepare_incoming_links(
        _links(incoming_links_document),
        existing_links=_links(
            read_json(
                working_root / "mappings" / "requirement_ui_links.json",
                {"links": []},
            )
        ),
    )
    incoming_report = _normalized_report(agent_report)
    touched_ids = _touched_requirement_ids(incoming_links, incoming_report)

    if should_reset:
        existing_links: list[dict[str, Any]] = []
        existing_report = _empty_report()
        chunk_index = 1
    else:
        existing_links = [
            item
            for item in _links(
                read_json(
                    working_root / "mappings" / "requirement_ui_links.json",
                    {"links": []},
                )
            )
            if str(item.get("requirement_id") or "").strip() in current_ids
            and str(item.get("requirement_id") or "").strip() not in touched_ids
        ]
        existing_report = _normalized_report(
            read_json(result_root / "agent_report.json", {})
        )
        for key in _ASSESSMENT_KEYS:
            existing_report[key] = [
                item
                for item in existing_report[key]
                if str(item.get("requirement_id") or "").strip() not in touched_ids
            ]
        chunk_index = max(1, int(state.get("chunks", 1)) + 1)

    merged_links = _deduplicate_links([*existing_links, *incoming_links])
    merged_report = _merge_report(existing_report, incoming_report)
    result = write_ui_schema_bundle(
        working_root=working_root,
        result_root=result_root,
        files=normalize_traceability_argument(
            requirement_ui_links={"links": merged_links},
            agent_report=merged_report,
        ),
        maximum_files=2,
    )
    write_json(
        state_path,
        {
            **state,
            "initialized": True,
            "chunks": chunk_index,
            "started_new_traceability": should_reset,
            "last_touched_requirement_ids": sorted(touched_ids),
        },
    )
    remaining_dirty = clear_traceability_dirty(run_path, touched_ids)
    return {
        **result,
        "chunk_index": chunk_index,
        "started_new_traceability": should_reset,
        "requirements_touched": len(touched_ids),
        "requirement_links_total": len(merged_links),
        "assessment_totals": {
            key: len(merged_report[key]) for key in _ASSESSMENT_KEYS
        },
        "remaining_dirty_requirement_ids": remaining_dirty,
    }


def _prepare_incoming_links(
    links: list[dict[str, Any]],
    *,
    existing_links: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fill only technical link fields omitted by the model."""
    existing_ids = {
        _semantic_link_key(item): str(item.get("id") or "").strip()
        for item in existing_links
        if str(item.get("id") or "").strip()
    }
    result: list[dict[str, Any]] = []
    for source in links:
        item = dict(source)
        key = _semantic_link_key(item)
        if not str(item.get("id") or "").strip():
            item["id"] = existing_ids.get(key) or _generated_link_id(key)
        status = str(item.get("implementation_status") or "").strip()
        if status not in {"planned", "in_progress", "implemented"}:
            raise ValueError(
                "Each requirement link must include implementation_status: "
                "planned, in_progress or implemented"
            )
        result.append(item)
    return result


def _semantic_link_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return tuple(
        str(item.get(name) or "").strip()
        for name in ("requirement_id", "target_type", "target_id", "relation")
    )


def _generated_link_id(key: tuple[str, str, str, str]) -> str:
    digest = hashlib.sha1("|".join(key).encode("utf-8")).hexdigest()[:16]
    return f"requirement_link_{digest}"


def _normalized_report(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    result = _empty_report()
    result["summary"] = str(source.get("summary") or "")
    result["agent_note"] = str(source.get("agent_note") or "")
    result["warnings"] = [
        str(item) for item in source.get("warnings", []) if str(item).strip()
    ] if isinstance(source.get("warnings"), list) else []
    for key in _ASSESSMENT_KEYS:
        items = source.get(key, [])
        result[key] = [dict(item) for item in items if isinstance(item, dict)]
    return result


def _empty_report() -> dict[str, Any]:
    return {
        "summary": "",
        "agent_note": "",
        "cross_cutting_ui": [],
        "no_ui": [],
        "unclear": [],
        "warnings": [],
    }


def _merge_report(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    result = _normalized_report(existing)
    for key in _ASSESSMENT_KEYS:
        result[key] = [*result[key], *incoming[key]]
    if incoming.get("agent_note"):
        result["agent_note"] = str(incoming["agent_note"])
    result["summary"] = ""
    result["warnings"] = list(
        dict.fromkeys([*result.get("warnings", []), *incoming.get("warnings", [])])
    )
    return result


def _links(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or not isinstance(value.get("links"), list):
        return []
    return [dict(item) for item in value["links"] if isinstance(item, dict)]


def _touched_requirement_ids(
    links: list[dict[str, Any]], report: dict[str, Any]
) -> set[str]:
    result = {
        str(item.get("requirement_id") or "").strip()
        for item in links
        if str(item.get("requirement_id") or "").strip()
    }
    for key in _ASSESSMENT_KEYS:
        result.update(
            str(item.get("requirement_id") or "").strip()
            for item in report.get(key, [])
            if str(item.get("requirement_id") or "").strip()
        )
    return result


def _deduplicate_links(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in items:
        key = tuple(
            str(item.get(name) or "").strip()
            for name in ("requirement_id", "target_type", "target_id", "relation")
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
