from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_target_references import (
    canonical_references_for_core,
    canonical_references_for_dictionaries,
    canonical_references_for_relations,
)
from backend.modules.data_schema.agent_write_integrity import require_exact_relation_entities
from backend.modules.data_schema.files import read_json, write_json
from backend.modules.data_schema.index_builder import rebuild_index


def patch_schema_core(
    *,
    working_root: Path,
    schema_patch: dict[str, Any] | None,
    entities: list[dict[str, Any]],
) -> dict[str, Any]:
    schema = read_json(working_root / "schema.json", {})
    registry = [
        item
        for item in schema.get("entities", [])
        if isinstance(item, dict) and item.get("id")
    ]
    registry_by_id = {str(item.get("id")): dict(item) for item in registry}
    dictionary_ids = _dictionary_ids(working_root)
    written: list[dict[str, Any]] = []

    if schema_patch:
        if "title" in schema_patch:
            schema["title"] = _required_text(schema_patch["title"], label="schema title")
        if "description" in schema_patch:
            schema["description"] = str(schema_patch["description"] or "")

    for patch in entities:
        entity_id = str(patch.get("id") or "").strip()
        if entity_id not in registry_by_id:
            raise ValueError(f"Unknown entity ID {entity_id!r}; patch accepts existing IDs only")
        path = working_root / "entities" / f"{entity_id}.json"
        current = read_json(path, {})
        if not isinstance(current, dict) or str(current.get("id") or "") != entity_id:
            raise ValueError(f"Entity file for {entity_id!r} is missing or inconsistent")

        if "title" in patch:
            current["title"] = _required_text(
                patch["title"], label=f"entity {entity_id} title"
            )
        if "description" in patch:
            current["description"] = str(patch["description"] or "")

        fields = [item for item in current.get("fields", []) if isinstance(item, dict)]
        fields_by_id = {
            str(item.get("id")): dict(item)
            for item in fields
            if item.get("id")
        }
        field_order = [str(item.get("id")) for item in fields if item.get("id")]
        for field_patch in patch.get("fields", []):
            field_id = str(field_patch.get("id") or "").strip()
            if not field_id:
                raise ValueError(f"Entity {entity_id}: field patch requires an exact id")
            is_new = field_id not in fields_by_id
            if is_new:
                field = {
                    "id": field_id,
                    "title": _required_text(
                        field_patch.get("title"),
                        label=f"new field {entity_id}.{field_id} title",
                    ),
                    "type": str(field_patch.get("type") or "string"),
                    "required": bool(field_patch.get("required", False)),
                    "description": str(field_patch.get("description") or ""),
                }
            else:
                field = fields_by_id[field_id]
            for key in ("title", "type", "required", "description", "dictionary_id"):
                if key not in field_patch:
                    continue
                if key == "required":
                    field[key] = bool(field_patch[key])
                elif key in {"title", "type"}:
                    field[key] = _required_text(
                        field_patch[key],
                        label=f"field {entity_id}.{field_id} {key}",
                    )
                elif key == "dictionary_id":
                    value = str(field_patch[key] or "").strip()
                    if value:
                        field[key] = value
                    else:
                        field.pop(key, None)
                else:
                    field[key] = str(field_patch[key] or "")
            _validate_field_dictionary_reference(
                entity_id=entity_id,
                field=field,
                dictionary_ids=dictionary_ids,
            )
            fields_by_id[field_id] = field
            if is_new:
                field_order.append(field_id)

        current["fields"] = [fields_by_id[field_id] for field_id in field_order]
        write_json(path, current)
        registry_by_id[entity_id]["title"] = str(current.get("title") or "")
        written.append(
            {
                "id": entity_id,
                "title": str(current.get("title") or ""),
                "fields": [item.get("id") for item in current["fields"]],
            }
        )

    schema["entities"] = [registry_by_id[str(item["id"])] for item in registry]
    write_json(working_root / "schema.json", schema)
    rebuild_index(working_root)
    return {
        "patched": written,
        "canonical_references": canonical_references_for_core(written),
    }


