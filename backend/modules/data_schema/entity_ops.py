from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema import storage
from backend.modules.data_schema.ids import make_unique_id
from backend.modules.data_schema.index_builder import rebuild_index


LOGICAL_TYPES = {
    "string", "text", "integer", "decimal", "boolean",
    "date", "datetime", "uuid", "dictionary", "json",
}


def update_schema(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    schema = storage.read_schema(root)
    for key in ("title", "description"):
        if key in payload:
            schema[key] = payload[key]
    storage.write_schema(root, schema)
    rebuild_index(root)
    return schema


def create_entity(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    schema = storage.read_schema(root)
    existing_ids = [item.get("id", "") for item in schema.get("entities", [])]
    entity_id = make_unique_id(payload.get("id") or payload["title"], existing_ids, fallback="entity")
    if storage.read_entity(root, entity_id):
        raise ValueError("Entity already exists")
    entity = {
        "id": entity_id,
        "title": payload["title"],
        "description": payload.get("description", ""),
        "fields": [],
    }
    schema.setdefault("entities", []).append({
        "id": entity_id,
        "title": entity["title"],
        "file": f"entities/{entity_id}.json",
    })
    storage.write_schema(root, schema)
    storage.write_entity(root, entity)
    rebuild_index(root)
    return entity


def update_entity(root: Path, entity_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    entity = storage.read_entity(root, entity_id)
    if not entity:
        raise ValueError("Entity not found")
    for key in ("title", "description"):
        if key in payload:
            entity[key] = payload[key]
    storage.write_entity(root, entity)
    schema = storage.read_schema(root)
    for item in schema.get("entities", []):
        if item.get("id") == entity_id and "title" in payload:
            item["title"] = payload["title"]
    storage.write_schema(root, schema)
    rebuild_index(root)
    return entity


def delete_entity(root: Path, entity_id: str) -> None:
    entity = storage.read_entity(root, entity_id)
    if not entity:
        raise ValueError("Entity not found")
    if entity.get("fields"):
        raise ValueError("Delete entity fields first")
    relations = storage.read_relations(root).get("relations", [])
    if any(item.get("source_entity") == entity_id or item.get("target_entity") == entity_id for item in relations):
        raise ValueError("Delete entity relations first")
    schema = storage.read_schema(root)
    schema["entities"] = [item for item in schema.get("entities", []) if item.get("id") != entity_id]
    storage.write_schema(root, schema)
    storage.delete_entity_file(root, entity_id)
    rebuild_index(root)


def add_field(root: Path, entity_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    entity = storage.read_entity(root, entity_id)
    if not entity:
        raise ValueError("Entity not found")
    field_id = make_unique_id(payload.get("id") or payload["title"], [item.get("id", "") for item in entity.get("fields", [])], fallback="field")
    payload = {**payload, "id": field_id}
    if any(item.get("id") == field_id for item in entity.get("fields", [])):
        raise ValueError("Field already exists")
    field_type = payload.get("type", "string")
    if field_type not in LOGICAL_TYPES:
        raise ValueError("Unsupported logical type")
    field = _field_from_payload(payload)
    entity.setdefault("fields", []).append(field)
    storage.write_entity(root, entity)
    rebuild_index(root)
    return field


def update_field(root: Path, entity_id: str, field_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    entity = storage.read_entity(root, entity_id)
    if not entity:
        raise ValueError("Entity not found")
    field = _find_field(entity, field_id)
    if not field:
        raise ValueError("Field not found")
    if "type" in payload and payload["type"] not in LOGICAL_TYPES:
        raise ValueError("Unsupported logical type")
    for key in ("title", "type", "required", "description", "dictionary_id"):
        if key in payload:
            field[key] = payload[key]
    if field.get("type") != "dictionary":
        field.pop("dictionary_id", None)
    storage.write_entity(root, entity)
    rebuild_index(root)
    return field


def delete_field(root: Path, entity_id: str, field_id: str) -> None:
    entity = storage.read_entity(root, entity_id)
    if not entity:
        raise ValueError("Entity not found")
    before = len(entity.get("fields", []))
    entity["fields"] = [item for item in entity.get("fields", []) if item.get("id") != field_id]
    if len(entity["fields"]) == before:
        raise ValueError("Field not found")
    storage.write_entity(root, entity)
    rebuild_index(root)


def _field_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    field = {
        "id": payload["id"],
        "title": payload["title"],
        "type": payload.get("type", "string"),
        "required": bool(payload.get("required", False)),
        "description": payload.get("description", ""),
    }
    if field["type"] == "dictionary" and payload.get("dictionary_id"):
        field["dictionary_id"] = payload["dictionary_id"]
    return field


def _find_field(entity: dict[str, Any], field_id: str) -> dict[str, Any] | None:
    for field in entity.get("fields", []):
        if field.get("id") == field_id:
            return field
    return None
