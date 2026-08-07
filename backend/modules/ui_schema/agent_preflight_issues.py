from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChangePreflightError(ValueError):
    issues: list[dict[str, Any]]

    def __str__(self) -> str:
        messages = [
            str(item.get("message") or item.get("code") or "")
            for item in self.issues
        ]
        return "Техническая проверка пакета выявила ошибки: " + " | ".join(messages)


def preflight_issue(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **details}


def deduplicate_preflight_issues(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (str(item.get("code") or ""), str(item.get("message") or ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
