from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_changes import build_change_report
from backend.modules.data_schema.agent_context import build_data_schema_context
from backend.modules.data_schema.agent_schema_catalog import compact_schema_catalog
from backend.modules.data_schema.agent_requirement_scope import (
    requirement_ids as document_requirement_ids,
)
from backend.modules.data_schema.agent_target_references import (
    canonical_reference_catalog,
    structure_stored_requirement_link,
)
from backend.modules.data_schema.files import read_json, write_json


_CHANGE_TARGET_TYPES = {
    "entities": "entity",
    "fields": "field",
    "relations": "relation",
    "dictionaries": "dictionary",
    "dictionary_values": "dictionary_value",
}


def build_review_correction_context(
    run_path: Path,
    review: dict[str, Any],
    *,
    correction_round: int,
) -> dict[str, Any]:
    context = build_review_relevant_context(run_path, review)
    context["correction_round"] = correction_round
    write_json(
        run_path / "input" / f"review_correction_context_round_{correction_round}.json",
        context,
    )
    return context


def build_review_relevant_context(
    run_path: Path,
    review: dict[str, Any],
) -> dict[str, Any]:
    requirements_doc = read_json(
        run_path / "input" / "requirements.json",
        {"requirements": []},
    )
    current_requirement_ids = document_requirement_ids(requirements_doc)
    schema = build_data_schema_context(run_path / "working" / "data_schema")
    requirement_ids = _review_requirement_ids(review) & current_requirement_ids
    issue_targets = _review_targets(review)
    requirement_ids.update(
        _requirements_linked_to_targets(schema, issue_targets)
        & current_requirement_ids
    )
    links = _links_for_requirements(schema, requirement_ids)
    selected_targets = issue_targets | {
        f"{item.get('target_type')}:{item.get('target_id')}"
        for item in links
        if isinstance(item, dict)
    }
    selected = _selected_schema(schema, selected_targets)
    context = {
        "task": read_json(run_path / "input" / "task.json", {}),
        "requirements": _selected_requirements(requirements_doc, requirement_ids),
        "canonical_references": canonical_reference_catalog(
            run_path / "working" / "data_schema"
        ),
        "relevant_candidate_schema": selected,
        "current_requirement_links": _compact_requirement_links(
            [structure_stored_requirement_link(item) for item in links]
        ),
        "current_assessments": _selected_assessments(
            read_json(run_path / "result" / "agent_report.json", {}),
            requirement_ids,
        ),
        "removable_added_targets": _added_targets(run_path),
        "validation": read_json(run_path / "result" / "validation_errors.json", {}),
        "constraints": _constraints(run_path),
        "rules": {
            "base_objects_cannot_be_removed": True,
            "base_objects_may_be_updated_by_exact_id_when_required": True,
            "remove_only_targets_listed_in_removable_added_targets": True,
            "requirement_result_patch_replaces_only_listed_requirement_ids": True,
            "each_requirement_has_direct_links_or_one_exclusive_assessment": True,
        },
    }
    linked_requirement_ids = {
        str(item.get("requirement_id") or "").strip()
        for item in links
        if isinstance(item, dict) and str(item.get("requirement_id") or "").strip()
    }
    if requirement_ids - linked_requirement_ids:
        context["candidate_schema_catalog"] = compact_schema_catalog(
            run_path / "working" / "data_schema"
        )
    return context



def _compact_requirement_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for item in links:
        if not isinstance(item, dict):
            continue
        requirement_id = str(item.get("requirement_id") or "").strip()
        if not requirement_id:
            continue
        if requirement_id not in grouped:
            grouped[requirement_id] = []
            order.append(requirement_id)
        grouped[requirement_id].append(
            {
                key: item[key]
                for key in ("target_type", "target_id", "relation")
                if key in item
            }
        )
    return [
        {"requirement_id": requirement_id, "links": grouped[requirement_id]}
        for requirement_id in order
    ]


def _selected_requirements(
    document: dict[str, Any],
    requirement_ids: set[str],
) -> dict[str, Any]:
    requirements = [
        _compact_requirement(item)
        for item in document.get("requirements", [])
        if isinstance(item, dict)
        and str(item.get("id") or item.get("code") or "") in requirement_ids
    ]
    group_ids = {str(item.get("groupId") or "") for item in requirements}
    project_ids = {str(item.get("projectId") or "") for item in requirements}
    cluster_ids = {str(item.get("clusterId") or "") for item in requirements}
    return {
        "projects": _compact_named_items(document.get("projects", []), project_ids),
        "groups": _compact_named_items(document.get("groups", []), group_ids),
        "clusters": _compact_named_items(document.get("clusters", []), cluster_ids),
        "requirements": requirements,
    }


def _compact_requirement(item: dict[str, Any]) -> dict[str, Any]:
    omitted = {
        "status",
        "criticality",
        "implementationStage",
        "types",
        "formIds",
        "domainId",
    }
    return {key: value for key, value in item.items() if key not in omitted}


