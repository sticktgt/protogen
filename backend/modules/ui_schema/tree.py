from __future__ import annotations

from typing import Any


def collect_element_ids(page: dict[str, Any]) -> list[str]:
    result = []

    def walk(items: list[dict[str, Any]]) -> None:
        for item in items:
            if item.get("id"):
                result.append(item["id"])
            walk(item.get("children", []))

    walk(page.get("elements", []))
    return result


def element_exists(page: dict[str, Any], element_id: str) -> bool:
    return find_element(page.get("elements", []), element_id) is not None


def find_element(elements: list[dict[str, Any]], element_id: str) -> dict[str, Any] | None:
    for item in elements:
        if item.get("id") == element_id:
            return item
        nested = find_element(item.get("children", []), element_id)
        if nested:
            return nested
    return None


def remove_element(elements: list[dict[str, Any]], element_id: str) -> list[dict[str, Any]]:
    result = []
    for item in elements:
        if item.get("id") == element_id:
            continue
        item["children"] = remove_element(item.get("children", []), element_id)
        result.append(item)
    return result
