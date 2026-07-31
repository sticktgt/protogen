from __future__ import annotations

import json
import platform
import sys
import zipfile
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_paths import (
    legacy_diagnostics_root,
    run_file,
    run_root,
    validate_run_id,
)
from backend.modules.data_schema.files import read_json

_PACKAGE_NAMES = (
    "deepagents",
    "langchain",
    "langchain-core",
    "langchain-openai",
    "langgraph",
)


def diagnostics_archive_path(module_root: Path, run_id: str, attempt: int) -> Path:
    return run_root(module_root, run_id) / "diagnostics" / f"attempt_{max(1, int(attempt))}.zip"


def stored_diagnostics_archive_path(module_root: Path, run_id: str, attempt: int) -> Path:
    """Return the canonical archive path inside the run directory."""
    return diagnostics_archive_path(module_root, run_id, attempt)


def build_diagnostics_archive(module_root: Path, run_id: str) -> Path:
    root = run_root(module_root, run_id)
    run = read_json(root / "run.json", {})
    attempt = max(1, int(run.get("attempt", 1)))
    target = diagnostics_archive_path(module_root, run_id, attempt)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".zip.tmp")

    manifest = {
        "format_version": "0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "attempt": attempt,
        "workspace_id": run.get("workspace_id"),
        "status": run.get("status"),
        "phase": run.get("phase"),
        "llm": _safe_llm(run.get("llm")),
        "agent_runtime": {
            "type": "langchain_create_agent",
            "tool_policy": "data_schema_domain_tools_only",
            "primary_generation": "single_agent_schema_and_direct_traceability",
            "verification": "technical_validation_plus_two_focused_semantic_reviews_and_bounded_structured_recovery",
        },
        "execution_limits": run.get("execution", {}),
        "python": {
            "version": sys.version,
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "packages": _package_versions(),
        "contents": {
            "input": "Original task and requirements used by the run",
            "base": "data schema copied before the run",
            "working": "data schema produced by the agent",
            "reference": "Prompt references and module configuration copied for the run",
            "result": "Agent report, technical validation, changes and error details",
            "run.json": "Run state without API credentials",
            "metrics.json": "LLM, token and tool-call counters",
            "events.jsonl": "Chronological execution event log",
            "previous_attempts/": "Diagnostic ZIP files for earlier regeneration attempts",
        },
    }

    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr(
            "diagnostics_manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
        previous_attempts = root / "diagnostics"
        if previous_attempts.is_dir():
            for path in sorted(previous_attempts.glob("attempt_*.zip")):
                if path.resolve() != target.resolve():
                    archive.write(path, f"previous_attempts/{path.name}")
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if relative.parts and relative.parts[0] == "diagnostics":
                continue
            archive.write(path, relative.as_posix())
    temporary.replace(target)
    return target


def persist_diagnostics_archive(module_root: Path, run_id: str) -> Path:
    return build_diagnostics_archive(module_root, run_id)


def ensure_diagnostics_archive(module_root: Path, run_id: str) -> Path:
    validate_run_id(run_id)
    current_file = run_file(module_root, run_id)
    if current_file.is_file():
        run = read_json(current_file, {})
        if run.get("status") in {"running", "cancelling", "applying"}:
            raise ValueError("Diagnostics archive is available after the run stops or reaches preview")
        stored = sorted((run_root(module_root, run_id) / "diagnostics").glob("attempt_*.zip"))
        if run.get("archived"):
            if stored:
                return stored[-1]
            raise FileNotFoundError(f"Diagnostics archive not found: {run_id}")
        # Rebuild a non-terminal run on download so the archive reflects current state.
        return build_diagnostics_archive(module_root, run_id)

    # Backward-compatible fallback for workspaces not migrated yet.
    stored = sorted((legacy_diagnostics_root(module_root) / run_id).glob("attempt_*.zip"))
    if stored:
        return stored[-1]
    raise FileNotFoundError(f"Diagnostics archive not found: {run_id}")


def _safe_llm(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        key: str(value.get(key) or "")
        for key in ("provider", "model", "base_url")
        if value.get(key)
    }


def _package_versions() -> dict[str, str]:
    result: dict[str, str] = {}
    for name in _PACKAGE_NAMES:
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result[name] = "not-installed"
    return result
