from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.entity_ops import LOGICAL_TYPES
from backend.modules.data_schema.files import read_json
from backend.modules.data_schema.index_builder import rebuild_index
from backend.modules.data_schema.relation_ops import CARDINALITIES

TARGET_TYPES = {"entity", "field", "relation", "dictionary", "dictionary_value"}


def validate_data_schema(
    root: Path,
    *,
    rebuild: bool = False,
    known_requirement_ids: set[str] | None = None,
    logical_types: list[str] | set[str] | tuple[str, ...] | None = None,
    cardinalities: list[str] | set[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    allowed_logical_types = set(logical_types) if logical_types is not None else set(LOGICAL_TYPES)
    allowed_cardinalities = set(cardinalities) if cardinalities is not None else set(CARDINALITIES)
    if not allowed_logical_types:
        errors.append("Agent domain logical_types must not be empty")
    if not allowed_cardinalities:
        errors.append("Agent domain cardinalities must not be empty")

    schema = _read_object(root / "schema.json", errors)
    dictionaries_doc = _read_object(root / "dictionaries.json", errors, default={"dictionaries": []})
    relations_doc = _read_object(root / "relations.json", errors, default={"relations": []})
    requirement_links_doc = _read_object(
        root / "mappings" / "requirement_data_links.json", errors, default={"links": []}
    )
    ui_links_doc = _read_object(root / "mappings" / "ui_data_links.json", errors, default={"links": []})
    api_links_doc = _read_object(root / "mappings" / "api_data_links.json", errors, default={"links": []})
    code_links_doc = _read_object(root / "code_links.json", errors, default={"links": []})

    if not isinstance(schema.get("schema_version"), str) or not schema.get("schema_version"):
        errors.append("schema.json: schema_version must be a non-empty string")
    if not isinstance(schema.get("title"), str) or not schema.get("title", "").strip():
        errors.append("schema.json: title must be a non-empty string")
    registry = schema.get("entities")
    if not isinstance(registry, list):
        errors.append("schema.json: entities must be an array")
        registry = []

    dictionaries = dictionaries_doc.get("dictionaries")
    if not isinstance(dictionaries, list):
        errors.append("dictionaries.json: dictionaries must be an array")
        dictionaries = []
    dictionary_ids: set[str] = set()
    dictionary_value_ids: set[str] = set()
    for index, dictionary in enumerate(dictionaries):
        prefix = f"dictionaries.json:dictionaries[{index}]"
        if not isinstance(dictionary, dict):
            errors.append(f"{prefix}: item must be an object")
            continue
        dictionary_id = _required_id(dictionary, prefix, errors)
        if dictionary_id:
            if dictionary_id in dictionary_ids:
                errors.append(f"{prefix}: duplicate dictionary id {dictionary_id}")
            dictionary_ids.add(dictionary_id)
        if not isinstance(dictionary.get("title"), str) or not dictionary.get("title", "").strip():
            errors.append(f"{prefix}: title must be a non-empty string")
        values = dictionary.get("values")
        if not isinstance(values, list):
            errors.append(f"{prefix}: values must be an array")
            values = []
        local_value_ids: set[str] = set()
        for value_index, value in enumerate(values):
            value_prefix = f"{prefix}.values[{value_index}]"
            if not isinstance(value, dict):
                errors.append(f"{value_prefix}: item must be an object")
                continue
            value_id = _required_id(value, value_prefix, errors)
            if value_id:
                if value_id in local_value_ids:
                    errors.append(f"{value_prefix}: duplicate value id {value_id}")
                local_value_ids.add(value_id)
                if dictionary_id:
                    dictionary_value_ids.add(f"{dictionary_id}.{value_id}")
            if not isinstance(value.get("title"), str) or not value.get("title", "").strip():
                errors.append(f"{value_prefix}: title must be a non-empty string")

    entity_ids: set[str] = set()
    field_ids: set[str] = set()
    registry_files: set[str] = set()
    for index, item in enumerate(registry):
        prefix = f"schema.json:entities[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: item must be an object")
            continue
        entity_id = _required_id(item, prefix, errors)
        if entity_id:
            if entity_id in entity_ids:
                errors.append(f"{prefix}: duplicate entity id {entity_id}")
            entity_ids.add(entity_id)
        file_path = item.get("file")
        expected_file = f"entities/{entity_id}.json" if entity_id else ""
        if not isinstance(file_path, str) or not file_path:
            errors.append(f"{prefix}: file must be a non-empty string")
            continue
        if file_path != expected_file:
            errors.append(f"{prefix}: file must be {expected_file}")
        if file_path in registry_files:
            errors.append(f"{prefix}: duplicate entity file {file_path}")
        registry_files.add(file_path)
        entity = _read_object(root / file_path, errors)
        if entity_id and entity.get("id") != entity_id:
            errors.append(f"{file_path}: id must equal registry id {entity_id}")
        if not isinstance(entity.get("title"), str) or not entity.get("title", "").strip():
            errors.append(f"{file_path}: title must be a non-empty string")
        fields = entity.get("fields")
        if not isinstance(fields, list):
            errors.append(f"{file_path}: fields must be an array")
            fields = []
        local_fields: set[str] = set()
        for field_index, field in enumerate(fields):
            field_prefix = f"{file_path}:fields[{field_index}]"
            if not isinstance(field, dict):
                errors.append(f"{field_prefix}: item must be an object")
                continue
            field_id = _required_id(field, field_prefix, errors)
            if field_id:
                if field_id in local_fields:
                    errors.append(f"{field_prefix}: duplicate field id {field_id}")
                local_fields.add(field_id)
                if entity_id:
                    field_ids.add(f"{entity_id}.{field_id}")
            if not isinstance(field.get("title"), str) or not field.get("title", "").strip():
                errors.append(f"{field_prefix}: title must be a non-empty string")
            field_type = field.get("type")
            if field_type not in allowed_logical_types:
                errors.append(f"{field_prefix}: unsupported logical type {field_type}")
            if not isinstance(field.get("required"), bool):
                errors.append(f"{field_prefix}: required must be boolean")
            dictionary_id = field.get("dictionary_id")
            if field_type == "dictionary":
                if not isinstance(dictionary_id, str) or dictionary_id not in dictionary_ids:
                    errors.append(f"{field_prefix}: dictionary_id must reference an existing dictionary")
            elif dictionary_id not in {None, ""}:
                errors.append(f"{field_prefix}: dictionary_id is allowed only for dictionary fields")

    entities_dir = root / "entities"
    if entities_dir.is_dir():
        for path in entities_dir.glob("*.json"):
            relative = path.relative_to(root).as_posix()
            if relative not in registry_files:
                warnings.append(f"Orphan entity file is not registered: {relative}")

    relations = relations_doc.get("relations")
    if not isinstance(relations, list):
        errors.append("relations.json: relations must be an array")
        relations = []
    relation_ids: set[str] = set()
    for index, relation in enumerate(relations):
        prefix = f"relations.json:relations[{index}]"
        if not isinstance(relation, dict):
            errors.append(f"{prefix}: item must be an object")
            continue
        relation_id = _required_id(relation, prefix, errors)
        if relation_id:
            if relation_id in relation_ids:
                errors.append(f"{prefix}: duplicate relation id {relation_id}")
            relation_ids.add(relation_id)
        if relation.get("source_entity") not in entity_ids:
            errors.append(f"{prefix}: source_entity does not exist")
        if relation.get("target_entity") not in entity_ids:
            errors.append(f"{prefix}: target_entity does not exist")
        if relation.get("cardinality") not in allowed_cardinalities:
            errors.append(f"{prefix}: unsupported cardinality {relation.get('cardinality')}")
        if not isinstance(relation.get("title"), str) or not relation.get("title", "").strip():
            errors.append(f"{prefix}: title must be a non-empty string")

    target_catalog = {
        "entity": entity_ids,
        "field": field_ids,
        "relation": relation_ids,
        "dictionary": dictionary_ids,
        "dictionary_value": dictionary_value_ids,
    }
    _validate_requirement_links(
        requirement_links_doc,
        target_catalog,
        known_requirement_ids,
        errors,
    )
    _validate_external_links(ui_links_doc, target_catalog, "ui_data_links", errors)
    _validate_external_links(api_links_doc, target_catalog, "api_data_links", errors)
    _validate_code_links(code_links_doc, target_catalog, errors)

    source = _read_object(root / "requirements_source.json", errors, default={"type": "workspace_file", "path": ""})
    if source.get("type") not in {None, "workspace_file"}:
        errors.append("requirements_source.json: only workspace_file is supported")
    if "path" in source and not isinstance(source.get("path"), str):
        errors.append("requirements_source.json: path must be a string")

    if rebuild and not errors:
        rebuild_index(root)

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "entities": len(entity_ids),
            "fields": len(field_ids),
            "relations": len(relation_ids),
            "dictionaries": len(dictionary_ids),
            "dictionary_values": len(dictionary_value_ids),
            "requirement_links": len(requirement_links_doc.get("links", [])) if isinstance(requirement_links_doc.get("links"), list) else 0,
        },
    }


