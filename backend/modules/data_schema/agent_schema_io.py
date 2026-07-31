from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from backend.modules.data_schema.files import read_json, write_json
from backend.modules.data_schema.ids import make_unique_id
from backend.modules.data_schema.index_builder import rebuild_index
from backend.modules.data_schema.agent_target_references import (
    canonical_references_for_core,
    canonical_references_for_dictionaries,
    canonical_references_for_relations,
)
from backend.modules.data_schema.agent_write_integrity import (
    require_exact_dictionary_references,
    require_exact_relation_entities,
)


def recoverable_tool_result(operation: Callable[[], dict[str, Any]]) -> str:
    try:
        result = operation()
        return json.dumps({"ok": True, **result}, ensure_ascii=False)
    except (ValueError, TypeError, KeyError) as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


def write_dictionaries(*, working_root: Path, dictionaries: list[dict[str, Any]]) -> dict[str, Any]:
    document = read_json(working_root / "dictionaries.json", {"dictionaries": []})
    existing = {
        str(item.get("id")): item
        for item in document.get("dictionaries", [])
        if isinstance(item, dict) and item.get("id")
    }
    ordered_ids = [
        str(item.get("id"))
        for item in document.get("dictionaries", [])
        if isinstance(item, dict) and item.get("id")
    ]
    used_ids = set(existing)
    written: list[dict[str, Any]] = []
    for payload in dictionaries:
        if not isinstance(payload, dict):
            raise ValueError("Each dictionary must be an object")
        title = str(payload.get("title") or "").strip()
        if not title:
            raise ValueError("Dictionary title is required")
        requested_id = str(payload.get("id") or "").strip()
        dictionary_id = requested_id if requested_id in existing else make_unique_id(
            requested_id or title, used_ids, fallback="dictionary"
        )
        used_ids.add(dictionary_id)
        current = dict(existing.get(dictionary_id) or {})
        current.update({
            "id": dictionary_id,
            "title": title,
            "description": str(payload.get("description") or current.get("description") or ""),
        })
        existing_values = {
            str(item.get("id")): item
            for item in current.get("values", [])
            if isinstance(item, dict) and item.get("id")
        }
        value_order = [
            str(item.get("id"))
            for item in current.get("values", [])
            if isinstance(item, dict) and item.get("id")
        ]
        used_value_ids = set(existing_values)
        for value_payload in payload.get("values", []):
            if not isinstance(value_payload, dict):
                raise ValueError(f"Dictionary {dictionary_id}: each value must be an object")
            value_title = str(value_payload.get("title") or "").strip()
            if not value_title:
                raise ValueError(f"Dictionary {dictionary_id}: value title is required")
            requested_value_id = str(value_payload.get("id") or "").strip()
            value_id = (
                requested_value_id
                if requested_value_id in existing_values
                else make_unique_id(requested_value_id or value_title, used_value_ids, fallback="value")
            )
            used_value_ids.add(value_id)
            value = dict(existing_values.get(value_id) or {})
            value.update({"id": value_id, "title": value_title})
            if "description" in value_payload:
                value["description"] = str(value_payload.get("description") or "")
            existing_values[value_id] = value
            if value_id not in value_order:
                value_order.append(value_id)
        current["values"] = [existing_values[value_id] for value_id in value_order]
        existing[dictionary_id] = current
        if dictionary_id not in ordered_ids:
            ordered_ids.append(dictionary_id)
        written.append({
            "id": dictionary_id,
            "title": title,
            "values": [item.get("id") for item in current["values"]],
        })
    write_json(working_root / "dictionaries.json", {"dictionaries": [existing[item] for item in ordered_ids]})
    rebuild_index(working_root)
    return {
        "written": written,
        "dictionary_count": len(ordered_ids),
        "canonical_references": canonical_references_for_dictionaries(written),
    }


