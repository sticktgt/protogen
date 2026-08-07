from __future__ import annotations

from typing import Any, Iterable


def unique_strings(values: Iterable[Any]) -> list[str]:
    return list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))


def join_notes(values: Iterable[Any]) -> str:
    return "\n\n".join(unique_strings(values))
