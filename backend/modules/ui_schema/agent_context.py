from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.element_types import element_type_catalog
from backend.modules.ui_schema.files import read_json, write_json_compact


def write_compact_agent_inputs(*, run_root: Path) -> None:
    """Create compact diagnostic copies of the bounded synchronization context."""
    context = build_synchronization_context(run_root)
    write_json_compact(
        run_root / "input" / "requirements.agent.json",
        context["requirements"],
    )
    write_json_compact(
        run_root / "input" / "ui_schema_context.json",
        context["ui_schema"],
    )
    write_json_compact(
        run_root / "input" / "synchronization_context.json",
        context,
    )


def build_synchronization_context(run_root: Path) -> dict[str, Any]:
    """Build the current context returned by the single read-only domain tool.

    It is rebuilt on every invocation, so a validation-repair invocation sees
    the latest temporary schema instead of the initial snapshot.
    """
    requirements = read_json(
        run_root / "input" / "requirements.json",
        {"requirements": []},
    )
    validation = read_json(run_root / "result" / "validation_errors.json", {})
    return {
        "task": read_json(run_root / "input" / "task.json", {}),
        "requirements": requirements,
        "ui_schema": build_ui_schema_context(run_root / "working" / "ui_schema"),
        "element_types": [dict(item) for item in element_type_catalog()],
        "agent_report": read_json(run_root / "result" / "agent_report.json", {}),
        "validation": validation if isinstance(validation, dict) else {},
    }


def build_ui_schema_context(schema_root: Path) -> dict[str, Any]:
    pages: dict[str, Any] = {}
    pages_root = schema_root / "pages"
    if pages_root.is_dir():
        for path in sorted(pages_root.glob("*.json")):
            pages[path.name] = read_json(path, {})
    return {
        "app": read_json(schema_root / "app.json", {}),
        "schema": read_json(schema_root / "schema.json", {}),
        "links": read_json(schema_root / "links.json", {"links": []}),
        "requirement_ui_links": read_json(
            schema_root / "mappings" / "requirement_ui_links.json",
            {"links": []},
        ),
        "pages": pages,
    }

