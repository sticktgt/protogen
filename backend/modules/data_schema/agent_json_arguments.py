from __future__ import annotations

import json
from typing import Any


def decode_json_argument(value: Any, *, label: str) -> Any:
    """Decode provider-serialized nested JSON while preferring native values."""
    if not isinstance(value, str):
        return value
    text = strip_json_fence(value)
    if not text or not text.startswith(("{", "[", '"')):
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{label} must contain valid JSON: {exc.msg} at line {exc.lineno}, "
            f"column {exc.colno}. Pass native JSON objects/arrays when possible."
        ) from exc


def normalize_optional_object_argument(value: Any, *, label: str) -> Any:
    """Treat provider-generated blank optional object values as omission."""
    if isinstance(value, str) and not value.strip():
        return None
    candidate = decode_json_argument(value, label=label)
    if candidate is None:
        return None
    return candidate


def normalize_array_argument(value: Any, *, label: str, wrapper_key: str) -> Any:
    candidate = decode_json_argument(value, label=label)
    if isinstance(candidate, dict) and set(candidate) == {wrapper_key}:
        candidate = decode_json_argument(candidate[wrapper_key], label=f"{label} wrapper")
    if isinstance(candidate, list):
        return [
            decode_json_argument(item, label=f"{label}[{index}]")
            for index, item in enumerate(candidate)
        ]
    return candidate


def strip_json_fence(value: str) -> str:
    text = value.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
