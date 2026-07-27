from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.ui_schema.agent_llm import create_chat_model
from backend.modules.ui_schema.agent_middleware import create_tool_error_middleware
from backend.modules.ui_schema.agent_prompts import load_prompt
from backend.modules.ui_schema.agent_tools import create_agent_tools


def create_ui_schema_agent(
    *,
    run_path: Path,
    llm_settings: dict[str, Any],
    agent_config: dict[str, Any],
):
    """Create a deliberately small tool-calling agent for UI Schema sync.

    The general Deep Agents harness adds planning, filesystem and execution
    tools together with their own prompts. This workflow is a bounded data
    transformation and must expose only domain tools; otherwise provider models
    can spend most of the budget on todo/filesystem loops.
    """
    try:
        from langchain.agents import create_agent
        from langgraph.checkpoint.memory import MemorySaver
    except ImportError as exc:
        raise RuntimeError(
            "LangChain agent dependencies are not installed. Install project requirements.txt."
        ) from exc

    return create_agent(
        model=create_chat_model(llm_settings, agent_config),
        tools=create_agent_tools(run_path=run_path, agent_config=agent_config),
        system_prompt=load_prompt(agent_config, "system"),
        middleware=[create_tool_error_middleware()],
        checkpointer=MemorySaver(),
        name="ui_schema_sync_agent",
    )
