from __future__ import annotations

import re
from collections.abc import Iterable

_TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
})

_ID_PATTERN = re.compile(r"[^a-z0-9_]+")
_UNDERSCORE_PATTERN = re.compile(r"_+")


def make_slug(value: str, fallback: str = "item") -> str:
    """Build a stable lower_snake_case identifier from a human title."""
    text = (value or "").strip().lower().translate(_TRANSLIT)
    text = _ID_PATTERN.sub("_", text)
    text = _UNDERSCORE_PATTERN.sub("_", text).strip("_")
    if not text:
        text = fallback
    if text[0].isdigit():
        text = f"{fallback}_{text}"
    return text


def make_unique_id(value: str, existing_ids: Iterable[str], fallback: str = "item") -> str:
    base = make_slug(value, fallback=fallback)
    existing = set(existing_ids)
    if base not in existing:
        return base
    index = 2
    while f"{base}_{index}" in existing:
        index += 1
    return f"{base}_{index}"
