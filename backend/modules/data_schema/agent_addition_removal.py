from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_changes import build_change_report
from backend.modules.data_schema.files import read_json, write_json
from backend.modules.data_schema.index_builder import rebuild_index


def remove_run_additions(*, run_path: Path, targets: list[str]) -> dict[str, Any]:
    """Remove only objects introduced after the run base snapshot."""
    base_root = run_path / "base" / "data_schema"
    working_root = run_path / "working" / "data_schema"
    allowed = _added_targets(base_root, working_root)
    requested = _unique_targets(targets)
    disallowed = [target for target in requested if target not in allowed]
    if disallowed:
        raise ValueError(
            "Only objects added by the current run can be removed: "
            + ", ".join(disallowed)
        )

    removed: list[str] = []
    # Remove leaves before containers so a model may request both safely.
    for prefix in ("field:", "dictionary_value:", "relation:", "entity:", "dictionary:"):
        for target in requested:
            if target.startswith(prefix) and _remove_target(working_root, target, allowed):
                removed.append(target)

    _remove_links_to_missing_targets(working_root)
    rebuild_index(working_root)
    return {"removed": removed, "removed_count": len(removed)}


def _added_targets(base_root: Path, working_root: Path) -> set[str]:
    changes = build_change_report(base_root, working_root).get("changes", {})
    result: set[str] = set()
    mapping = {
        "entities": "entity",
        "fields": "field",
        "relations": "relation",
        "dictionaries": "dictionary",
        "dictionary_values": "dictionary_value",
    }
    for group, target_type in mapping.items():
        for item in changes.get(group, []):
            if not isinstance(item, dict) or item.get("change_type") != "added":
                continue
            object_id = str(item.get("id") or "").strip()
            if object_id:
                result.add(f"{target_type}:{object_id}")
    return result


def _remove_target(working_root: Path, target: str, allowed: set[str]) -> bool:
    target_type, object_id = target.split(":", 1)
    if target_type == "field":
        entity_id, field_id = _split_nested_id(object_id, target)
        path = working_root / "entities" / f"{entity_id}.json"
        entity = read_json(path, {})
        fields = [
            item for item in entity.get("fields", [])
            if not (isinstance(item, dict) and str(item.get("id")) == field_id)
        ]
        if len(fields) == len(entity.get("fields", [])):
            return False
        entity["fields"] = fields
        write_json(path, entity)
        return True

    if target_type == "relation":
        document = read_json(working_root / "relations.json", {"relations": []})
        relations = [
            item for item in document.get("relations", [])
            if not (isinstance(item, dict) and str(item.get("id")) == object_id)
        ]
        if len(relations) == len(document.get("relations", [])):
            return False
        write_json(working_root / "relations.json", {"relations": relations})
        return True

    if target_type == "dictionary_value":
        dictionary_id, value_id = _split_nested_id(object_id, target)
        document = read_json(working_root / "dictionaries.json", {"dictionaries": []})
        changed = False
        for dictionary in document.get("dictionaries", []):
            if not isinstance(dictionary, dict) or str(dictionary.get("id")) != dictionary_id:
                continue
            values = [
                item for item in dictionary.get("values", [])
                if not (isinstance(item, dict) and str(item.get("id")) == value_id)
            ]
            changed = len(values) != len(dictionary.get("values", []))
            dictionary["values"] = values
            break
        if changed:
            write_json(working_root / "dictionaries.json", document)
        return changed

    if target_type == "entity":
        _ensure_entity_relations_removable(working_root, object_id, allowed)
        schema = read_json(working_root / "schema.json", {})
        registry = [
            item for item in schema.get("entities", [])
            if not (isinstance(item, dict) and str(item.get("id")) == object_id)
        ]
        if len(registry) == len(schema.get("entities", [])):
            return False
        schema["entities"] = registry
        write_json(working_root / "schema.json", schema)
        (working_root / "entities" / f"{object_id}.json").unlink(missing_ok=True)
        relations_doc = read_json(working_root / "relations.json", {"relations": []})
        relations_doc["relations"] = [
            relation for relation in relations_doc.get("relations", [])
            if not (
                isinstance(relation, dict)
                and object_id in {
                    str(relation.get("source_entity") or ""),
                    str(relation.get("target_entity") or ""),
                }
            )
        ]
        write_json(working_root / "relations.json", relations_doc)
        return True

    if target_type == "dictionary":
        _ensure_dictionary_unused(working_root, object_id)
        document = read_json(working_root / "dictionaries.json", {"dictionaries": []})
        dictionaries = [
            item for item in document.get("dictionaries", [])
            if not (isinstance(item, dict) and str(item.get("id")) == object_id)
        ]
        if len(dictionaries) == len(document.get("dictionaries", [])):
            return False
        write_json(working_root / "dictionaries.json", {"dictionaries": dictionaries})
        return True

    raise ValueError(f"Unsupported removable target: {target}")


