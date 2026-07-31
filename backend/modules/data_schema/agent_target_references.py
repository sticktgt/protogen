from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from backend.modules.data_schema.files import read_json


_TARGET_TYPES = {
    "entity",
    "field",
    "relation",
    "dictionary",
    "dictionary_value",
}


def materialize_requirement_link(
    *,
    working_root: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Convert an explicit structured target into the storage target format.

    This function performs no alias lookup, fuzzy matching or semantic inference.
    Every component used to form target_id must be explicitly supplied by the LLM.
    """

    target_type = str(payload.get("target_type") or "").strip()
    target_id = str(payload.get("target_id") or "").strip()
    if target_type or target_id:
        if not target_type or not target_id:
            raise ValueError("Each compact requirement link requires target_type and target_id")
    else:
        target = payload.get("target")
        if isinstance(target, BaseModel):
            target = target.model_dump(exclude_none=True)
        if not isinstance(target, dict):
            raise ValueError("Each requirement link requires exact target_type and target_id")
        target_type, target_id = compact_target_reference(target)

    target_id = _canonical_target_id(
        working_root,
        target_type=target_type,
        target_id=target_id,
    )

    result = {
        key: value
        for key, value in payload.items()
        if key not in {"target", "target_type", "target_id"}
    }
    result["target_type"] = target_type
    result["target_id"] = target_id
    return result


def structure_stored_requirement_link(payload: dict[str, Any]) -> dict[str, Any]:
    """Expose a stored target as the explicit agent-tool target shape."""

    target_type = str(payload.get("target_type") or "").strip()
    target_id = str(payload.get("target_id") or "").strip()
    require_exact_type = target_type in _TARGET_TYPES
    if not require_exact_type or not target_id:
        raise ValueError("Stored requirement link has an invalid exact target")
    return {
        key: value
        for key, value in payload.items()
        if key not in {"target_type", "target_id"}
    } | {"target_type": target_type, "target_id": target_id}




def compact_target_reference(target: dict[str, Any]) -> tuple[str, str]:
    """Compose one exact compact reference from the legacy structured shape."""

    return _materialize_target(target)

def require_exact_target_reference(
    working_root: Path,
    *,
    target_type: str,
    target_id: str,
) -> None:
    """Validate one exact compact reference without resolving aliases or meaning."""

    normalized_type = str(target_type or "").strip()
    normalized_id = str(target_id or "").strip()
    if normalized_type not in _TARGET_TYPES:
        raise ValueError(f"Unsupported exact target type: {normalized_type or '<empty>'}")
    if not normalized_id:
        raise ValueError("Exact target_id must be non-empty")
    _canonical_target_id(
        working_root,
        target_type=normalized_type,
        target_id=normalized_id,
    )


def structure_exact_target_reference(*, target_type: str, target_id: str) -> dict[str, str]:
    """Build the standard structured target from an exact model-selected ID.

    This is a purely syntactic conversion. It does not search the schema, resolve an
    alias, choose an owner or infer a semantic target.
    """

    return _structure_target(target_type=target_type, target_id=target_id)

def materialize_traceability_update(
    *,
    working_root: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    requirement_id = str(payload.get("requirement_id") or "").strip()
    if not requirement_id:
        raise ValueError("Each traceability update requires requirement_id")
    links = payload.get("links", [])
    if not isinstance(links, list):
        raise ValueError(f"Traceability links for {requirement_id} must be an array")
    return {
        "requirement_id": requirement_id,
        "links": [
            materialize_requirement_link(working_root=working_root, payload=link)
            for link in links
        ],
    }


def canonical_reference_catalog(working_root: Path) -> dict[str, list[dict[str, str]]]:
    """Return exact structured references for all current schema objects."""

    catalog = _target_catalog(working_root)
    return {
        "entities": [
            {"target_type": "entity", "entity_id": entity_id}
            for entity_id in sorted(catalog["entity"])
        ],
        "fields": [
            {
                "target_type": "field",
                "entity_id": target_id.split(".", 1)[0],
                "field_id": target_id.split(".", 1)[1],
            }
            for target_id in sorted(catalog["field"])
        ],
        "relations": [
            {"target_type": "relation", "relation_id": relation_id}
            for relation_id in sorted(catalog["relation"])
        ],
        "dictionaries": [
            {"target_type": "dictionary", "dictionary_id": dictionary_id}
            for dictionary_id in sorted(catalog["dictionary"])
        ],
        "dictionary_values": [
            {
                "target_type": "dictionary_value",
                "dictionary_id": target_id.split(".", 1)[0],
                "value_id": target_id.split(".", 1)[1],
            }
            for target_id in sorted(catalog["dictionary_value"])
        ],
    }


def canonical_references_for_core(written: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    entities: list[dict[str, str]] = []
    fields: list[dict[str, str]] = []
    for item in written:
        entity_id = str(item.get("id") or "")
        if not entity_id:
            continue
        entities.append({"target_type": "entity", "entity_id": entity_id})
        for field_id in item.get("fields", []):
            field_id = str(field_id or "")
            if field_id:
                fields.append(
                    {
                        "target_type": "field",
                        "entity_id": entity_id,
                        "field_id": field_id,
                    }
                )
    return {"entities": entities, "fields": fields}


def canonical_references_for_dictionaries(
    written: list[dict[str, Any]],
) -> dict[str, list[dict[str, str]]]:
    dictionaries: list[dict[str, str]] = []
    values: list[dict[str, str]] = []
    for item in written:
        dictionary_id = str(item.get("id") or "")
        if not dictionary_id:
            continue
        dictionaries.append(
            {"target_type": "dictionary", "dictionary_id": dictionary_id}
        )
        for value_id in item.get("values", []):
            value_id = str(value_id or "")
            if value_id:
                values.append(
                    {
                        "target_type": "dictionary_value",
                        "dictionary_id": dictionary_id,
                        "value_id": value_id,
                    }
                )
    return {"dictionaries": dictionaries, "dictionary_values": values}


def canonical_references_for_relations(
    written: list[dict[str, Any]],
) -> list[dict[str, str]]:
    return [
        {"target_type": "relation", "relation_id": str(item.get("id"))}
        for item in written
        if item.get("id")
    ]


def _structure_target(*, target_type: str, target_id: str) -> dict[str, str]:
    if target_type == "entity":
        return {"target_type": "entity", "entity_id": target_id}
    if target_type == "field":
        owner_id, field_id = _split_compound_id(target_id, label="field target_id")
        return {
            "target_type": "field",
            "entity_id": owner_id,
            "field_id": field_id,
        }
    if target_type == "relation":
        return {"target_type": "relation", "relation_id": target_id}
    if target_type == "dictionary":
        return {"target_type": "dictionary", "dictionary_id": target_id}
    if target_type == "dictionary_value":
        dictionary_id, value_id = _split_compound_id(
            target_id,
            label="dictionary value target_id",
        )
        return {
            "target_type": "dictionary_value",
            "dictionary_id": dictionary_id,
            "value_id": value_id,
        }
    raise ValueError(f"Unsupported stored requirement target type: {target_type or '<empty>'}")


def _split_compound_id(value: str, *, label: str) -> tuple[str, str]:
    if "." not in value:
        raise ValueError(f"{label} must contain two exact ID parts separated by a dot")
    left, right = value.split(".", 1)
    if not left or not right:
        raise ValueError(f"{label} must contain non-empty exact ID parts")
    return left, right


def _materialize_target(target: dict[str, Any]) -> tuple[str, str]:
    target_type = str(target.get("target_type") or "").strip()
    if target_type not in _TARGET_TYPES:
        raise ValueError(f"Unsupported requirement target type: {target_type or '<empty>'}")

    allowed_keys = {
        "entity": {"target_type", "entity_id"},
        "field": {"target_type", "entity_id", "field_id"},
        "relation": {"target_type", "relation_id"},
        "dictionary": {"target_type", "dictionary_id"},
        "dictionary_value": {"target_type", "dictionary_id", "value_id"},
    }[target_type]
    unexpected = sorted(
        key
        for key, value in target.items()
        if key not in allowed_keys and value not in (None, "")
    )
    if unexpected:
        raise ValueError(
            f"Requirement target_type={target_type} does not permit fields: "
            + ", ".join(unexpected)
        )

    if target_type == "entity":
        return target_type, _required(target, "entity_id")
    if target_type == "field":
        entity_id = _required(target, "entity_id")
        field_id = _required(target, "field_id")
        return target_type, f"{entity_id}.{field_id}"
    if target_type == "relation":
        return target_type, _required(target, "relation_id")
    if target_type == "dictionary":
        return target_type, _required(target, "dictionary_id")

    dictionary_id = _required(target, "dictionary_id")
    value_id = _required(target, "value_id")
    return target_type, f"{dictionary_id}.{value_id}"


def _required(target: dict[str, Any], key: str) -> str:
    value = str(target.get(key) or "").strip()
    if not value:
        raise ValueError(f"Requirement target requires {key}")
    return value


def _canonical_target_id(
    working_root: Path,
    *,
    target_type: str,
    target_id: str,
) -> str:
    """Return an exact target ID, tolerating only redundant owner prefixes.

    This is syntactic normalization for compact nested IDs. It never searches by
    title, description, similarity or requirement meaning.
    """

    catalog = _target_catalog(working_root)
    available_ids = catalog[target_type]
    if target_id in available_ids:
        return target_id

    candidates = _owner_prefix_candidates(target_type=target_type, target_id=target_id)
    matches = [candidate for candidate in candidates if candidate in available_ids]
    if len(matches) == 1:
        return matches[0]

    available = sorted(available_ids)
    sample = available[:20]
    suffix = "" if len(available) <= len(sample) else f"; total available: {len(available)}"
    raise ValueError(
        f"Unknown exact target {target_type}:{target_id}. "
        f"Use canonical IDs returned by write tools or loaded from context. "
        f"Available exact IDs: {sample}{suffix}"
    )


def _owner_prefix_candidates(*, target_type: str, target_id: str) -> list[str]:
    if target_type not in {"field", "dictionary_value"} or "." not in target_id:
        return []
    owner_id, local_id = target_id.split(".", 1)
    if not owner_id or not local_id:
        return []

    local_variants = [local_id]
    dotted_prefix = owner_id + "."
    underscored_prefix = owner_id + "_"
    if local_id.startswith(dotted_prefix):
        local_variants.append(local_id[len(dotted_prefix):])
    if local_id.startswith(underscored_prefix):
        local_variants.append(local_id[len(underscored_prefix):])
    if "." in local_id:
        local_variants.append(local_id.replace(".", "_"))

    candidates: list[str] = []
    for variant in local_variants:
        if not variant:
            continue
        for candidate in (
            f"{owner_id}.{variant}",
            f"{owner_id}.{owner_id}_{variant}",
        ):
            if candidate != target_id and candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _target_catalog(working_root: Path) -> dict[str, set[str]]:
    catalog: dict[str, set[str]] = {target_type: set() for target_type in _TARGET_TYPES}

    schema = read_json(working_root / "schema.json", {"entities": []})
    for registry_item in schema.get("entities", []):
        if not isinstance(registry_item, dict):
            continue
        entity_id = str(registry_item.get("id") or "")
        if not entity_id:
            continue
        catalog["entity"].add(entity_id)
        entity = read_json(working_root / "entities" / f"{entity_id}.json", {})
        for field in entity.get("fields", []):
            if isinstance(field, dict) and field.get("id"):
                catalog["field"].add(f"{entity_id}.{field['id']}")

    relations = read_json(working_root / "relations.json", {"relations": []})
    for relation in relations.get("relations", []):
        if isinstance(relation, dict) and relation.get("id"):
            catalog["relation"].add(str(relation["id"]))

    dictionaries = read_json(working_root / "dictionaries.json", {"dictionaries": []})
    for dictionary in dictionaries.get("dictionaries", []):
        if not isinstance(dictionary, dict) or not dictionary.get("id"):
            continue
        dictionary_id = str(dictionary["id"])
        catalog["dictionary"].add(dictionary_id)
        for value in dictionary.get("values", []):
            if isinstance(value, dict) and value.get("id"):
                catalog["dictionary_value"].add(f"{dictionary_id}.{value['id']}")

    return catalog