def patch_dictionaries(
    *,
    working_root: Path,
    dictionaries: list[dict[str, Any]],
) -> dict[str, Any]:
    document = read_json(working_root / "dictionaries.json", {"dictionaries": []})
    items = [item for item in document.get("dictionaries", []) if isinstance(item, dict)]
    by_id = {str(item.get("id")): dict(item) for item in items if item.get("id")}
    order = [str(item.get("id")) for item in items if item.get("id")]
    written: list[dict[str, Any]] = []

    for patch in dictionaries:
        dictionary_id = str(patch.get("id") or "").strip()
        if dictionary_id not in by_id:
            raise ValueError(
                f"Unknown dictionary ID {dictionary_id!r}; patch accepts existing IDs only"
            )
        current = by_id[dictionary_id]
        if "title" in patch:
            current["title"] = _required_text(
                patch["title"], label=f"dictionary {dictionary_id} title"
            )
        if "description" in patch:
            current["description"] = str(patch["description"] or "")
        values = [item for item in current.get("values", []) if isinstance(item, dict)]
        values_by_id = {
            str(item.get("id")): dict(item)
            for item in values
            if item.get("id")
        }
        value_order = [str(item.get("id")) for item in values if item.get("id")]
        for value_patch in patch.get("values", []):
            value_id = str(value_patch.get("id") or "").strip()
            if not value_id:
                raise ValueError(f"Dictionary {dictionary_id}: value patch requires an exact id")
            is_new = value_id not in values_by_id
            if is_new:
                value = {
                    "id": value_id,
                    "title": _required_text(
                        value_patch.get("title"),
                        label=f"new dictionary value {dictionary_id}.{value_id} title",
                    ),
                    "description": str(value_patch.get("description") or ""),
                }
            else:
                value = values_by_id[value_id]
            if "title" in value_patch:
                value["title"] = _required_text(
                    value_patch["title"],
                    label=f"dictionary value {dictionary_id}.{value_id} title",
                )
            if "description" in value_patch:
                value["description"] = str(value_patch["description"] or "")
            values_by_id[value_id] = value
            if is_new:
                value_order.append(value_id)
        current["values"] = [values_by_id[value_id] for value_id in value_order]
        by_id[dictionary_id] = current
        written.append(
            {
                "id": dictionary_id,
                "title": str(current.get("title") or ""),
                "values": [item.get("id") for item in current["values"]],
            }
        )

    write_json(
        working_root / "dictionaries.json",
        {"dictionaries": [by_id[dictionary_id] for dictionary_id in order]},
    )
    rebuild_index(working_root)
    return {
        "patched": written,
        "canonical_references": canonical_references_for_dictionaries(written),
    }


def patch_relations(
    *,
    working_root: Path,
    relations: list[dict[str, Any]],
) -> dict[str, Any]:
    document = read_json(working_root / "relations.json", {"relations": []})
    items = [item for item in document.get("relations", []) if isinstance(item, dict)]
    by_id = {str(item.get("id")): dict(item) for item in items if item.get("id")}
    order = [str(item.get("id")) for item in items if item.get("id")]
    written: list[dict[str, Any]] = []

    for patch in relations:
        relation_id = str(patch.get("id") or "").strip()
        if relation_id not in by_id:
            raise ValueError(
                f"Unknown relation ID {relation_id!r}; patch accepts existing IDs only"
            )
        current = by_id[relation_id]
        for key in ("title", "source_entity", "target_entity", "cardinality"):
            if key in patch:
                current[key] = _required_text(
                    patch[key], label=f"relation {relation_id} {key}"
                )
        if "description" in patch:
            current["description"] = str(patch["description"] or "")
        require_exact_relation_entities(working_root=working_root, relations=[current])
        by_id[relation_id] = current
        written.append(current)

    write_json(
        working_root / "relations.json",
        {"relations": [by_id[relation_id] for relation_id in order]},
    )
    rebuild_index(working_root)
    return {
        "patched": written,
        "canonical_references": canonical_references_for_relations(written),
    }


def _dictionary_ids(working_root: Path) -> set[str]:
    document = read_json(working_root / "dictionaries.json", {"dictionaries": []})
    return {
        str(item.get("id"))
        for item in document.get("dictionaries", [])
        if isinstance(item, dict) and item.get("id")
    }


def _validate_field_dictionary_reference(
    *,
    entity_id: str,
    field: dict[str, Any],
    dictionary_ids: set[str],
) -> None:
    field_id = str(field.get("id") or "")
    field_type = str(field.get("type") or "string")
    dictionary_id = str(field.get("dictionary_id") or "").strip()
    if field_type == "dictionary":
        if not dictionary_id:
            raise ValueError(f"Field {entity_id}.{field_id}: dictionary_id is required")
        if dictionary_id not in dictionary_ids:
            raise ValueError(
                f"Field {entity_id}.{field_id}: unknown dictionary_id {dictionary_id!r}"
            )
        return
    field.pop("dictionary_id", None)


def _required_text(value: Any, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} must be a non-empty string")
    return text
