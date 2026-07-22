from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema import storage
from backend.modules.data_schema.index_builder import rebuild_index


def read_summary(root: Path) -> dict[str, Any]:
    index = rebuild_index(root)
    entities = storage.list_entities(root)
    relations = storage.read_relations(root).get("relations", [])
    field_count = sum(len(item.get("details", {}).get("fields", [])) for item in entities)
    requirements_data = storage.read_requirements(root)
    return {
        "schema": storage.read_schema(root),
        "entities": entities,
        "relations": relations,
        "dictionaries": storage.read_dictionaries(root).get("dictionaries", []),
        "requirement_links": storage.read_requirement_links(root).get("links", []),
        "ui_links": storage.read_ui_links(root).get("links", []),
        "api_links": storage.read_api_links(root).get("links", []),
        "code_links": storage.read_code_links(root).get("links", []),
        "requirements": requirements_data.get("requirements", []),
        "requirement_groups": requirements_data.get("groups", []),
        "requirement_projects": requirements_data.get("projects", []),
        "index": index,
        "stats": {
            "entity_count": len(entities),
            "field_count": field_count,
            "relation_count": len(relations),
            "requirement_link_count": len(storage.read_requirement_links(root).get("links", [])),
            "ui_link_count": len(storage.read_ui_links(root).get("links", [])),
            "api_link_count": len(storage.read_api_links(root).get("links", [])),
            "code_link_count": len(storage.read_code_links(root).get("links", [])),
        },
    }
