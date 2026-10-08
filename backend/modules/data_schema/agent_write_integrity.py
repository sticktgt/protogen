from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.files import read_json


def require_exact_dictionary_references(
    *,
    working_root: Path,
    entities: list[dict[str, Any]],
) -> None:
    """Reject invalid dictionary references without choosing an alternative target."""
    document = read_json(working_root / "dictionaries.json", {"dictionaries": []})
    dictionary_ids = {
        str(item.get("id"))
        for item in document.get("dictionaries", [])
        if isinstance(item, dict) and item.get("id")
    }
    for entity_index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            continue
        for field_index, field in enumerate(entity.get("fields", [])):
            if not isinstance(field, dict):
                continue
            field_type = str(field.get("type") or "string")
            dictionary_id = field.get("dictionary_id")
            location = f"entities[{entity_index}].fields[{field_index}]"
            if field_type == "dictionary":
                if not isinstance(dictionary_id, str) or not dictionary_id.strip():
                    raise ValueError(
                        f"{location}: dictionary_id is required for dictionary fields"
                    )
                if dictionary_id not in dictionary_ids:
                    raise ValueError(
                        f"{location}: unknown dictionary_id {dictionary_id!r}; "
                        "use an exact ID returned by write_data_schema_dictionaries"
                    )
            elif dictionary_id not in {None, ""}:
                raise ValueError(
                    f"{location}: dictionary_id is allowed only for dictionary fields"
                )


def require_exact_relation_entities(
    *,
    working_root: Path,
    relations: list[dict[str, Any]],
) -> None:
    """Reject relation endpoints that are not exact entity IDs."""
    schema = read_json(working_root / "schema.json", {"entities": []})
    entity_ids = {
        str(item.get("id"))
        for item in schema.get("entities", [])
        if isinstance(item, dict) and item.get("id")
    }
    for index, relation in enumerate(relations):
        if not isinstance(relation, dict):
            continue
        for key in ("source_entity", "target_entity"):
            value = relation.get(key)
            if not isinstance(value, str) or value not in entity_ids:
                raise ValueError(
                    f"relations[{index}].{key}: unknown entity ID {value!r}; "
                    "use an exact ID returned by write_data_schema_core"
                )
