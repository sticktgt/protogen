from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.files import read_json


def preservation_validation(
    base_root: Path,
    working_root: Path,
    validation: dict[str, Any],
) -> dict[str, Any]:
    errors = list(validation.get("errors", []))
    missing = find_missing_base_objects(base_root, working_root)
    errors.extend(f"Existing base object was removed: {item}" for item in missing)
    result = dict(validation)
    result["errors"] = errors
    result["valid"] = not errors
    result["preservation"] = {"missing_base_objects": missing}
    return result


def find_missing_base_objects(base_root: Path, working_root: Path) -> list[str]:
    base = collect_schema_ids(base_root)
    working = collect_schema_ids(working_root)
    missing: list[str] = []
    for object_type in ("entity", "field", "relation", "dictionary", "dictionary_value"):
        for object_id in sorted(base[object_type] - working[object_type]):
            missing.append(f"{object_type}:{object_id}")
    return missing


def collect_schema_ids(root: Path) -> dict[str, set[str]]:
    result = {
        "entity": set(),
        "field": set(),
        "relation": set(),
        "dictionary": set(),
        "dictionary_value": set(),
    }
    schema = read_json(root / "schema.json", {"entities": []})
    for item in schema.get("entities", []):
        if not isinstance(item, dict):
            continue
        entity_id = str(item.get("id") or "")
        if not entity_id:
            continue
        result["entity"].add(entity_id)
        entity = read_json(root / str(item.get("file") or f"entities/{entity_id}.json"), {})
        for field in entity.get("fields", []):
            if isinstance(field, dict) and field.get("id"):
                result["field"].add(f"{entity_id}.{field['id']}")
    relations = read_json(root / "relations.json", {"relations": []})
    for item in relations.get("relations", []):
        if isinstance(item, dict) and item.get("id"):
            result["relation"].add(str(item["id"]))
    dictionaries = read_json(root / "dictionaries.json", {"dictionaries": []})
    for dictionary in dictionaries.get("dictionaries", []):
        if not isinstance(dictionary, dict) or not dictionary.get("id"):
            continue
        dictionary_id = str(dictionary["id"])
        result["dictionary"].add(dictionary_id)
        for value in dictionary.get("values", []):
            if isinstance(value, dict) and value.get("id"):
                result["dictionary_value"].add(f"{dictionary_id}.{value['id']}")
    return result
