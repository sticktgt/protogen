from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.modules.ui_schema.files import read_json, write_json

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_generated_links(
    *,
    working_root: Path,
    descendant_remap: dict[str, str],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if descendant_remap:
        _remap_link_file(
            working_root / "links.json",
            descendant_remap,
            requirement_links=False,
            actions=actions,
        )
        _remap_link_file(
            working_root / "mappings" / "requirement_ui_links.json",
            descendant_remap,
            requirement_links=True,
            actions=actions,
        )

    page_ids, element_ids = _collect_object_ids(working_root)
    _repair_reference_ids(
        working_root / "links.json",
        page_ids=page_ids,
        element_ids=element_ids,
        requirement_links=False,
        actions=actions,
    )
    _repair_reference_ids(
        working_root / "mappings" / "requirement_ui_links.json",
        page_ids=page_ids,
        element_ids=element_ids,
        requirement_links=True,
        actions=actions,
    )
    return actions


def _remap_link_file(
    path: Path,
    remap: dict[str, str],
    *,
    requirement_links: bool,
    actions: list[dict[str, Any]],
) -> None:
    data = read_json(path, {"links": []})
    links = data.get("links", []) if isinstance(data, dict) else []
    if not isinstance(links, list):
        return
    changed = False
    remapped_count = 0
    for link in links:
        if not isinstance(link, dict):
            continue
        keys = ("target_id",) if requirement_links else ("source_id", "target_id")
        for key in keys:
            old_id = link.get(key)
            if old_id in remap:
                link[key] = remap[old_id]
                changed = True
                remapped_count += 1
    if requirement_links and changed:
        links, removed = _dedupe_requirement_links(links)
        if removed:
            actions.append(
                {
                    "type": "duplicate_requirement_links_removed",
                    "count": removed,
                    "message": (
                        f"После нормализации таблиц удалено дублирующихся связей требований: {removed}."
                    ),
                }
            )
    if changed:
        data["links"] = links
        write_json(path, data)
        actions.append(
            {
                "type": "table_descendant_links_remapped",
                "file": str(path.name),
                "count": remapped_count,
                "message": (
                    f"Связи на виртуальные дочерние элементы table перенаправлены на таблицу: {remapped_count}."
                ),
            }
        )


def _repair_reference_ids(
    path: Path,
    *,
    page_ids: set[str],
    element_ids: set[str],
    requirement_links: bool,
    actions: list[dict[str, Any]],
) -> None:
    data = read_json(path, {"links": []})
    links = data.get("links", []) if isinstance(data, dict) else []
    if not isinstance(links, list):
        return
    changed = False
    repairs: list[tuple[str, str, str]] = []
    for link in links:
        if not isinstance(link, dict):
            continue
        fields = (("target_type", "target_id"),) if requirement_links else (
            ("source_type", "source_id"),
            ("target_type", "target_id"),
        )
        for type_key, id_key in fields:
            object_type = link.get(type_key)
            object_id = link.get(id_key)
            candidates = (
                page_ids
                if object_type == "page"
                else element_ids if object_type == "ui_element" else set()
            )
            if not isinstance(object_id, str) or object_id in candidates or not candidates:
                continue
            replacement = _unique_canonical_match(object_id, candidates)
            if replacement:
                link[id_key] = replacement
                repairs.append((str(link.get("id") or "<without id>"), object_id, replacement))
                changed = True
    if changed:
        data["links"] = links
        write_json(path, data)
        for link_id, old_id, new_id in repairs:
            actions.append(
                {
                    "type": "reference_id_punctuation_repaired",
                    "link_id": link_id,
                    "old_id": old_id,
                    "new_id": new_id,
                    "message": (
                        f"Backend исправил однозначную пунктуационную опечатку в связи {link_id}: "
                        f"{old_id} → {new_id}."
                    ),
                }
            )


def _collect_object_ids(root: Path) -> tuple[set[str], set[str]]:
    page_ids: set[str] = set()
    element_ids: set[str] = set()
    schema = read_json(root / "schema.json", {})
    for item in schema.get("pages", []) if isinstance(schema, dict) else []:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            page_ids.add(item["id"])
    app = read_json(root / "app.json", {})
    _collect_tree_ids(app.get("root_elements", []) if isinstance(app, dict) else [], element_ids)
    for path in (root / "pages").glob("*.json"):
        page = read_json(path, {})
        _collect_tree_ids(page.get("elements", []) if isinstance(page, dict) else [], element_ids)
    return page_ids, element_ids


def _collect_tree_ids(items: Any, target: set[str]) -> None:
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id:
            target.add(item_id)
        _collect_tree_ids(item.get("children", []), target)


def _unique_canonical_match(value: str, candidates: set[str]) -> str | None:
    canonical = _canonical_id(value)
    if not canonical:
        return None
    matches = [candidate for candidate in candidates if _canonical_id(candidate) == canonical]
    return matches[0] if len(matches) == 1 else None


def _canonical_id(value: str) -> str:
    return _NON_ALNUM.sub("", value.lower())


def _dedupe_requirement_links(links: list[Any]) -> tuple[list[Any], int]:
    result: list[Any] = []
    seen: set[tuple[str, str, str, str]] = set()
    removed = 0
    for link in links:
        if not isinstance(link, dict):
            result.append(link)
            continue
        key = (
            str(link.get("requirement_id")),
            str(link.get("target_type")),
            str(link.get("target_id")),
            str(link.get("relation")),
        )
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        result.append(link)
    return result, removed
