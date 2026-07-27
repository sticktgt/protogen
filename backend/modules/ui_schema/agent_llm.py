from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit


class LlmConfigurationError(ValueError):
    pass


def user_llm_settings(user: dict[str, Any]) -> dict[str, Any]:
    settings = user.get("settings", {}) if isinstance(user, dict) else {}
    llm = settings.get("llm", {}) if isinstance(settings, dict) else {}
    return dict(llm) if isinstance(llm, dict) else {}


def public_llm_settings(llm_settings: dict[str, Any], agent_config: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_llm_settings(llm_settings, agent_config)
    return {
        "provider": normalized["provider"],
        "model": normalized["model"],
        "base_url": normalized.get("base_url") or None,
        "api_key_configured": bool(normalized.get("api_key")),
    }


def normalize_llm_settings(
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
) -> dict[str, Any]:
    llm_config = _llm_config(agent_config)
    provider = str(llm_settings.get("provider") or "").strip().lower()
    model = str(llm_settings.get("model") or "").strip()
    base_url = str(llm_settings.get("base_url") or "").strip()
    api_key = str(llm_settings.get("api_key") or "").strip()

    if not provider:
        raise LlmConfigurationError("В настройках пользователя не указан LLM provider")
    if not model:
        raise LlmConfigurationError("В настройках пользователя не указана LLM model")

    provider_map = llm_config.get("provider_map", {})
    model_provider = provider_map.get(provider) if isinstance(provider_map, dict) else None
    if not isinstance(model_provider, str) or not model_provider:
        raise LlmConfigurationError(f"Провайдер LLM не поддерживается агентом UI Schema: {provider}")

    defaults = llm_config.get("default_base_urls", {})
    if not base_url and isinstance(defaults, dict):
        base_url = str(defaults.get(provider) or "").strip()
    if provider in _string_set(llm_config.get("append_v1_base_url_for")) and base_url:
        base_url = _ensure_v1_url(base_url)

    if provider in _string_set(llm_config.get("api_key_required_for")) and not api_key:
        raise LlmConfigurationError(
            f"Для провайдера {provider} в настройках пользователя не задан api_key"
        )

    return {
        "provider": provider,
        "model": model,
        "model_provider": model_provider,
        "base_url": base_url,
        "api_key": api_key,
    }


def create_chat_model(llm_settings: dict[str, Any], agent_config: dict[str, Any]):
    try:
        from langchain.chat_models import init_chat_model
    except ImportError as exc:
        raise RuntimeError("LangChain is not installed") from exc

    normalized = normalize_llm_settings(llm_settings, agent_config)
    llm_config = _llm_config(agent_config)
    kwargs: dict[str, Any] = {
        "model": normalized["model"],
        "model_provider": normalized["model_provider"],
        "max_retries": int(llm_config.get("max_retries", 2)),
        "temperature": float(llm_config.get("temperature", 0)),
        "timeout": int(
            (agent_config.get("execution", {}) or {}).get("request_timeout_seconds", 300)
        ),
    }
    if normalized["api_key"]:
        kwargs["api_key"] = normalized["api_key"]
    elif normalized["provider"] in _string_set(llm_config.get("placeholder_api_key_for")):
        kwargs["api_key"] = "not-required"
    if normalized["base_url"]:
        kwargs["base_url"] = normalized["base_url"]
    if normalized["provider"] in _string_set(llm_config.get("openai_chat_completions_for")):
        kwargs["use_responses_api"] = False
    return init_chat_model(**kwargs)


def test_llm_connection(
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
    prompt: str,
) -> dict[str, Any]:
    try:
        from langchain_core.tools import tool
    except ImportError as exc:
        raise RuntimeError("LangChain core tools are not installed") from exc

    expected = str(_llm_config(agent_config).get("connection_test_expected") or "ok")

    @tool
    def ui_schema_connection_probe() -> str:
        """Return the UI Schema LLM connection test marker."""
        return expected

    model = create_chat_model(llm_settings, agent_config)
    try:
        bound = model.bind_tools([ui_schema_connection_probe], tool_choice="required")
        response = bound.invoke(prompt)
    except Exception as exc:
        raise RuntimeError(f"Не удалось подключиться к LLM: {exc}") from exc

    tool_calls = getattr(response, "tool_calls", None)
    if tool_calls is None and isinstance(response, dict):
        tool_calls = response.get("tool_calls")
    if not isinstance(tool_calls, list) or not tool_calls:
        raise RuntimeError(
            "Соединение с LLM установлено, но модель не выполнила обязательный tool call"
        )
    first = tool_calls[0]
    name = first.get("name") if isinstance(first, dict) else getattr(first, "name", None)
    if name != "ui_schema_connection_probe":
        raise RuntimeError(f"Модель вызвала неожиданный инструмент: {name or '<unknown>'}")

    return {
        "ok": True,
        "message": "Соединение с LLM и вызов инструментов работают",
        "llm": public_llm_settings(llm_settings, agent_config),
        "tool_call_supported": True,
    }


def _llm_config(agent_config: dict[str, Any]) -> dict[str, Any]:
    value = agent_config.get("llm", {}) if isinstance(agent_config, dict) else {}
    return value if isinstance(value, dict) else {}


def _string_set(value: Any) -> set[str]:
    return {str(item) for item in value} if isinstance(value, list) else set()


def _ensure_v1_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if not parsed.scheme or not parsed.netloc:
        raise LlmConfigurationError(f"Некорректный base_url: {value}")
    path = parsed.path.rstrip("/")
    if not path.endswith("/v1"):
        path = f"{path}/v1" if path else "/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))
