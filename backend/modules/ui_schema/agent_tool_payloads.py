from __future__ import annotations

import json
from typing import Any

from backend.modules.ui_schema.agent_normalize_documents import (
    canonicalize_schema_document,
    normalize_element_labels_in_document,
)


def decode_json_argument(value: Any, *, label: str) -> Any:
    """Decode a valid provider-side JSON string while preferring native values."""
    return _decode_jsonish(value, label=label)


def normalize_core_argument(
    *,
    app: Any = None,
    schema: Any = None,
    links: Any = None,
) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for value, file_path in (
        (app, "app.json"),
        (schema, "schema.json"),
        (links, "links.json"),
    ):
        if value is not None:
            files.append(
                {
                    "file_path": file_path,
                    "content": normalize_document_content(file_path, value),
                }
            )
    if not files:
        raise ValueError("At least one of app, schema_document or links must be provided")
    return files


def normalize_traceability_argument(
    *,
    requirement_ui_links: Any,
    agent_report: Any,
) -> list[dict[str, Any]]:
    return [
        {
            "file_path": "mappings/requirement_ui_links.json",
            "content": normalize_document_content(
                "mappings/requirement_ui_links.json", requirement_ui_links
            ),
        },
        {
            "file_path": "result/agent_report.json",
            "content": normalize_document_content(
                "result/agent_report.json", agent_report
            ),
        },
    ]


def normalize_document_content(file_path: str, value: Any) -> dict[str, Any]:
    """Turn provider-specific JSON wrappers into the object stored by UI Schema."""
    candidate = _decode_jsonish(value, label=f"content for {file_path}", allow_plain_text=True)
    normalized_path = _canonical_path(file_path)

    if normalized_path == "schema.json" and isinstance(candidate, dict):
        candidate = canonicalize_schema_document(candidate)
    elif normalized_path == "app.json" and isinstance(candidate, dict):
        normalize_element_labels_in_document(candidate, collection_key="root_elements")
    elif normalized_path in {"links.json", "mappings/requirement_ui_links.json"}:
        if isinstance(candidate, list):
            candidate = {"links": candidate}
    elif normalized_path == "result/agent_report.json":
        if isinstance(candidate, str):
            candidate = {
                "agent_note": candidate,
                "cross_cutting_ui": [],
                "no_ui": [],
                "unclear": [],
                "warnings": [],
            }
    elif normalized_path.startswith("pages/"):
        if isinstance(candidate, list) and len(candidate) == 1 and isinstance(candidate[0], dict):
            candidate = candidate[0]
        if isinstance(candidate, dict) and set(candidate) == {"page"}:
            candidate = _decode_jsonish(candidate["page"], label=f"page wrapper for {file_path}")

    if not isinstance(candidate, dict):
        raise ValueError(f"{file_path} must contain a JSON object")
    return candidate


def _canonical_path(file_path: str) -> str:
    normalized = file_path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.lstrip("/")
    for prefix in ("working/ui_schema/", "result/"):
        if normalized.startswith(prefix):
            if prefix == "result/":
                return normalized
            return normalized[len(prefix):]
    return normalized


def _decode_jsonish(value: Any, *, label: str, allow_plain_text: bool = False) -> Any:
    if not isinstance(value, str):
        return value
    text = _strip_json_fence(value)
    if not text:
        return "" if allow_plain_text else value
    if not text.startswith(("{", "[", '"')):
        if allow_plain_text:
            return text
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        recovered = _decode_concatenated_json(text) if exc.msg == "Extra data" else None
        if recovered is not None:
            return recovered
        if allow_plain_text:
            return text
        raise ValueError(
            f"{label} must contain valid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}. "
            "Pass native JSON objects/arrays to the tool; do not serialize them into a string."
        ) from exc


def _strip_json_fence(value: str) -> str:
    text = value.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _decode_concatenated_json(text: str) -> Any | None:
    """Recover only a sequence of complete adjacent JSON arrays or objects."""
    decoder = json.JSONDecoder()
    values: list[Any] = []
    index = 0
    length = len(text)
    try:
        while index < length:
            while index < length and (text[index].isspace() or text[index] == ","):
                index += 1
            if index >= length:
                break
            value, end = decoder.raw_decode(text, index)
            values.append(value)
            index = end
    except json.JSONDecodeError:
        return None
    if len(values) < 2:
        return None
    if all(isinstance(value, list) for value in values):
        return [item for value in values for item in value]
    if all(isinstance(value, dict) for value in values):
        return values
    return None
