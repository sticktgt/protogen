from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_requirement_decisions import TraceabilityItem
from backend.modules.ui_schema.agent_requirement_scope import compact_requirements
from backend.modules.ui_schema.files import read_json, write_json

_FILE = "traceability_items.json"


def write_traceability_items(
    result_root: Path,
    *,
    run_path: Path,
    items: list[TraceabilityItem],
    reset: bool = False,
) -> dict[str, Any]:
    current = {} if reset else read_json(result_root / _FILE, {})
    by_id = {
        str(item.get("requirement_id") or ""): dict(item)
        for item in current.get("items", [])
        if isinstance(item, dict) and str(item.get("requirement_id") or "")
    }
    for item in items:
        by_id[item.requirement_id] = item.model_dump(exclude_none=True)
    order = {
        str(item.get("id") or ""): index
        for index, item in enumerate(compact_requirements(run_path, fields=["id"]))
    }
    payload = {
        "items": sorted(
            by_id.values(),
            key=lambda item: order.get(str(item.get("requirement_id") or ""), 10**9),
        )
    }
    write_json(result_root / _FILE, payload)
    return payload


def read_traceability_items(result_root: Path) -> dict[str, dict[str, Any]]:
    data = read_json(result_root / _FILE, {})
    return {
        str(item.get("requirement_id") or ""): dict(item)
        for item in data.get("items", [])
        if isinstance(item, dict) and str(item.get("requirement_id") or "")
    }
