from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema import storage
from backend.modules.data_schema.ids import make_unique_id
from backend.modules.data_schema.index_builder import rebuild_index

CARDINALITIES = {"one_to_one", "one_to_many", "many_to_one", "many_to_many"}


def create_relation(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    relations = storage.read_relations(root)
    existing_ids = [item.get("id", "") for item in relations.get("relations", [])]
    seed = payload.get("id") or payload.get("title") or f"{payload.get('source_entity', 'entity')}_{payload.get('target_entity', 'entity')}"
    relation_id = make_unique_id(seed, existing_ids, fallback="relation")
    payload = {**payload, "id": relation_id}
    if any(item.get("id") == relation_id for item in relations.get("relations", [])):
        raise ValueError("Relation already exists")
    _validate_relation(root, payload)
    relation = _relation_from_payload(payload)
    relations.setdefault("relations", []).append(relation)
    storage.write_relations(root, relations)
    rebuild_index(root)
    return relation


def update_relation(root: Path, relation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    relations = storage.read_relations(root)
    relation = _find_relation(relations, relation_id)
    if not relation:
        raise ValueError("Relation not found")
    updated = {**relation, **payload}
    _validate_relation(root, updated)
    for key in ("title", "source_entity", "target_entity", "cardinality", "description"):
        if key in payload:
            relation[key] = payload[key]
    storage.write_relations(root, relations)
    rebuild_index(root)
    return relation


def delete_relation(root: Path, relation_id: str) -> None:
    relations = storage.read_relations(root)
    before = len(relations.get("relations", []))
    relations["relations"] = [item for item in relations.get("relations", []) if item.get("id") != relation_id]
    if len(relations["relations"]) == before:
        raise ValueError("Relation not found")
    storage.write_relations(root, relations)
    rebuild_index(root)


def _relation_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": payload["id"],
        "title": payload["title"],
        "source_entity": payload["source_entity"],
        "target_entity": payload["target_entity"],
        "cardinality": payload.get("cardinality", "one_to_many"),
        "description": payload.get("description", ""),
    }


def _validate_relation(root: Path, payload: dict[str, Any]) -> None:
    if payload.get("cardinality", "one_to_many") not in CARDINALITIES:
        raise ValueError("Unsupported cardinality")
    for entity_id in (payload.get("source_entity"), payload.get("target_entity")):
        if not storage.read_entity(root, entity_id or ""):
            raise ValueError(f"Entity not found: {entity_id}")


def _find_relation(relations: dict[str, Any], relation_id: str) -> dict[str, Any] | None:
    for relation in relations.get("relations", []):
        if relation.get("id") == relation_id:
            return relation
    return None
