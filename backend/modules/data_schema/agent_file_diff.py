from __future__ import annotations

import difflib
import hashlib
from pathlib import Path
from typing import Any


_CHANGE_ORDER = {"added": 0, "modified": 1, "deleted": 2}


def build_file_diff(base_root: Path, working_root: Path) -> dict[str, Any]:
    base_files = _collect_files(base_root)
    working_files = _collect_files(working_root)
    files: list[dict[str, Any]] = []

    for relative_path in sorted(set(base_files) | set(working_files)):
        before = base_files.get(relative_path)
        after = working_files.get(relative_path)
        if before == after:
            continue
        change_type = (
            "added" if before is None else "deleted" if after is None else "modified"
        )
        entry = _build_file_entry(
            relative_path=relative_path,
            change_type=change_type,
            before=before,
            after=after,
        )
        files.append(entry)

    files.sort(
        key=lambda item: (
            _CHANGE_ORDER[str(item["change_type"])],
            str(item["path"]),
        )
    )
    return {
        "summary": {
            "files": len(files),
            "added": sum(item["change_type"] == "added" for item in files),
            "modified": sum(item["change_type"] == "modified" for item in files),
            "deleted": sum(item["change_type"] == "deleted" for item in files),
            "additions": sum(int(item["additions"]) for item in files),
            "deletions": sum(int(item["deletions"]) for item in files),
        },
        "files": files,
    }


def write_file_diff_result(
    *,
    base_root: Path,
    working_root: Path,
    result_path: Path,
) -> dict[str, Any]:
    from backend.modules.data_schema.files import write_json

    result = build_file_diff(base_root, working_root)
    write_json(result_path / "file_diff.json", result)
    return result


def _collect_files(root: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    if not root.is_dir():
        return result
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        result[relative] = path.read_bytes()
    return result


def _decode_content(value: bytes | None) -> str | None:
    if value is None:
        return None
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        digest = hashlib.sha256(value).hexdigest()
        return f"<binary file: {len(value)} bytes, sha256={digest}>\n"


def _build_file_entry(
    *,
    relative_path: str,
    change_type: str,
    before: bytes | None,
    after: bytes | None,
) -> dict[str, Any]:
    before_lines = _split_lines(_decode_content(before))
    after_lines = _split_lines(_decode_content(after))
    from_file = "/dev/null" if before is None else f"a/{relative_path}"
    to_file = "/dev/null" if after is None else f"b/{relative_path}"
    diff_lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=from_file,
            tofile=to_file,
            lineterm="",
        )
    )
    additions = sum(
        line.startswith("+") and not line.startswith("+++") for line in diff_lines
    )
    deletions = sum(
        line.startswith("-") and not line.startswith("---") for line in diff_lines
    )
    return {
        "path": relative_path,
        "change_type": change_type,
        "additions": additions,
        "deletions": deletions,
        "diff": "\n".join(diff_lines),
    }


def _split_lines(value: str | None) -> list[str]:
    if value is None:
        return []
    return value.splitlines()
