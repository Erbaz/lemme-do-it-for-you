"""Base agent factory for creating LangGraph ReAct agents."""

from langgraph.prebuilt import create_react_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from typing import Sequence


def langchain_create_agent(
    llm: BaseChatModel,
    tools: Sequence[BaseTool],
    system_prompt: str
) -> "CompiledStateGraph":
    """Create a ReAct agent with the given LLM, tools, and system prompt.

    This uses langgraph.prebuilt.create_react_agent, a standard ReAct loop
    without the deepagents planning/todo-list/subagent orchestration that
    caused the agent to over-explore and use incorrect tools (e.g. grep
    instead of clicking UI elements).

    Args:
        llm: The language model to use.
        tools: Sequence of tools available to the agent.
        system_prompt: System prompt describing the agent's role and capabilities.

    Returns:
        A compiled LangGraph ReAct agent.
    """
    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=system_prompt,
    )