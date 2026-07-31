from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_requirements import (
    RequirementsSourceError,
    load_requirements_from_workspace,
)
from backend.modules.data_schema.files import read_json
from backend.modules.data_schema.storage import read_requirements_source

EMPTY_REQUIREMENTS: dict[str, Any] = {"projects": [], "groups": [], "requirements": []}

def source_reference(workspace_path: str, *, sha256: str | None = None) -> dict[str, Any]:
    reference: dict[str, Any] = {
        "type": "workspace_file",
        "path": str(workspace_path or "").strip().replace("\\", "/"),
    }
    if sha256:
        reference["sha256_at_sync"] = sha256
    return reference


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_requirements(
    module_root: Path,
    *,
    max_bytes: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source = read_requirements_source(module_root)
    source_type = source.get("type")
    workspace_path = source.get("path")
    metadata: dict[str, Any] = {
        "type": source_type or "workspace_file",
        "path": workspace_path or "",
        "status": "not_configured",
    }
    if source_type not in {None, "workspace_file"}:
        metadata.update(status="unsupported", error=f"Unsupported requirements source type: {source_type}")
        return dict(EMPTY_REQUIREMENTS), metadata
    if not isinstance(workspace_path, str) or not workspace_path.strip():
        # Legacy fallback is allowed only when the source-reference file does
        # not exist at all. A present but empty requirements_source.json means
        # that the new storage model is active but no external source has been
        # configured yet. This also prevents an obsolete requirements.json
        # left by an overlay installation from becoming canonical again.
        legacy = module_root / "requirements.json"
        if not (module_root / "requirements_source.json").is_file() and legacy.is_file():
            try:
                data = read_json(legacy, dict(EMPTY_REQUIREMENTS))
            except (OSError, ValueError) as exc:
                metadata.update(status="unavailable", error=str(exc), legacy_local_file=True)
                return dict(EMPTY_REQUIREMENTS), metadata
            metadata.update(
                type="legacy_local_file",
                path="data_schema/requirements.json",
                status="legacy",
                legacy_local_file=True,
                sha256=file_sha256(legacy),
                requirements_count=len(data.get("requirements", [])),
            )
            return data, metadata
        return dict(EMPTY_REQUIREMENTS), metadata

    try:
        data, path, normalized = load_requirements_from_workspace(
            module_root=module_root,
            workspace_relative_path=workspace_path,
            max_bytes=max_bytes,
        )
    except RequirementsSourceError as exc:
        metadata.update(status="unavailable", error=str(exc))
        return dict(EMPTY_REQUIREMENTS), metadata

    current_hash = file_sha256(path)
    metadata.update(
        path=normalized,
        status="available",
        sha256=current_hash,
        sha256_at_sync=source.get("sha256_at_sync"),
        changed_since_sync=(
            isinstance(source.get("sha256_at_sync"), str)
            and source.get("sha256_at_sync") != current_hash
        ),
        requirements_count=len(data.get("requirements", [])),
    )
    return data, metadata


def read_preview_requirements(run_root: Path, run: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    data = read_json(run_root / "input" / "requirements.json", dict(EMPTY_REQUIREMENTS))
    metadata = {
        "type": "workspace_file",
        "path": run.get("requirements_source_path") or "",
        "status": "snapshot",
        "sha256": run.get("requirements_source_sha256"),
        "requirements_count": len(data.get("requirements", [])),
        "preview_snapshot": True,
    }
    return data, metadata
