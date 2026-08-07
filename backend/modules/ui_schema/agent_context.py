from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_requirement_scope import compact_requirements
from backend.modules.ui_schema.agent_pipeline_settings import pipeline_settings
from backend.modules.ui_schema.element_types import element_type_catalog, root_type_ids
from backend.modules.ui_schema.files import read_json, write_json_compact


def write_compact_agent_inputs(
    *,
    run_root: Path,
    agent_config: dict[str, Any] | None = None,
) -> None:
    """Write bounded diagnostic input snapshots for managed pipeline v2."""
    context = build_synchronization_context(run_root, agent_config=agent_config)
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


def build_synchronization_context(
    run_root: Path,
    *,
    agent_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = agent_config if isinstance(agent_config, dict) else {}
    context_config = config.get("context", {})
    requirement_fields = (
        context_config.get("requirement_fields")
        if isinstance(context_config, dict)
        else None
    )
    requirements = compact_requirements(
        run_root,
        fields=requirement_fields if isinstance(requirement_fields, list) else None,
    )
    configured_pipeline = pipeline_settings(config)
    return {
        "task": read_json(run_root / "input" / "task.json", {}),
        "requirements": {
            "total_count": len(requirements),
            "items": requirements,
        },
        "pipeline": {
            "version": 2,
            "analysis_batch_size": configured_pipeline["analysis_batch_size"],
            "audit_batch_size": configured_pipeline["audit_batch_size"],
            "stages": [
                "analysis",
                "planning",
                "apply",
                "audit",
                "correction",
                "structural_check",
                "validation",
            ],
        },
        "ui_schema": build_ui_schema_context(run_root / "working" / "ui_schema"),
        "element_types": build_element_type_context(),
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


def build_element_type_context() -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {"app": [], "page": []}
    for raw in element_type_catalog():
        item = {"id": raw["id"], "kind": raw["kind"]}
        for key in (
            "root_allowed",
            "unique_root",
            "link_source",
            "allowed_children",
            "allowed_parents",
            "review_empty",
        ):
            if key in raw:
                item[key] = raw[key]
        grouped[str(raw["scope"])].append(item)
    grouped["app"].sort(
        key=lambda item: (not bool(item.get("root_allowed")), str(item.get("id")))
    )
    grouped["page"].sort(key=lambda item: str(item.get("id")))
    return {
        "app_root_type_ids": sorted(root_type_ids(scope="app")),
        "app": grouped["app"],
        "page": grouped["page"],
    }
