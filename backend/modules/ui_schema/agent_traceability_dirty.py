from __future__ import annotations

from pathlib import Path
from typing import Iterable

from backend.modules.ui_schema.files import read_json, write_json
from backend.modules.ui_schema.storage import read_requirement_links

_STATE_FILE = "traceability_dirty.json"


def mark_traceability_targets_dirty(run_path: Path, target_ids: Iterable[str]) -> list[str]:
    trace_state = read_json(run_path / "result" / "traceability_state.json", {})
    if not trace_state.get("initialized"):
        return []
    normalized_targets = {str(item).strip() for item in target_ids if str(item).strip()}
    if not normalized_targets:
        return []
    links = read_requirement_links(run_path / "working" / "ui_schema").get("links", [])
    affected = {
        str(item.get("requirement_id") or "").strip()
        for item in links if isinstance(item, dict)
        and str(item.get("target_id") or "").strip() in normalized_targets
        and str(item.get("requirement_id") or "").strip()
    }
    if not affected:
        return []
    path = run_path / "result" / _STATE_FILE
    state = read_json(path, {})
    current = {
        str(item).strip()
        for item in state.get("requirement_ids", []) if str(item).strip()
    }
    current.update(affected)
    targets = {
        str(item).strip()
        for item in state.get("target_ids", []) if str(item).strip()
    }
    targets.update(normalized_targets)
    write_json(
        path,
        {
            "requirement_ids": sorted(current),
            "target_ids": sorted(targets),
            "reason": "linked targets changed after traceability was written",
        },
    )
    return sorted(affected)


def clear_traceability_dirty(run_path: Path, requirement_ids: Iterable[str]) -> list[str]:
    path = run_path / "result" / _STATE_FILE
    state = read_json(path, {})
    current = {
        str(item).strip()
        for item in state.get("requirement_ids", []) if str(item).strip()
    }
    current.difference_update(
        str(item).strip() for item in requirement_ids if str(item).strip()
    )
    if current:
        state["requirement_ids"] = sorted(current)
        write_json(path, state)
    else:
        path.unlink(missing_ok=True)
    return sorted(current)


def traceability_dirty_errors(run_path: Path) -> list[str]:
    state = read_json(run_path / "result" / _STATE_FILE, {})
    requirement_ids = [
        str(item).strip()
        for item in state.get("requirement_ids", []) if str(item).strip()
    ]
    if not requirement_ids:
        return []
    return [
        "Traceability must be reviewed only for requirements whose linked targets changed after the last traceability write: "
        + ", ".join(requirement_ids[:40])
    ]
