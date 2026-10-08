from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_assessments import assessment_maps
from backend.modules.data_schema.files import read_json


def build_requirements_data_result(
    *,
    requirements_file: Path,
    schema_root: Path,
    agent_report_file: Path,
    run: dict[str, Any],
) -> dict[str, Any]:
    requirements_data = read_json(requirements_file, {"requirements": []})
    report = read_json(agent_report_file, {})
    assessments = assessment_maps(report)
    requirement_warnings = _requirement_warning_map(report)
    links_doc = read_json(
        schema_root / "mappings" / "requirement_data_links.json",
        {"links": []},
    )
    target_titles = _target_catalog(schema_root)
    links_by_requirement: dict[str, list[dict[str, Any]]] = {}
    for link in links_doc.get("links", []):
        if not isinstance(link, dict):
            continue
        requirement_id = str(link.get("requirement_id") or "")
        if not requirement_id:
            continue
        enriched = dict(link)
        key = f"{link.get('target_type')}:{link.get('target_id')}"
        enriched["target_title"] = target_titles.get(key, str(link.get("target_id") or ""))
        links_by_requirement.setdefault(requirement_id, []).append(enriched)

    records: list[dict[str, Any]] = []
    counts = {
        "total": 0,
        "linked": 0,
        "cross_cutting_data": 0,
        "no_data": 0,
        "unclear": 0,
        "unclassified": 0,
    }
    for requirement in requirements_data.get("requirements", []):
        if not isinstance(requirement, dict) or not requirement.get("id"):
            continue
        requirement_id = str(requirement["id"])
        links = links_by_requirement.get(requirement_id, [])
        assessment = _assessment(requirement_id, links, assessments)
        counts["total"] += 1
        counts[assessment["type"]] += 1
        records.append(
            {
                "requirement_id": requirement_id,
                "code": requirement.get("code") or requirement_id,
                "name": requirement.get("name") or requirement.get("title") or requirement_id,
                "description": requirement.get("description") or "",
                "types": requirement.get("types") or [],
                "assessment": assessment,
                "links": links,
                "warnings": requirement_warnings.get(requirement_id, []),
            }
        )
    warnings = _traceability_warnings(records)
    return {
        "run_id": run.get("run_id"),
        "requirements_source_path": run.get("requirements_source_path"),
        "requirements_source_sha256": run.get("requirements_source_sha256"),
        "assessment_counts": counts,
        "traceability_warnings": warnings,
        "requirements": records,
    }


def _assessment(
    requirement_id: str,
    links: list[dict[str, Any]],
    assessments: dict[str, dict[str, dict[str, str]]],
) -> dict[str, str]:
    if links:
        return {"type": "linked", "reason": "Есть прямая трассировка к объектам схемы данных"}
    for group in ("cross_cutting_data", "no_data", "unclear"):
        item = assessments.get(group, {}).get(requirement_id)
        if item:
            return {"type": group, "reason": item.get("reason", "")}
    return {"type": "unclassified", "reason": "Нет ссылки или итоговой оценки"}


def _requirement_warning_map(report: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    records = report.get("requirement_warnings", []) if isinstance(report, dict) else []
    if not isinstance(records, list):
        return result
    for item in records:
        if not isinstance(item, dict) or not item.get("requirement_id"):
            continue
        messages = item.get("messages", [])
        if not isinstance(messages, list):
            continue
        normalized = [str(message).strip() for message in messages if str(message).strip()]
        if normalized:
            result[str(item["requirement_id"])] = normalized
    return result


def _traceability_warnings(records: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for record in records:
        assessment = record.get("assessment", {})
        assessment_type = str(assessment.get("type") or "")
        requirement_id = str(record.get("requirement_id") or "")
        title = str(record.get("name") or requirement_id)
        reason = str(assessment.get("reason") or "").strip()
        if assessment_type == "unclear":
            warnings.append(
                f"Требует уточнения: {requirement_id} · {title}"
                + (f" — {reason}" if reason else "")
            )
        elif assessment_type == "unclassified":
            warnings.append(
                f"Не классифицировано: {requirement_id} · {title}"
                + (f" — {reason}" if reason else "")
            )
        for message in record.get("warnings", []):
            text = str(message).strip()
            if text:
                warnings.append(f"{requirement_id} · {title} — {text}")
    return list(dict.fromkeys(warnings))


def _target_catalog(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    schema = read_json(root / "schema.json", {"entities": []})
    for item in schema.get("entities", []):
        if not isinstance(item, dict) or not item.get("id"):
            continue
        entity_id = str(item["id"])
        entity = read_json(root / str(item.get("file") or f"entities/{entity_id}.json"), {})
        entity_title = str(entity.get("title") or item.get("title") or entity_id)
        result[f"entity:{entity_id}"] = entity_title
        for field in entity.get("fields", []):
            if isinstance(field, dict) and field.get("id"):
                field_id = str(field["id"])
                result[f"field:{entity_id}.{field_id}"] = f"{entity_title} · {field.get('title') or field_id}"
    relations = read_json(root / "relations.json", {"relations": []})
    for relation in relations.get("relations", []):
        if isinstance(relation, dict) and relation.get("id"):
            result[f"relation:{relation['id']}"] = str(relation.get("title") or relation["id"])
    dictionaries = read_json(root / "dictionaries.json", {"dictionaries": []})
    for dictionary in dictionaries.get("dictionaries", []):
        if not isinstance(dictionary, dict) or not dictionary.get("id"):
            continue
        dictionary_id = str(dictionary["id"])
        dictionary_title = str(dictionary.get("title") or dictionary_id)
        result[f"dictionary:{dictionary_id}"] = dictionary_title
        for value in dictionary.get("values", []):
            if isinstance(value, dict) and value.get("id"):
                result[f"dictionary_value:{dictionary_id}.{value['id']}"] = (
                    f"{dictionary_title} · {value.get('title') or value['id']}"
                )
    return result
