from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from backend.modules.data_schema.agent_llm_retry import invoke_with_transient_llm_retry


class LlmConfigurationError(ValueError):
    pass


LlmProfile = Literal["generation", "correction", "review", "connection"]


def user_llm_settings(user: dict[str, Any]) -> dict[str, Any]:
    settings = user.get("settings", {}) if isinstance(user, dict) else {}
    llm = settings.get("llm", {}) if isinstance(settings, dict) else {}
    return dict(llm) if isinstance(llm, dict) else {}


def public_llm_settings(
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
) -> dict[str, Any]:
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
    model_provider = (
        provider_map.get(provider) if isinstance(provider_map, dict) else None
    )
    if not isinstance(model_provider, str) or not model_provider:
        raise LlmConfigurationError(
            f"Провайдер LLM не поддерживается агентом Data Schema: {provider}"
        )

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


def create_chat_model(
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
    *,
    profile: LlmProfile = "generation",
):
    try:
        from langchain.chat_models import init_chat_model
    except ImportError as exc:
        raise RuntimeError("LangChain is not installed") from exc

    normalized = normalize_llm_settings(llm_settings, agent_config)
    llm_config = _llm_config(agent_config)
    kwargs: dict[str, Any] = {
        "model": normalized["model"],
        "model_provider": normalized["model_provider"],
        "max_retries": _required_number(llm_config, "max_retries", int),
        "temperature": _required_number(llm_config, "temperature", float),
        "timeout": _required_number(
            agent_config.get("execution", {}), "request_timeout_seconds", int
        ),
    }
    if normalized["api_key"]:
        kwargs["api_key"] = normalized["api_key"]
    elif normalized["provider"] in _string_set(
        llm_config.get("placeholder_api_key_for")
    ):
        kwargs["api_key"] = "not-required"
    if normalized["base_url"]:
        kwargs["base_url"] = normalized["base_url"]
    if normalized["provider"] in _string_set(
        llm_config.get("openai_chat_completions_for")
    ):
        kwargs["use_responses_api"] = False
    reasoning_effort = _reasoning_effort(
        llm_config,
        provider=normalized["provider"],
        model=normalized["model"],
        profile=profile,
    )
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort
    return init_chat_model(**kwargs)


def sequential_tool_calls_supported(
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
) -> bool:
    normalized = normalize_llm_settings(llm_settings, agent_config)
    configured = _string_set(
        _llm_config(agent_config).get("disable_parallel_tool_calls_for")
    )
    return normalized["provider"] in configured


def test_llm_connection(
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
    prompt: str,
) -> dict[str, Any]:
    try:
        from langchain_core.tools import tool
    except ImportError as exc:
        raise RuntimeError("LangChain core tools are not installed") from exc

    expected = str(
        _required_value(_llm_config(agent_config), "connection_test_expected")
    )

    @tool
    def data_schema_connection_probe() -> str:
        """Return the Data Schema LLM connection test marker."""
        return expected

    model = create_chat_model(llm_settings, agent_config, profile="connection")
    try:
        bound = model.bind_tools([data_schema_connection_probe], tool_choice="required")
        response = invoke_with_transient_llm_retry(
            lambda: bound.invoke(prompt),
            agent_config=agent_config,
            operation_name="проверки соединения с LLM",
        )
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
    name = (
        first.get("name") if isinstance(first, dict) else getattr(first, "name", None)
    )
    if name != "data_schema_connection_probe":
        raise RuntimeError(
            f"Модель вызвала неожиданный инструмент: {name or '<unknown>'}"
        )

    return {
        "ok": True,
        "message": "Соединение с LLM и вызов инструментов работают",
        "llm": public_llm_settings(llm_settings, agent_config),
        "tool_call_supported": True,
    }


def _reasoning_effort(
    llm_config: dict[str, Any],
    *,
    provider: str,
    profile: LlmProfile,
    model: str | None = None,
) -> str | None:
    provider_config = _reasoning_profile(
        llm_config.get("reasoning_effort", {}),
        provider=provider,
        setting_name="reasoning_effort",
    )
    model_config: dict[str, Any] | None = None
    if model:
        by_model = llm_config.get("reasoning_effort_by_model", {})
        if by_model is not None and not isinstance(by_model, dict):
            raise LlmConfigurationError(
                "Invalid agent LLM setting: reasoning_effort_by_model"
            )
        provider_models = (
            by_model.get(provider) if isinstance(by_model, dict) else None
        )
        if provider_models is not None and not isinstance(provider_models, dict):
            raise LlmConfigurationError(
                f"Invalid model reasoning profiles for provider: {provider}"
            )
        candidate = (
            provider_models.get(model)
            if isinstance(provider_models, dict)
            else None
        )
        if candidate is not None and not isinstance(candidate, dict):
            raise LlmConfigurationError(
                f"Invalid model reasoning profile for provider {provider}, model {model}"
            )
        model_config = candidate

    value = (model_config or {}).get(profile)
    if value is None:
        value = (provider_config or {}).get(profile)
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized not in {"none", "low", "medium", "high"}:
        target = f"{provider}/{model}" if model_config is not None else provider
        raise LlmConfigurationError(
            f"Invalid reasoning_effort for {target}, profile {profile}"
        )
    return normalized


def _reasoning_profile(
    configured: Any,
    *,
    provider: str,
    setting_name: str,
) -> dict[str, Any] | None:
    if configured is None:
        return None
    if not isinstance(configured, dict):
        raise LlmConfigurationError(f"Invalid agent LLM setting: {setting_name}")
    provider_config = configured.get(provider)
    if provider_config is None:
        return None
    if not isinstance(provider_config, dict):
        raise LlmConfigurationError(
            f"Invalid agent LLM reasoning profile for provider: {provider}"
        )
    return provider_config


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


def _required_value(config: Any, key: str) -> Any:
    if not isinstance(config, dict) or key not in config:
        raise LlmConfigurationError(f"Agent LLM setting is not configured: {key}")
    return config[key]


def _required_number(config: Any, key: str, converter):
    value = _required_value(config, key)
    try:
        return converter(value)
    except (TypeError, ValueError) as exc:
        raise LlmConfigurationError(f"Invalid agent LLM setting: {key}") from exc
