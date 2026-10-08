from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_cleanup_context import build_schema_catalog
from backend.modules.ui_schema.agent_requirement_scope import current_requirement_ids
from backend.modules.ui_schema.agent_validation_rules import SUPPORTED_REQUIREMENT_LINK_RELATIONS
from backend.modules.ui_schema.files import read_json, write_json

_RELATION_LABELS = {
    "implemented_by": "реализуется объектом",
    "supports": "поддерживается объектом",
    "triggers": "запускает действие",
    "starts_flow": "начинает пользовательский сценарий",
    "provides_access": "предоставляет доступ",
    "displays_result": "показывает результат",
    "displays_summary": "показывает сводку",
}


def build_manual_review_result(
    run_path: Path,
    cleanup_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build non-blocking information intended only for analyst review."""
    inherited = _inherited_requirement_links(run_path)
    review = cleanup_review if isinstance(cleanup_review, dict) else {}
    cleanup = [
        dict(item)
        for item in review.get("cleanup_candidates", [])
        if isinstance(item, dict)
    ]
    return {
        "inherited_requirement_links": inherited,
        "cleanup_candidates": cleanup,
        "cleanup_review": {
            key: review.get(key)
            for key in ("status", "summary", "warning", "reviewed_at")
            if review.get(key) not in (None, "")
        },
        "counts": {
            "inherited_requirement_ids": len(inherited),
            "inherited_requirement_links": sum(
                len(item.get("links", [])) for item in inherited
            ),
            "cleanup_candidates": len(cleanup),
            "inherited_link_issues": sum(
                len(item.get("issue_details", [])) for item in inherited
            ),
        },
    }


def write_manual_review_result(
    run_path: Path,
    cleanup_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = build_manual_review_result(run_path, cleanup_review)
    write_json(run_path / "result" / "manual_review.json", result)
    return result


def ensure_manual_review_result(run_path: Path) -> dict[str, Any]:
    """Refresh deterministic details while preserving an optional LLM review."""
    stored = read_json(run_path / "result" / "manual_review.json", {})
    cleanup_review: dict[str, Any] = {}
    if isinstance(stored, dict):
        cleanup_review.update(
            stored.get("cleanup_review", {})
            if isinstance(stored.get("cleanup_review"), dict)
            else {}
        )
        cleanup_review["cleanup_candidates"] = [
            dict(item)
            for item in stored.get("cleanup_candidates", [])
            if isinstance(item, dict)
        ]
    return write_manual_review_result(run_path, cleanup_review)


def merge_traceability_with_inherited_links(
    run_path: Path,
    incoming_document: dict[str, Any],
) -> dict[str, Any]:
    """Keep only links for the complete current requirements set.

    The selected requirements file is authoritative for the current synchronization.
    Links to IDs absent from it are removed from the temporary result and remain visible
    in manual review as previously existing links that require an analyst decision about
    related UI objects.
    """
    current_ids = current_requirement_ids(run_path)
    incoming = incoming_document.get("links", []) if isinstance(incoming_document, dict) else []
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in incoming:
        if not isinstance(item, dict):
            continue
        if str(item.get("requirement_id") or "").strip() not in current_ids:
            continue
        key = tuple(
            str(item.get(name) or "").strip()
            for name in ("requirement_id", "target_type", "target_id", "relation")
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(dict(item))
    return {"links": merged}


def _inherited_requirement_links(run_path: Path) -> list[dict[str, Any]]:
    current_ids = current_requirement_ids(run_path)
    base_links = _read_links(run_path / "base" / "ui_schema")
    inherited_ids = {
        str(item.get("requirement_id") or "").strip()
        for item in base_links
        if str(item.get("requirement_id") or "").strip()
        and str(item.get("requirement_id") or "").strip() not in current_ids
    }
    working_root = run_path / "working" / "ui_schema"
    working_links = _read_links(working_root)
    working_keys = {_semantic_key(item) for item in working_links}
    catalog = build_schema_catalog(working_root)
    object_by_target = {
        str(item.get("target") or ""): item
        for item in catalog.get("objects", [])
        if isinstance(item, dict) and item.get("target")
    }
    page_titles = {
        str(item.get("id") or ""): str(item.get("title") or item.get("id") or "")
        for item in catalog.get("objects", [])
        if isinstance(item, dict) and item.get("object_type") == "page"
    }
    valid_targets = set(catalog.get("target_ids", []))

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in base_links:
        requirement_id = str(item.get("requirement_id") or "").strip()
        if requirement_id not in inherited_ids:
            continue
        described = _describe_inherited_link(
                item,
                object_by_target=object_by_target,
                page_titles=page_titles,
                valid_targets=valid_targets,
            )
        described["status"] = "preserved" if _semantic_key(item) in working_keys else "removed"
        grouped.setdefault(requirement_id, []).append(described)

    result: list[dict[str, Any]] = []
    for requirement_id in sorted(grouped):
        links = grouped[requirement_id]
        issue_details = [
            dict(issue)
            for link in links
            for issue in link.get("issues", [])
            if isinstance(issue, dict)
        ]
        result.append(
            {
                "requirement_id": requirement_id,
                "reason": (
                    "Требование с таким ID отсутствует в полном текущем наборе требований. "
                    "Его прежние связи удалены из результата; проверьте, остались ли связанные UI-объекты актуальными."
                ),
                "links": links,
                "issues": [str(issue.get("message") or "") for issue in issue_details],
                "issue_details": issue_details,
            }
        )
    return result


def _describe_inherited_link(
    source: dict[str, Any],
    *,
    object_by_target: dict[str, dict[str, Any]],
    page_titles: dict[str, str],
    valid_targets: set[str],
) -> dict[str, Any]:
    link = {
        key: str(source.get(key) or "").strip()
        for key in ("id", "target_type", "target_id", "relation")
        if str(source.get(key) or "").strip()
    }
    target_type = link.get("target_type", "")
    target_id = link.get("target_id", "")
    target_key = f"{target_type}:{target_id}"
    target_object = object_by_target.get(target_key, {})
    page_id = str(target_object.get("page_id") or "")
    if target_type == "page" and not page_id:
        page_id = target_id
    label = str(
        target_object.get("title")
        or target_object.get("label")
        or target_id
        or "Объект не указан"
    )
    link.update(
        {
            "target_exists": target_key in valid_targets,
            "target_label": label,
            "page_id": page_id,
            "page_title": page_titles.get(page_id, ""),
            "relation_label": _RELATION_LABELS.get(
                link.get("relation", ""),
                link.get("relation", "") or "Тип связи не указан",
            ),
            "relation_supported": link.get("relation")
            in SUPPORTED_REQUIREMENT_LINK_RELATIONS,
        }
    )
    link["issues"] = _inherited_link_issue_details(link, valid_targets=valid_targets)
    return link


def _inherited_link_issue_details(
    link: dict[str, Any],
    *,
    valid_targets: set[str],
) -> list[dict[str, str]]:
    link_id = str(link.get("id") or "").strip()
    relation = str(link.get("relation") or "").strip()
    target_type = str(link.get("target_type") or "").strip()
    target_id = str(link.get("target_id") or "").strip()
    target = f"{target_type}:{target_id}"
    issues: list[dict[str, str]] = []

    if relation not in SUPPORTED_REQUIREMENT_LINK_RELATIONS:
        issues.append(
            {
                "code": "unsupported_relation",
                "title": "Устаревший тип связи",
                "message": (
                    f"Связь {link_id or 'без id'} использует тип {relation!r}, "
                    "который больше не поддерживается."
                ),
                "recommendation": _relation_recommendation(relation),
            }
        )
    if target not in valid_targets:
        issues.append(
            {
                "code": "missing_target",
                "title": "Целевой объект не найден",
                "message": (
                    f"Связь {link_id or 'без id'} ведёт на отсутствующий объект {target}."
                ),
                "recommendation": (
                    "Укажите существующую страницу или UI-элемент. Если требование и связь "
                    "больше не актуальны, удалите связь вручную; сам UI-объект оценивайте отдельно."
                ),
            }
        )
    if not link_id:
        issues.append(
            {
                "code": "missing_link_id",
                "title": "У связи нет технического ID",
                "message": "Сохранённая связь не имеет уникального технического идентификатора.",
                "recommendation": "Назначьте связи уникальный id перед дальнейшим ручным редактированием.",
            }
        )
    return issues


def _relation_recommendation(relation: str) -> str:
    if relation == "provides_access":
        return (
            "Проверьте смысл связи. Для пункта меню обычно подходит 'implemented_by', "
            "а если требование описывает начало сценария — 'starts_flow'."
        )
    if relation in {"displays_result", "displays_summary"}:
        return (
            "Проверьте смысл связи. Если объект непосредственно реализует отображение, "
            "обычно подходит 'implemented_by'; для вспомогательного влияния — 'supports'."
        )
    return (
        "Замените relation на один из допустимых: implemented_by, supports, triggers "
        "или starts_flow — в соответствии со смыслом требования."
    )



def _semantic_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return tuple(
        str(item.get(name) or "").strip()
        for name in ("requirement_id", "target_type", "target_id", "relation")
    )

def _read_links(schema_root: Path) -> list[dict[str, Any]]:
    document = read_json(
        schema_root / "mappings" / "requirement_ui_links.json",
        {"links": []},
    )
    links = document.get("links", []) if isinstance(document, dict) else []
    return [item for item in links if isinstance(item, dict)]
