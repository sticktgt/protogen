from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_exports import build_requirements_data_result
from backend.modules.data_schema.agent_file_diff import write_file_diff_result
from backend.modules.data_schema.files import read_json, write_json

OBJECT_TYPES = ("entities", "fields", "relations", "dictionaries", "dictionary_values", "requirement_links")


def build_change_report(base_root: Path, working_root: Path) -> dict[str, Any]:
    base = _collect_objects(base_root)
    working = _collect_objects(working_root)
    changes: dict[str, list[dict[str, Any]]] = {}
    statistics: dict[str, dict[str, int]] = {}
    for object_type in OBJECT_TYPES:
        before = base[object_type]
        after = working[object_type]
        entries: list[dict[str, Any]] = []
        for object_id in sorted(set(before) | set(after)):
            previous = before.get(object_id)
            current = after.get(object_id)
            if previous is None:
                entries.append(_entry("added", object_type, object_id, None, current))
            elif current is None:
                entries.append(_entry("deleted", object_type, object_id, previous, None))
            elif _canonical(previous) != _canonical(current):
                entries.append(_entry("modified", object_type, object_id, previous, current))
        changes[object_type] = entries
        statistics[object_type] = {
            "added": sum(item["change_type"] == "added" for item in entries),
            "modified": sum(item["change_type"] == "modified" for item in entries),
            "deleted": sum(item["change_type"] == "deleted" for item in entries),
        }

    base_manifest = build_file_manifest(base_root)
    working_manifest = build_file_manifest(working_root)
    file_changes = {
        "added": sorted(set(working_manifest) - set(base_manifest)),
        "deleted": sorted(set(base_manifest) - set(working_manifest)),
        "modified": sorted(
            path
            for path in set(base_manifest) & set(working_manifest)
            if base_manifest[path]["sha256"] != working_manifest[path]["sha256"]
        ),
    }
    return {"statistics": statistics, "changes": changes, "files": file_changes}


def build_file_manifest(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*.json")):
        relative = path.relative_to(root).as_posix()
        data = path.read_bytes()
        result[relative] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return result


def write_result_files(
    *,
    base_root: Path,
    working_root: Path,
    requirements_file: Path,
    agent_report_file: Path,
    result_path: Path,
    run: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    changes = build_change_report(base_root, working_root)
    requirements_result = build_requirements_data_result(
        requirements_file=requirements_file,
        schema_root=working_root,
        agent_report_file=agent_report_file,
        run=run,
    )
    write_json(result_path / "changes.json", changes)
    write_file_diff_result(
        base_root=base_root,
        working_root=working_root,
        result_path=result_path,
    )
    write_json(result_path / "requirements_data_result.json", requirements_result)
    return changes, requirements_result


def _collect_objects(root: Path) -> dict[str, dict[str, dict[str, Any]]]:
    result = {key: {} for key in OBJECT_TYPES}
    schema = read_json(root / "schema.json", {"entities": []})
    for item in schema.get("entities", []):
        if not isinstance(item, dict) or not item.get("id"):
            continue
        entity_id = str(item["id"])
        entity = read_json(root / str(item.get("file") or f"entities/{entity_id}.json"), {})
        result["entities"][entity_id] = {
            "id": entity_id,
            "title": entity.get("title") or item.get("title") or entity_id,
            "description": entity.get("description") or "",
        }
        for field in entity.get("fields", []):
            if isinstance(field, dict) and field.get("id"):
                target_id = f"{entity_id}.{field['id']}"
                result["fields"][target_id] = {"entity_id": entity_id, **field}
    for relation in read_json(root / "relations.json", {"relations": []}).get("relations", []):
        if isinstance(relation, dict) and relation.get("id"):
            result["relations"][str(relation["id"])] = relation
    for dictionary in read_json(root / "dictionaries.json", {"dictionaries": []}).get("dictionaries", []):
        if not isinstance(dictionary, dict) or not dictionary.get("id"):
            continue
        dictionary_id = str(dictionary["id"])
        result["dictionaries"][dictionary_id] = {
            key: value for key, value in dictionary.items() if key != "values"
        }
        for value in dictionary.get("values", []):
            if isinstance(value, dict) and value.get("id"):
                target_id = f"{dictionary_id}.{value['id']}"
                result["dictionary_values"][target_id] = {"dictionary_id": dictionary_id, **value}
    for link in read_json(
        root / "mappings" / "requirement_data_links.json", {"links": []}
    ).get("links", []):
        if not isinstance(link, dict):
            continue
        key = f"{link.get('requirement_id')}|{link.get('target_type')}|{link.get('target_id')}"
        result["requirement_links"][key] = link
    return result


def _entry(
    change_type: str,
    object_type: str,
    object_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> dict[str, Any]:
    value = after or before or {}
    return {
        "change_type": change_type,
        "object_type": object_type,
        "id": object_id,
        "title": value.get("title") or value.get("name") or object_id,
        "before": before,
        "after": after,
        "field_changes": _field_changes(before or {}, after or {}) if before and after else [],
    }


def _field_changes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for key in sorted(set(before) | set(after)):
        if key == "id" or _canonical(before.get(key)) == _canonical(after.get(key)):
            continue
        result.append({"field": key, "before": before.get(key), "after": after.get(key)})
    return result


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
