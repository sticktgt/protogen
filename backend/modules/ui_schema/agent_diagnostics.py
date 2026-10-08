from __future__ import annotations

import json
import platform
import sys
import zipfile
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_paths import diagnostics_root, run_file, run_root, validate_run_id
from backend.modules.ui_schema.files import read_json

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
    validate_run_id(run_id)
    return diagnostics_root(module_root) / run_id / f"attempt_{max(1, int(attempt))}.zip"


def build_diagnostics_archive(module_root: Path, run_id: str) -> Path:
    root = run_root(module_root, run_id)
    run = read_json(root / "run.json", {})
    attempt = max(1, int(run.get("attempt", 1)))
    target = diagnostics_archive_path(module_root, run_id, attempt)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".zip.tmp")

    fingerprints = read_json(root / "reference" / "source_fingerprints.json", {})
    manifest = {
        "format_version": "0.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "attempt": attempt,
        "workspace_id": run.get("workspace_id"),
        "status": run.get("status"),
        "phase": run.get("phase"),
        "llm": _safe_llm(run.get("llm")),
        "build": {
            "build_id": fingerprints.get("build_id", ""),
            "commit_id": fingerprints.get("commit_id", ""),
            "module_version": fingerprints.get("module_version", ""),
            "source_fingerprints": "reference/source_fingerprints.json",
        },
        "agent_runtime": {
            "type": "managed_pipeline_v2",
            "tool_policy": "one_forced_structured_output_per_llm_stage",
        },
        "execution_limits": run.get("execution", {}),
        "diagnostics_settings": (
            run.get("config", {}).get("diagnostics", {})
            if isinstance(run.get("config"), dict)
            else {}
        ),
        "python": {
            "version": sys.version,
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "packages": _package_versions(),
        "contents": {
            "input": "Original task, requirements and rendered prompts used by the run",
            "base": "UI schema copied before the run",
            "working": "UI schema produced by the agent",
            "reference": "Prompt sources, module configuration and source fingerprints",
            "result": "Agent report, validation history, tool trace, changes and error details",
            "run.json": "Run state without API credentials",
            "metrics.json": "LLM, token and tool-call counters",
            "events.jsonl": "Chronological execution event log",
            "result/validation_history.json": "All recorded validation attempts with codes and repair hints",
            "result/tool_trace.jsonl": "Compact per-tool timing, argument counts and results",
            "result/structural_churn.json": "Technical comparison of element parents and page/root counts",
            "result/analysis.json": "Model-authored requirement analysis batches",
            "result/plan.json": "Canonical decisions and planned transactional schema changes",
            "result/applied_plan.json": "Plan whose schema transaction was accepted",
            "result/audit.json": "Independent audit issues only",
            "result/correction.json": "Last targeted correction, when one was required",
            "result/pipeline_decisions.json": "Final canonical decisions for all current requirements",
            "result/pipeline_state.json": "Managed pipeline v2 phase and completion state",
            "result/pipeline.json": "Completed managed pipeline v2 summary",
        },
    }

    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr(
            "diagnostics_manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
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
    source = build_diagnostics_archive(module_root, run_id)
    run = read_json(run_file(module_root, run_id), {})
    attempt = max(1, int(run.get("attempt", 1)))
    target = stored_diagnostics_archive_path(module_root, run_id, attempt)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".zip.tmp")
    temporary.write_bytes(source.read_bytes())
    temporary.replace(target)
    return target


def ensure_diagnostics_archive(module_root: Path, run_id: str) -> Path:
    validate_run_id(run_id)
    if run_file(module_root, run_id).is_file():
        run = read_json(run_file(module_root, run_id), {})
        if run.get("status") in {"running", "cancelling", "applying"}:
            raise ValueError("Diagnostics archive is available after the run stops or reaches preview")
        # Rebuild on download so the archive reflects current final state.
        return build_diagnostics_archive(module_root, run_id)
    stored = sorted((diagnostics_root(module_root) / run_id).glob("attempt_*.zip"))
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
