from __future__ import annotations

import json
from typing import Any


def parse_json_array(value: Any) -> Any:
    """Accept a native list or a strict JSON-encoded list.

    Some tool-capable models occasionally serialize a structured tool argument one
    level too far. Decoding a syntactically valid JSON array is a technical input
    normalization only; Markdown, prose and non-array JSON remain invalid.
    """
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return []
    if not text.startswith("["):
        return value
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return value
    return parsed if isinstance(parsed, list) else value