def write_schema_core(
    *,
    working_root: Path,
    schema: dict[str, Any] | None,
    entities: list[dict[str, Any]],
) -> dict[str, Any]:
    require_exact_dictionary_references(
        working_root=working_root,
        entities=entities,
    )
    schema_doc = read_json(working_root / "schema.json", {})
    if schema:
        for key in ("title", "description"):
            if key in schema:
                schema_doc[key] = str(schema.get(key) or "")
    schema_doc.setdefault("schema_version", "0.1")
    registry = [item for item in schema_doc.get("entities", []) if isinstance(item, dict)]
    registry_by_id = {str(item.get("id")): dict(item) for item in registry if item.get("id")}
    ordered_ids = [str(item.get("id")) for item in registry if item.get("id")]
    used_entity_ids = set(registry_by_id)
    written: list[dict[str, Any]] = []

    for payload in entities:
        if not isinstance(payload, dict):
            raise ValueError("Each entity must be an object")
        title = str(payload.get("title") or "").strip()
        if not title:
            raise ValueError("Entity title is required")
        requested_id = str(payload.get("id") or "").strip()
        entity_id = requested_id if requested_id in registry_by_id else make_unique_id(
            requested_id or title, used_entity_ids, fallback="entity"
        )
        used_entity_ids.add(entity_id)
        path = working_root / "entities" / f"{entity_id}.json"
        current = read_json(path, {}) if path.is_file() else {}
        current.update({
            "id": entity_id,
            "title": title,
            "description": str(payload.get("description") or current.get("description") or ""),
        })
        existing_fields = {
            str(item.get("id")): item
            for item in current.get("fields", [])
            if isinstance(item, dict) and item.get("id")
        }
        field_order = [
            str(item.get("id"))
            for item in current.get("fields", [])
            if isinstance(item, dict) and item.get("id")
        ]
        used_field_ids = set(existing_fields)
        for field_payload in payload.get("fields", []):
            if not isinstance(field_payload, dict):
                raise ValueError(f"Entity {entity_id}: each field must be an object")
            field_title = str(field_payload.get("title") or "").strip()
            if not field_title:
                raise ValueError(f"Entity {entity_id}: field title is required")
            requested_field_id = str(field_payload.get("id") or "").strip()
            field_id = (
                requested_field_id
                if requested_field_id in existing_fields
                else make_unique_id(requested_field_id or field_title, used_field_ids, fallback="field")
            )
            used_field_ids.add(field_id)
            field = dict(existing_fields.get(field_id) or {})
            field.update({
                "id": field_id,
                "title": field_title,
                "type": str(field_payload.get("type") or field.get("type") or "string"),
                "required": bool(field_payload.get("required", field.get("required", False))),
                "description": str(field_payload.get("description") or field.get("description") or ""),
            })
            if field["type"] == "dictionary" and field_payload.get("dictionary_id"):
                field["dictionary_id"] = str(field_payload["dictionary_id"])
            elif field["type"] != "dictionary":
                field.pop("dictionary_id", None)
            existing_fields[field_id] = field
            if field_id not in field_order:
                field_order.append(field_id)
        current["fields"] = [existing_fields[field_id] for field_id in field_order]
        write_json(path, current)
        registry_by_id[entity_id] = {
            "id": entity_id,
            "title": title,
            "file": f"entities/{entity_id}.json",
        }
        if entity_id not in ordered_ids:
            ordered_ids.append(entity_id)
        written.append({
            "id": entity_id,
            "title": title,
            "fields": [item.get("id") for item in current["fields"]],
        })

    schema_doc["entities"] = [registry_by_id[item] for item in ordered_ids]
    write_json(working_root / "schema.json", schema_doc)
    rebuild_index(working_root)
    return {
        "written": written,
        "entity_count": len(ordered_ids),
        "canonical_references": canonical_references_for_core(written),
    }


def write_relations(*, working_root: Path, relations: list[dict[str, Any]]) -> dict[str, Any]:
    require_exact_relation_entities(
        working_root=working_root,
        relations=relations,
    )
    document = read_json(working_root / "relations.json", {"relations": []})
    existing = {
        str(item.get("id")): item
        for item in document.get("relations", [])
        if isinstance(item, dict) and item.get("id")
    }
    ordered_ids = [
        str(item.get("id"))
        for item in document.get("relations", [])
        if isinstance(item, dict) and item.get("id")
    ]
    used_ids = set(existing)
    written: list[dict[str, Any]] = []
    for payload in relations:
        if not isinstance(payload, dict):
            raise ValueError("Each relation must be an object")
        title = str(payload.get("title") or "").strip()
        source = str(payload.get("source_entity") or "").strip()
        target = str(payload.get("target_entity") or "").strip()
        if not title or not source or not target:
            raise ValueError("Relation title, source_entity and target_entity are required")
        requested_id = str(payload.get("id") or "").strip()
        relation_id = requested_id if requested_id in existing else make_unique_id(
            requested_id or title, used_ids, fallback="relation"
        )
        used_ids.add(relation_id)
        relation = dict(existing.get(relation_id) or {})
        relation.update({
            "id": relation_id,
            "title": title,
            "source_entity": source,
            "target_entity": target,
            "cardinality": str(payload.get("cardinality") or relation.get("cardinality") or "one_to_many"),
            "description": str(payload.get("description") or relation.get("description") or ""),
        })
        existing[relation_id] = relation
        if relation_id not in ordered_ids:
            ordered_ids.append(relation_id)
        written.append(relation)
    write_json(working_root / "relations.json", {"relations": [existing[item] for item in ordered_ids]})
    rebuild_index(working_root)
    return {
        "written": written,
        "relation_count": len(ordered_ids),
        "canonical_references": canonical_references_for_relations(written),
    }


def write_requirement_links(*, working_root: Path, links: list[dict[str, Any]]) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    semantic: set[tuple[str, str, str]] = set()
    for payload in links:
        if not isinstance(payload, dict):
            raise ValueError("Each requirement link must be an object")
        requirement_id = str(payload.get("requirement_id") or "").strip()
        target_type = str(payload.get("target_type") or "").strip()
        target_id = str(payload.get("target_id") or "").strip()
        if not requirement_id or not target_type or not target_id:
            raise ValueError("requirement_id, target_type and target_id are required")
        key = (requirement_id, target_type, target_id)
        if key in semantic:
            continue
        semantic.add(key)
        link_id = make_unique_id(
            str(payload.get("id") or f"{requirement_id}_{target_type}_{target_id}"),
            used_ids,
            fallback="req_data_link",
        )
        used_ids.add(link_id)
        normalized.append({
            "id": link_id,
            "requirement_id": requirement_id,
            "target_type": target_type,
            "target_id": target_id,
            "relation": str(payload.get("relation") or "defines"),
            "implementation_status": str(payload.get("implementation_status") or "planned"),
        })
    write_json(
        working_root / "mappings" / "requirement_data_links.json",
        {"links": normalized},
    )
    return {
        "requirement_link_count": len(normalized),
        "covered_requirement_count": len({item["requirement_id"] for item in normalized}),
    }
