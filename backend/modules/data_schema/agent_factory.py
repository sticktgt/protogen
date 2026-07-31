from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.data_schema.agent_llm import (
    create_chat_model,
    sequential_tool_calls_supported,
)
from backend.modules.data_schema.agent_middleware import (
    create_sequential_tool_call_middleware,
    create_tool_error_middleware,
)
from backend.modules.data_schema.agent_prompts import load_prompt
from backend.modules.data_schema.agent_tools import create_agent_tools

_PRIMARY_TOOLS = {
    "load_synchronization_context",
    "write_data_schema_dictionaries",
    "write_data_schema_core",
    "write_data_schema_relations",
    "patch_data_schema_dictionaries",
    "patch_data_schema_core",
    "patch_data_schema_relations",
    "remove_data_schema_additions",
    "write_data_schema_traceability",
    "validate_data_schema_state",
}


def create_data_schema_agent(
    *,
    run_path: Path,
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
):
    """Create the bounded primary Data Schema synchronization agent."""
    try:
        from langchain.agents import create_agent
        from langgraph.checkpoint.memory import MemorySaver
    except ImportError as exc:
        raise RuntimeError(
            "LangChain agent dependencies are not installed. Install project requirements.txt."
        ) from exc

    middleware = [create_tool_error_middleware()]
    sequential = create_sequential_tool_call_middleware(
        enabled=sequential_tool_calls_supported(llm_settings, agent_config)
    )
    if sequential is not None:
        middleware.insert(0, sequential)

    return create_agent(
        model=create_chat_model(
            llm_settings,
            agent_config,
            profile="generation",
        ),
        tools=create_agent_tools(
            run_path=run_path,
            agent_config=agent_config,
            allowed_tools=_PRIMARY_TOOLS,
        ),
        system_prompt=load_prompt(agent_config, "system"),
        middleware=middleware,
        checkpointer=MemorySaver(),
        name="data_schema_primary_agent",
    )
