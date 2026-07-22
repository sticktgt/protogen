from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema import storage


def rebuild_index(root: Path) -> dict[str, Any]:
    entities = []
    for item in storage.list_entities(root):
        details = item.get("details", {})
        fields = details.get("fields", [])
        entities.append({
            "id": details.get("id") or item.get("id"),
            "title": details.get("title") or item.get("title"),
            "description": details.get("description", ""),
            "field_count": len(fields),
            "fields": [
                {
                    "id": field.get("id"),
                    "title": field.get("title"),
                    "type": field.get("type"),
                    "required": bool(field.get("required", False)),
                }
                for field in fields
            ],
        })
    index = {
        "schema": storage.read_schema(root),
        "entities": entities,
        "relations": storage.read_relations(root).get("relations", []),
        "dictionaries": storage.read_dictionaries(root).get("dictionaries", []),
    }
    storage.write_index(root, index)
    return index
