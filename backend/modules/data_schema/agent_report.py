from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.modules.data_schema.files import read_json, write_json

GROUPS = ("cross_cutting_data", "no_data", "unclear")


def ensure_agent_report(run_path: Path, response: Any) -> None:
    del response  # Tool completion payloads are technical data, not human comments.
    path = run_path / "result" / "agent_report.json"
    report = read_json(path, {})
    if not isinstance(report, dict):
        report = {}
    legacy_summary = str(report.get("summary") or "").strip()
    agent_note = _human_agent_note(report.get("agent_note") or legacy_summary)
    normalized: dict[str, Any] = {
        "summary": legacy_summary,
        "agent_note": agent_note,
        "warnings": _string_list(report.get("warnings")),
        "requirement_warnings": _normalize_requirement_warnings(
            report.get("requirement_warnings")
        ),
    }
    for group in GROUPS:
        normalized[group] = _normalize_assessments(report.get(group))
    write_json(path, normalized)


def finalize_agent_report(
    *,
    report_path: Path,
    changes: dict[str, Any],
    requirements_result: dict[str, Any],
) -> dict[str, Any]:
    report = read_json(report_path, {})
    if not isinstance(report, dict):
        report = {}
    report["summary"] = build_factual_summary(changes, requirements_result)
    report["agent_note"] = _human_agent_note(report.get("agent_note"))
    report.setdefault("warnings", [])
    report.setdefault("requirement_warnings", [])
    for group in GROUPS:
        report.setdefault(group, [])
    write_json(report_path, report)
    return report


def build_factual_summary(changes: dict[str, Any], requirements_result: dict[str, Any]) -> str:
    del changes  # Change counts are rendered in the compact UI panel below the execution log.
    assessments = requirements_result.get("assessment_counts", {})
    return (
        "Синхронизация схемы данных завершена. "
        "Требования: "
        f"{_integer(assessments, 'linked')} с прямой трассировкой, "
        f"{_integer(assessments, 'cross_cutting_data')} сквозных правил данных, "
        f"{_integer(assessments, 'no_data')} без влияния на логическую схему, "
        f"{_integer(assessments, 'unclear')} требуют уточнения."
    )


def _normalize_assessments(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, dict) and item.get("requirement_id"):
            result.append({
                "requirement_id": str(item["requirement_id"]),
                "reason": str(item.get("reason") or ""),
            })
    return result


def _normalize_requirement_warnings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict) or not item.get("requirement_id"):
            continue
        messages = _string_list(item.get("messages"))
        if messages:
            result.append({
                "requirement_id": str(item["requirement_id"]),
                "messages": messages,
            })
    return result


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _human_agent_note(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return text
    if not isinstance(payload, dict):
        return text
    technical_keys = {
        "valid",
        "errors",
        "warnings",
        "counts",
        "preservation",
        "assessment_counts",
        "completed",
        "next_action",
    }
    if set(payload).issubset(technical_keys) and (
        "valid" in payload or "completed" in payload or "counts" in payload
    ):
        return ""
    return text


def _integer(data: Any, key: str) -> int:
    if not isinstance(data, dict):
        return 0
    try:
        return int(data.get(key) or 0)
    except (TypeError, ValueError):
        return 0
