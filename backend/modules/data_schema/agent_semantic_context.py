from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from backend.modules.data_schema.agent_context import build_data_schema_context
from backend.modules.data_schema.agent_requirement_context import compact_requirements
from backend.modules.data_schema.agent_requirement_scope import requirement_ids
from backend.modules.data_schema.agent_semantic_requirement_groups import (
    group_requirements_by_current_result,
)
from backend.modules.data_schema.files import read_json, write_json

ReviewScope = Literal["coverage", "consistency"]


def build_semantic_review_context(
    run_path: Path,
    *,
    review_scope: ReviewScope,
    review_number: int = 1,
) -> dict[str, Any]:
    """Build a focused semantic-review context without planning artifacts.

    Coverage review receives final requirement links and exclusive assessments.
    Consistency review receives the same requirements and schema structure, but
    excludes traceability payloads that are irrelevant to internal modelling.
    """
    include_traceability = review_scope == "coverage"
    requirements_document = read_json(
        run_path / "input" / "requirements.json",
        {"projects": [], "groups": [], "requirements": []},
    )
    current_ids = requirement_ids(requirements_document)
    candidate = _candidate_schema(
        run_path / "working" / "data_schema",
        include_traceability=include_traceability,
        current_requirement_ids=current_ids,
    )
    report = read_json(run_path / "result" / "agent_report.json", {})
    requirements = (
        group_requirements_by_current_result(requirements_document, report)
        if include_traceability
        else compact_requirements(requirements_document)
    )
    context: dict[str, Any] = {
        "review_scope": review_scope,
        "review_number": review_number,
        "task": read_json(run_path / "input" / "task.json", {}),
        "requirements": requirements,
        "candidate_data_schema": candidate,
    }
    if include_traceability:
        context["requirement_assessments"] = _candidate_assessments(
            report,
            current_requirement_ids=current_ids,
        )

    write_json(
        run_path / "input" / f"semantic_review_context_{review_scope}_{review_number}.json",
        context,
    )
    return context


def _candidate_schema(
    schema_root: Path,
    *,
    include_traceability: bool,
    current_requirement_ids: set[str],
) -> dict[str, Any]:
    context = build_data_schema_context(schema_root)
    entities = context.get("entities", {}) if isinstance(context.get("entities"), dict) else {}
    compact_entities: dict[str, Any] = {}
    for entity_id, entity in entities.items():
        if not isinstance(entity, dict):
            continue
        compact_entity = {
            key: value
            for key, value in entity.items()
            if key != "fields" and value not in (None, "", [], {})
        }
        compact_entity["fields"] = [
            {
                key: value
                for key, value in field.items()
                if key != "entity_id" and value not in (None, "", [], {})
            }
            for field in entity.get("fields", [])
            if isinstance(field, dict)
        ]
        compact_entities[str(entity_id)] = compact_entity

    candidate: dict[str, Any] = {
        "schema": context.get("schema", {}),
        "entities": compact_entities,
        "relations": context.get("relations", {}),
        "dictionaries": context.get("dictionaries", {}),
    }
    if include_traceability:
        links = context.get("requirement_data_links", {}).get("links", [])
        candidate["requirement_data_links"] = {
            "links": [
                {
                    key: item[key]
                    for key in ("requirement_id", "target_type", "target_id", "relation")
                    if key in item
                }
                for item in links
                if isinstance(item, dict)
                and str(item.get("requirement_id") or "") in current_requirement_ids
            ]
        }
    return candidate


def _candidate_assessments(
    report: dict[str, Any],
    *,
    current_requirement_ids: set[str],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("cross_cutting_data", "no_data", "unclear", "requirement_warnings"):
        records = report.get(key, []) if isinstance(report.get(key), list) else []
        result[key] = [
            item
            for item in records
            if isinstance(item, dict)
            and str(item.get("requirement_id") or "") in current_requirement_ids
        ]
    result["warnings"] = (
        list(report.get("warnings", []))
        if isinstance(report.get("warnings"), list)
        else []
    )
    return result
