from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.files import read_json, write_json


def ensure_agent_report(run_path: Path, response: Any) -> None:
    path = run_path / "result" / "agent_report.json"
    report = read_json(path, {})
    if not isinstance(report, dict):
        report = {}

    legacy_summary = str(report.get("summary") or "").strip()
    agent_note = str(report.get("agent_note") or legacy_summary or "").strip()
    if not agent_note:
        agent_note = _last_message_text(response)

    normalized = {
        "summary": legacy_summary,
        "agent_note": agent_note,
        "cross_cutting_ui": _normalize_assessments(
            report.get("cross_cutting_ui"), include_scope=True
        ),
        "no_ui": _normalize_assessments(report.get("no_ui")),
        "unclear": _normalize_assessments(report.get("unclear")),
        "warnings": (
            [str(item) for item in report.get("warnings", [])]
            if isinstance(report.get("warnings"), list)
            else []
        ),
    }
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
    report.setdefault("agent_note", "")
    report.setdefault("cross_cutting_ui", [])
    report.setdefault("no_ui", [])
    report.setdefault("unclear", [])
    report.setdefault("warnings", [])
    write_json(report_path, report)
    return report


def build_factual_summary(
    changes: dict[str, Any], requirements_result: dict[str, Any]
) -> str:
    statistics = changes.get("statistics", {}) if isinstance(changes, dict) else {}
    pages = statistics.get("pages", {}) if isinstance(statistics, dict) else {}
    elements = statistics.get("elements", {}) if isinstance(statistics, dict) else {}
    assessments = requirements_result.get("assessment_counts", {})

    summary = (
        "Синхронизация UI-схемы завершена. "
        f"Страницы: +{_count(pages, 'added')}, ~{_count(pages, 'modified')}, "
        f"−{_count(pages, 'deleted')}. "
        f"UI-элементы: +{_count(elements, 'added')}, ~{_count(elements, 'modified')}, "
        f"−{_count(elements, 'deleted')}. "
        "Требования: "
        f"{_integer(assessments, 'linked')} с прямой UI-трассировкой, "
        f"{_integer(assessments, 'cross_cutting_ui')} сквозных UI-правил, "
        f"{_integer(assessments, 'no_ui')} без UI, "
        f"{_integer(assessments, 'unclear')} требуют уточнения."
    )
    unclassified = _integer(assessments, "unclassified")
    if unclassified:
        summary += f" Без итоговой классификации: {unclassified}."
    return summary


def _normalize_assessments(
    value: Any, *, include_scope: bool = False
) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        requirement_id = item.get("requirement_id")
        if not isinstance(requirement_id, str) or not requirement_id:
            continue
        normalized = {
            "requirement_id": requirement_id,
            "reason": str(item.get("reason") or ""),
        }
        if include_scope:
            normalized["scope"] = str(item.get("scope") or "global")
        result.append(normalized)
    return result


def _last_message_text(response: Any) -> str:
    if not isinstance(response, dict) or not isinstance(response.get("messages"), list):
        return ""
    for message in reversed(response["messages"]):
        content = getattr(message, "content", None)
        if content is None and isinstance(message, dict):
            content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            texts = [
                str(item.get("text"))
                for item in content
                if isinstance(item, dict) and item.get("type") == "text" and item.get("text")
            ]
            if texts:
                return "\n".join(texts)
    return ""


def _count(data: Any, key: str) -> int:
    return _integer(data if isinstance(data, dict) else {}, key)


def _integer(data: Any, key: str) -> int:
    if not isinstance(data, dict):
        return 0
    try:
        return int(data.get(key) or 0)
    except (TypeError, ValueError):
        return 0
