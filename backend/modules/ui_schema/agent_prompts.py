from __future__ import annotations

from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class PromptConfigurationError(RuntimeError):
    pass


def load_prompt(agent_config: dict[str, Any], name: str) -> str:
    prompts = agent_config.get("prompts", {})
    relative = prompts.get(name) if isinstance(prompts, dict) else None
    if not isinstance(relative, str) or not relative.strip():
        raise PromptConfigurationError(f"Agent prompt is not configured: {name}")
    path = _project_file(relative)
    if not path.is_file():
        raise PromptConfigurationError(f"Agent prompt file does not exist: {relative}")
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise PromptConfigurationError(f"Agent prompt file is empty: {relative}")
    return content


def prompt_files(agent_config: dict[str, Any]) -> dict[str, Path]:
    configured = agent_config.get("prompts", {})
    if not isinstance(configured, dict) or not configured:
        raise PromptConfigurationError("agent.prompts is not configured")
    result: dict[str, Path] = {}
    for name, relative in configured.items():
        if not isinstance(name, str) or not isinstance(relative, str):
            raise PromptConfigurationError("Invalid agent.prompts entry")
        source = _project_file(relative)
        if not source.is_file():
            raise PromptConfigurationError(f"Agent prompt file does not exist: {relative}")
        result[f"{name}{source.suffix or '.txt'}"] = source
    return result


def reference_files(agent_config: dict[str, Any]) -> dict[str, Path]:
    configured = agent_config.get("reference_files", {})
    if not isinstance(configured, dict) or not configured:
        raise PromptConfigurationError("agent.reference_files is not configured")
    result: dict[str, Path] = {}
    for destination_name, relative in configured.items():
        if not isinstance(destination_name, str) or not isinstance(relative, str):
            raise PromptConfigurationError("Invalid agent.reference_files entry")
        source = _project_file(relative)
        if not source.is_file():
            raise PromptConfigurationError(f"Reference file does not exist: {relative}")
        result[destination_name] = source
    return result


def _project_file(relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise PromptConfigurationError(f"Project-relative path expected: {relative}")
    resolved = (PROJECT_ROOT / path).resolve()
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise PromptConfigurationError(f"Path escapes project root: {relative}") from exc
    return resolved


def render_prompt(agent_config: dict[str, Any], name: str, **values: Any) -> str:
    """Render a configured prompt file with explicit caller-provided values."""
    template = load_prompt(agent_config, name)
    normalized = {key: str(value) for key, value in values.items()}
    try:
        return template.format_map(normalized).strip()
    except KeyError as exc:
        raise PromptConfigurationError(
            f"Prompt {name} references an unknown placeholder: {exc.args[0]}"
        ) from exc
