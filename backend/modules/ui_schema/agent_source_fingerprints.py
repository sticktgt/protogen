from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_diagnostic_settings import diagnostic_settings
from backend.modules.ui_schema.agent_prompts import PROJECT_ROOT, prompt_files, reference_files
from backend.modules.ui_schema.files import write_json


def write_source_fingerprints(
    *,
    run_path: Path,
    agent_config: dict[str, Any],
) -> dict[str, Any]:
    settings = diagnostic_settings(agent_config).get("source_fingerprints", {})
    if not settings.get("enabled", True):
        return {}

    project_root = PROJECT_ROOT
    source_module_root = project_root / "modules" / "ui_schema"
    prompt_sources = prompt_files(agent_config)
    reference_sources = reference_files(agent_config)
    files: list[dict[str, Any]] = []
    for kind, sources in (("prompt", prompt_sources), ("reference", reference_sources)):
        for snapshot_name, source in sorted(sources.items()):
            snapshot = (
                run_path / "reference" / "prompts" / snapshot_name
                if kind == "prompt"
                else run_path / "reference" / snapshot_name
            )
            files.append(
                {
                    "kind": kind,
                    "configured_path": _relative_path(source, project_root),
                    "snapshot_path": snapshot.relative_to(run_path).as_posix(),
                    "source_sha256": _file_sha256(source),
                    "snapshot_sha256": _file_sha256(snapshot),
                    "matches_snapshot": source.is_file()
                    and snapshot.is_file()
                    and _file_sha256(source) == _file_sha256(snapshot),
                }
            )

    prompt_mappings = [
        {
            "prompt_snapshot_path": (
                run_path / "reference" / "prompts" / snapshot_name
            ).relative_to(run_path).as_posix(),
            "prompt_sha256": _file_sha256(
                run_path / "reference" / "prompts" / snapshot_name
            ),
        }
        for snapshot_name in sorted(prompt_sources)
    ]

    build_id = _first_environment_value(settings.get("build_id_environment", []))
    commit_id = _first_environment_value(settings.get("commit_id_environment", []))
    if not commit_id and settings.get("include_git_commit", True):
        commit_id = _read_git_commit(project_root)

    module_manifest = _read_yaml(source_module_root / "module.yaml")
    result = {
        "format_version": "0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "build_id": build_id,
        "commit_id": commit_id,
        "module_manifest_sha256": _file_sha256(source_module_root / "module.yaml"),
        "module_version": str(module_manifest.get("version") or "") if isinstance(module_manifest, dict) else "",
        "files": files,
        "prompt_mappings": prompt_mappings,
    }
    try:
        write_json(run_path / "reference" / "source_fingerprints.json", result)
    except OSError:
        return {}
    return result


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _first_environment_value(names: Any) -> str:
    if not isinstance(names, list):
        return ""
    for name in names:
        value = os.environ.get(str(name), "").strip()
        if value:
            return value
    return ""


def _read_git_commit(project_root: Path) -> str:
    try:
        git_path = project_root / ".git"
        if git_path.is_file():
            text = git_path.read_text(encoding="utf-8", errors="ignore").strip()
            if text.startswith("gitdir:"):
                git_path = (project_root / text.split(":", 1)[1].strip()).resolve()
        if not git_path.is_dir():
            return ""
        head = git_path / "HEAD"
        if not head.is_file():
            return ""
        value = head.read_text(encoding="utf-8", errors="ignore").strip()
        if value.startswith("ref:"):
            ref_name = value.split(":", 1)[1].strip()
            ref_file = git_path / ref_name
            if ref_file.is_file():
                return ref_file.read_text(encoding="utf-8", errors="ignore").strip()
            packed = git_path / "packed-refs"
            if packed.is_file():
                for line in packed.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if not line or line.startswith(("#", "^")):
                        continue
                    commit, _, name = line.partition(" ")
                    if name.strip() == ref_name:
                        return commit.strip()
        return value if not value.startswith("ref:") else ""
    except OSError:
        return ""


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml

        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}
