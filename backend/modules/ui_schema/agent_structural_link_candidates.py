from __future__ import annotations

from typing import Any


def collect_link_candidates(
    *,
    base_links: list[dict[str, Any]],
    working_links: list[dict[str, Any]],
    elements: dict[str, dict[str, Any]],
    decisions_by_target: dict[str, list[str]],
) -> list[dict[str, Any]]:
    base_by_id = {
        str(item.get("id") or ""): item
        for item in base_links
        if isinstance(item, dict) and str(item.get("id") or "")
    }
    changed_links = [
        link
        for link in working_links
        if isinstance(link, dict)
        and str(link.get("id") or "")
        and base_by_id.get(str(link.get("id") or "")) != link
    ]
    result = _self_navigation_candidates(
        changed_links=changed_links,
        base_by_id=base_by_id,
        elements=elements,
        decisions_by_target=decisions_by_target,
    )
    result.extend(
        _multiple_navigation_candidates(
            working_links=working_links,
            changed_links=changed_links,
            base_by_id=base_by_id,
            elements=elements,
            decisions_by_target=decisions_by_target,
        )
    )
    return result


def _self_navigation_candidates(
    *,
    changed_links: list[dict[str, Any]],
    base_by_id: dict[str, dict[str, Any]],
    elements: dict[str, dict[str, Any]],
    decisions_by_target: dict[str, list[str]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for link in changed_links:
        link_id = str(link.get("id") or "").strip()
        source_type = str(link.get("source_type") or "")
        source_id = str(link.get("source_id") or "")
        target_type = str(link.get("target_type") or "")
        target_id = str(link.get("target_id") or "")
        relation = str(link.get("relation") or "")
        source_page_id = _source_page_id(
            source_type=source_type,
            source_id=source_id,
            elements=elements,
        )
        if (
            relation != "navigates_to"
            or target_type != "page"
            or not source_page_id
            or source_page_id != target_id
        ):
            continue
        affected_ids = [source_id] if source_type == "ui_element" else []
        result.append(
            {
                "candidate_id": f"self_link:{link_id}",
                "kind": "self_navigation",
                "page_id": source_page_id,
                "parent_id": "",
                "element_ids": affected_ids,
                "new_element_ids": [],
                "existing_element_ids": affected_ids,
                "affected_element_ids": affected_ids,
                "link_ids": [link_id],
                "new_link_ids": [link_id] if link_id not in base_by_id else [],
                "related_requirement_ids": _related_requirement_ids(
                    decisions_by_target,
                    [*affected_ids, target_id],
                ),
                "facts": {
                    "link": link,
                    "source_page_id": source_page_id,
                },
            }
        )
    return result


def _multiple_navigation_candidates(
    *,
    working_links: list[dict[str, Any]],
    changed_links: list[dict[str, Any]],
    base_by_id: dict[str, dict[str, Any]],
    elements: dict[str, dict[str, Any]],
    decisions_by_target: dict[str, list[str]],
) -> list[dict[str, Any]]:
    changed_ids = {str(item.get("id") or "") for item in changed_links}
    by_source: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for link in working_links:
        if not isinstance(link, dict) or link.get("relation") != "navigates_to":
            continue
        source_type = str(link.get("source_type") or "")
        source_id = str(link.get("source_id") or "")
        if not source_type or not source_id:
            continue
        by_source.setdefault((source_type, source_id), []).append(link)

    result: list[dict[str, Any]] = []
    for (source_type, source_id), links in by_source.items():
        target_pairs = {
            (str(item.get("target_type") or ""), str(item.get("target_id") or ""))
            for item in links
        }
        link_ids = [str(item.get("id") or "") for item in links if str(item.get("id") or "")]
        if len(target_pairs) <= 1 or not (set(link_ids) & changed_ids):
            continue
        source_page_id = _source_page_id(
            source_type=source_type,
            source_id=source_id,
            elements=elements,
        )
        affected_ids = [source_id] if source_type == "ui_element" else []
        target_ids = [str(item.get("target_id") or "") for item in links]
        result.append(
            {
                "candidate_id": f"multi_nav:{source_type}:{source_id}",
                "kind": "multiple_navigation_targets",
                "page_id": source_page_id or (source_id if source_type == "page" else ""),
                "parent_id": "",
                "element_ids": affected_ids,
                "new_element_ids": [],
                "existing_element_ids": affected_ids,
                "affected_element_ids": affected_ids,
                "link_ids": sorted(link_ids),
                "new_link_ids": sorted(
                    link_id for link_id in link_ids if link_id not in base_by_id
                ),
                "related_requirement_ids": _related_requirement_ids(
                    decisions_by_target,
                    [*affected_ids, *target_ids],
                ),
                "facts": {
                    "links": [dict(item) for item in links],
                    "source_page_id": source_page_id,
                },
            }
        )
    return result


def _source_page_id(
    *,
    source_type: str,
    source_id: str,
    elements: dict[str, dict[str, Any]],
) -> str:
    if source_type == "page":
        return source_id
    return str(elements.get(source_id, {}).get("page_id") or "")


def _related_requirement_ids(
    decisions_by_target: dict[str, list[str]],
    target_ids: list[str],
) -> list[str]:
    return sorted(
        {
            requirement_id
            for target_id in target_ids
            for requirement_id in decisions_by_target.get(target_id, [])
        }
    )