def _compact_named_items(value: Any, selected_ids: set[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {
            key: item[key]
            for key in ("id", "code", "name", "title", "description")
            if key in item
        }
        for item in value
        if isinstance(item, dict) and str(item.get("id") or "") in selected_ids
    ]


def _selected_schema(schema: dict[str, Any], targets: set[str]) -> dict[str, Any]:
    entities = schema.get("entities", {}) if isinstance(schema.get("entities"), dict) else {}
    relations_doc = schema.get("relations", {}) if isinstance(schema.get("relations"), dict) else {}
    dictionaries_doc = schema.get("dictionaries", {}) if isinstance(schema.get("dictionaries"), dict) else {}
    entity_ids: set[str] = set()
    relation_ids: set[str] = set()
    dictionary_ids: set[str] = set()
    for target in targets:
        target_type, object_id = _split_target(target)
        if target_type == "entity":
            entity_ids.add(object_id)
        elif target_type == "field":
            entity_ids.add(object_id.split(".", 1)[0])
        elif target_type == "relation":
            relation_ids.add(object_id)
        elif target_type in {"dictionary", "dictionary_value"}:
            dictionary_ids.add(object_id.split(".", 1)[0])

    relations = []
    for relation in relations_doc.get("relations", []):
        if not isinstance(relation, dict):
            continue
        relation_id = str(relation.get("id") or "")
        if relation_id in relation_ids or entity_ids.intersection(
            {
                str(relation.get("source_entity") or ""),
                str(relation.get("target_entity") or ""),
            }
        ):
            relations.append(relation)
            entity_ids.update(
                {
                    str(relation.get("source_entity") or ""),
                    str(relation.get("target_entity") or ""),
                }
            )

    selected_entities = {
        entity_id: entities[entity_id]
        for entity_id in sorted(entity_ids)
        if entity_id in entities
    }
    for entity in selected_entities.values():
        if not isinstance(entity, dict):
            continue
        for field in entity.get("fields", []):
            if isinstance(field, dict) and field.get("dictionary_id"):
                dictionary_ids.add(str(field["dictionary_id"]))

    dictionaries = [
        dictionary for dictionary in dictionaries_doc.get("dictionaries", [])
        if isinstance(dictionary, dict) and str(dictionary.get("id") or "") in dictionary_ids
    ]
    return {
        "schema": schema.get("schema", {}),
        "entities": selected_entities,
        "relations": {"relations": relations},
        "dictionaries": {"dictionaries": dictionaries},
    }




def _requirements_linked_to_targets(
    schema: dict[str, Any],
    targets: set[str],
) -> set[str]:
    result: set[str] = set()
    for item in schema.get("requirement_data_links", {}).get("links", []):
        if not isinstance(item, dict):
            continue
        target = f"{item.get('target_type')}:{item.get('target_id')}"
        requirement_id = str(item.get("requirement_id") or "").strip()
        if target in targets and requirement_id:
            result.add(requirement_id)
    return result


def _links_for_requirements(schema: dict[str, Any], requirement_ids: set[str]) -> list[dict[str, Any]]:
    return [
        item for item in schema.get("requirement_data_links", {}).get("links", [])
        if isinstance(item, dict) and str(item.get("requirement_id") or "") in requirement_ids
    ]


def _selected_assessments(report: dict[str, Any], requirement_ids: set[str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "agent_note": str(report.get("agent_note") or ""),
        "warnings": list(report.get("warnings", [])) if isinstance(report.get("warnings"), list) else [],
    }
    for key in ("cross_cutting_data", "no_data", "unclear", "requirement_warnings"):
        result[key] = [
            item for item in report.get(key, [])
            if isinstance(item, dict) and str(item.get("requirement_id") or "") in requirement_ids
        ]
    return result


def _added_targets(run_path: Path) -> list[str]:
    report = build_change_report(
        run_path / "base" / "data_schema",
        run_path / "working" / "data_schema",
    )
    result: list[str] = []
    for group, target_type in _CHANGE_TARGET_TYPES.items():
        for item in report.get("changes", {}).get(group, []):
            if not isinstance(item, dict) or item.get("change_type") != "added":
                continue
            object_id = str(item.get("id") or "").strip()
            if object_id:
                result.append(f"{target_type}:{object_id}")
    return result


def _constraints(run_path: Path) -> dict[str, Any]:
    run = read_json(run_path / "run.json", {})
    config = run.get("config", {}) if isinstance(run.get("config"), dict) else {}
    domain = config.get("domain", {}) if isinstance(config.get("domain"), dict) else {}
    return {
        "logical_types": list(domain.get("logical_types", [])) if isinstance(domain.get("logical_types"), list) else [],
        "cardinalities": list(domain.get("cardinalities", [])) if isinstance(domain.get("cardinalities"), list) else [],
    }


def _review_requirement_ids(review: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for issue in review.get("issues", []):
        if not isinstance(issue, dict):
            continue
        for value in issue.get("requirement_ids", []):
            text = str(value).strip()
            if text:
                result.add(text)
    return result


def _review_targets(review: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for issue in review.get("issues", []):
        if not isinstance(issue, dict):
            continue
        for value in issue.get("targets", []):
            text = str(value).strip()
            if ":" in text:
                result.add(text)
    return result


def _split_target(target: str) -> tuple[str, str]:
    if ":" not in target:
        return "", target
    return target.split(":", 1)
