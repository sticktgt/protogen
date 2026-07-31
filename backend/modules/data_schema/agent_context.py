from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_requirement_context import compact_requirements
from backend.modules.data_schema.agent_target_references import canonical_reference_catalog
from backend.modules.data_schema.files import read_json, write_json
from backend.modules.data_schema.storage import (
    read_dictionaries,
    read_relations,
    read_schema,
)


def write_compact_agent_inputs(*, run_root: Path) -> None:
    context = build_synchronization_context(run_root)
    write_json(run_root / "input" / "requirements.agent.json", context["requirements"])
    write_json(run_root / "input" / "data_schema_context.json", context["data_schema"])
    write_json(run_root / "input" / "synchronization_context.json", context)


def build_synchronization_context(run_root: Path) -> dict[str, Any]:
    requirements = compact_requirements(
        read_json(run_root / "input" / "requirements.json", {"requirements": []})
    )
    validation = read_json(run_root / "result" / "validation_errors.json", {})
    run = read_json(run_root / "run.json", {})
    config = run.get("config") if isinstance(run, dict) else {}
    domain = config.get("domain", {}) if isinstance(config, dict) else {}
    logical_types = domain.get("logical_types", []) if isinstance(domain, dict) else []
    cardinalities = domain.get("cardinalities", []) if isinstance(domain, dict) else []
    return {
        "task": read_json(run_root / "input" / "task.json", {}),
        "requirements": requirements,
        "data_schema": build_agent_data_schema_context(
            run_root / "working" / "data_schema"
        ),
        "canonical_references": canonical_reference_catalog(
            run_root / "working" / "data_schema"
        ),
        "logical_types": list(logical_types) if isinstance(logical_types, list) else [],
        "cardinalities": list(cardinalities) if isinstance(cardinalities, list) else [],
        "validation": validation if isinstance(validation, dict) else {},
    }


def build_agent_data_schema_context(schema_root: Path) -> dict[str, Any]:
    """Return the editable logical schema without unrelated link documents."""
    schema = read_schema(schema_root)
    entities: dict[str, Any] = {}
    for item in schema.get("entities", []):
        if not isinstance(item, dict):
            continue
        entity_id = str(item.get("id") or "")
        if not entity_id:
            continue
        entity_file = str(item.get("file") or f"entities/{entity_id}.json")
        entities[entity_id] = read_json(schema_root / entity_file, {})
    return {
        "schema": schema,
        "entities": entities,
        "relations": read_relations(schema_root),
        "dictionaries": read_dictionaries(schema_root),
    }


def build_data_schema_context(schema_root: Path) -> dict[str, Any]:
    """Return the complete schema context used by diagnostics and review helpers."""
    from backend.modules.data_schema.storage import (
        read_api_links,
        read_code_links,
        read_requirement_links,
        read_ui_links,
    )

    context = build_agent_data_schema_context(schema_root)
    return {
        **context,
        "requirement_data_links": read_requirement_links(schema_root),
        "ui_data_links": read_ui_links(schema_root),
        "api_data_links": read_api_links(schema_root),
        "code_links": read_code_links(schema_root),
    }