def _ensure_entity_relations_removable(
    working_root: Path,
    entity_id: str,
    allowed: set[str],
) -> None:
    document = read_json(working_root / "relations.json", {"relations": []})
    protected = []
    for relation in document.get("relations", []):
        if not isinstance(relation, dict):
            continue
        if entity_id not in {
            str(relation.get("source_entity") or ""),
            str(relation.get("target_entity") or ""),
        }:
            continue
        target = f"relation:{relation.get('id')}"
        if target not in allowed:
            protected.append(target)
    if protected:
        raise ValueError(
            f"Cannot remove added entity {entity_id}; base relations depend on it: "
            + ", ".join(protected)
        )


def _ensure_dictionary_unused(working_root: Path, dictionary_id: str) -> None:
    schema = read_json(working_root / "schema.json", {})
    references: list[str] = []
    for item in schema.get("entities", []):
        if not isinstance(item, dict):
            continue
        entity_id = str(item.get("id") or "")
        entity = read_json(
            working_root / str(item.get("file") or f"entities/{entity_id}.json"),
            {},
        )
        for field in entity.get("fields", []):
            if isinstance(field, dict) and str(field.get("dictionary_id") or "") == dictionary_id:
                references.append(f"field:{entity_id}.{field.get('id')}")
    if references:
        raise ValueError(
            f"Cannot remove dictionary {dictionary_id}; fields still reference it: "
            + ", ".join(references)
        )


def _remove_links_to_missing_targets(working_root: Path) -> None:
    path = working_root / "mappings" / "requirement_data_links.json"
    document = read_json(path, {"links": []})
    existing = _existing_targets(working_root)
    links = []
    for link in document.get("links", []):
        if not isinstance(link, dict):
            continue
        target = f"{link.get('target_type')}:{link.get('target_id')}"
        if target in existing:
            links.append(link)
    write_json(path, {"links": links})


def _existing_targets(working_root: Path) -> set[str]:
    result: set[str] = set()
    schema = read_json(working_root / "schema.json", {})
    for item in schema.get("entities", []):
        if not isinstance(item, dict):
            continue
        entity_id = str(item.get("id") or "")
        if not entity_id:
            continue
        result.add(f"entity:{entity_id}")
        entity = read_json(
            working_root / str(item.get("file") or f"entities/{entity_id}.json"),
            {},
        )
        for field in entity.get("fields", []):
            if isinstance(field, dict) and field.get("id"):
                result.add(f"field:{entity_id}.{field['id']}")
    for relation in read_json(working_root / "relations.json", {"relations": []}).get("relations", []):
        if isinstance(relation, dict) and relation.get("id"):
            result.add(f"relation:{relation['id']}")
    for dictionary in read_json(working_root / "dictionaries.json", {"dictionaries": []}).get("dictionaries", []):
        if not isinstance(dictionary, dict) or not dictionary.get("id"):
            continue
        dictionary_id = str(dictionary["id"])
        result.add(f"dictionary:{dictionary_id}")
        for value in dictionary.get("values", []):
            if isinstance(value, dict) and value.get("id"):
                result.add(f"dictionary_value:{dictionary_id}.{value['id']}")
    return result


def _split_nested_id(value: str, target: str) -> tuple[str, str]:
    if "." not in value:
        raise ValueError(f"Nested target must contain a dot: {target}")
    left, right = value.split(".", 1)
    if not left or not right:
        raise ValueError(f"Invalid nested target: {target}")
    return left, right


def _unique_targets(targets: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in targets:
        target = str(value).strip()
        if target and target not in seen:
            seen.add(target)
            result.append(target)
    return result