def _read_object(path: Path, errors: list[str], default: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        value = read_json(path, default or {})
    except (OSError, ValueError) as exc:
        errors.append(f"{path.name}: invalid JSON: {exc}")
        return dict(default or {})
    if not isinstance(value, dict):
        errors.append(f"{path.name}: root value must be an object")
        return dict(default or {})
    return value


def _required_id(item: dict[str, Any], prefix: str, errors: list[str]) -> str:
    value = item.get("id")
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{prefix}: id must be a non-empty string")
        return ""
    return value


def _validate_target(
    target_type: Any,
    target_id: Any,
    target_catalog: dict[str, set[str]],
    prefix: str,
    errors: list[str],
) -> None:
    if target_type not in TARGET_TYPES:
        errors.append(f"{prefix}: unsupported target type {target_type}")
        return
    if not isinstance(target_id, str) or target_id not in target_catalog[target_type]:
        errors.append(f"{prefix}: target does not exist: {target_type}:{target_id}")


def _validate_requirement_links(
    document: dict[str, Any],
    target_catalog: dict[str, set[str]],
    known_requirement_ids: set[str] | None,
    errors: list[str],
) -> None:
    links = document.get("links")
    if not isinstance(links, list):
        errors.append("requirement_data_links.json: links must be an array")
        return
    seen_ids: set[str] = set()
    seen_semantics: set[tuple[str, str, str]] = set()
    for index, link in enumerate(links):
        prefix = f"requirement_data_links.json:links[{index}]"
        if not isinstance(link, dict):
            errors.append(f"{prefix}: item must be an object")
            continue
        link_id = _required_id(link, prefix, errors)
        if link_id:
            if link_id in seen_ids:
                errors.append(f"{prefix}: duplicate link id {link_id}")
            seen_ids.add(link_id)
        requirement_id = link.get("requirement_id")
        if not isinstance(requirement_id, str) or not requirement_id.strip():
            errors.append(f"{prefix}: requirement_id must be a non-empty string")
            requirement_id = ""
        elif known_requirement_ids is not None and requirement_id not in known_requirement_ids:
            errors.append(f"{prefix}: unknown requirement_id {requirement_id}")
        _validate_target(link.get("target_type"), link.get("target_id"), target_catalog, prefix, errors)
        semantic = (str(requirement_id), str(link.get("target_type")), str(link.get("target_id")))
        if semantic in seen_semantics:
            errors.append(f"{prefix}: duplicate requirement-target link")
        seen_semantics.add(semantic)


def _validate_external_links(
    document: dict[str, Any],
    target_catalog: dict[str, set[str]],
    label: str,
    errors: list[str],
) -> None:
    links = document.get("links")
    if not isinstance(links, list):
        errors.append(f"{label}.json: links must be an array")
        return
    for index, link in enumerate(links):
        prefix = f"{label}.json:links[{index}]"
        if not isinstance(link, dict):
            errors.append(f"{prefix}: item must be an object")
            continue
        _validate_target(link.get("data_target_type"), link.get("data_target_id"), target_catalog, prefix, errors)


def _validate_code_links(
    document: dict[str, Any],
    target_catalog: dict[str, set[str]],
    errors: list[str],
) -> None:
    links = document.get("links")
    if not isinstance(links, list):
        errors.append("code_links.json: links must be an array")
        return
    for index, link in enumerate(links):
        prefix = f"code_links.json:links[{index}]"
        if not isinstance(link, dict):
            errors.append(f"{prefix}: item must be an object")
            continue
        _validate_target(link.get("target_type"), link.get("target_id"), target_catalog, prefix, errors)
