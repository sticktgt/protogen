from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.files import read_json
from backend.modules.data_schema.storage import read_dictionaries, read_relations, read_schema


def compact_schema_catalog(schema_root: Path) -> dict[str, Any]:
    """Return semantic labels plus exact compact target IDs for LLM selection."""

    schema = read_schema(schema_root)
    entities: list[dict[str, Any]] = []
    for ref in schema.get("entities", []):
        if not isinstance(ref, dict):
            continue
        entity_id = str(ref.get("id") or "").strip()
        if not entity_id:
            continue
        entity = read_json(
            schema_root / str(ref.get("file") or f"entities/{entity_id}.json"),
            {},
        )
        entities.append(
            {
                "target_type": "entity",
                "target_id": entity_id,
                "title": entity.get("title", ""),
                "description": entity.get("description", ""),
                "fields": [
                    {
                        "target_type": "field",
                        "target_id": f"{entity_id}.{item.get('id', '')}",
                        "title": item.get("title", ""),
                        "type": item.get("type", ""),
                        "required": bool(item.get("required")),
                        "description": item.get("description", ""),
                        "dictionary_id": item.get("dictionary_id"),
                    }
                    for item in entity.get("fields", [])
                    if isinstance(item, dict) and str(item.get("id") or "").strip()
                ],
            }
        )

    relations: list[dict[str, Any]] = []
    for relation in read_relations(schema_root).get("relations", []):
        if not isinstance(relation, dict) or not str(relation.get("id") or "").strip():
            continue
        relation_id = str(relation["id"])
        relations.append(
            {
                "target_type": "relation",
                "target_id": relation_id,
                **{key: value for key, value in relation.items() if key != "id"},
            }
        )

    dictionaries: list[dict[str, Any]] = []
    for dictionary in read_dictionaries(schema_root).get("dictionaries", []):
        if not isinstance(dictionary, dict) or not str(dictionary.get("id") or "").strip():
            continue
        dictionary_id = str(dictionary["id"])
        dictionaries.append(
            {
                "target_type": "dictionary",
                "target_id": dictionary_id,
                "title": dictionary.get("title", ""),
                "description": dictionary.get("description", ""),
                "values": [
                    {
                        "target_type": "dictionary_value",
                        "target_id": f"{dictionary_id}.{value.get('id', '')}",
                        "title": value.get("title", ""),
                        "description": value.get("description", ""),
                    }
                    for value in dictionary.get("values", [])
                    if isinstance(value, dict) and str(value.get("id") or "").strip()
                ],
            }
        )

    return {
        "schema": {
            "title": schema.get("title", ""),
            "description": schema.get("description", ""),
        },
        "entities": entities,
        "relations": relations,
        "dictionaries": dictionaries,
    }
