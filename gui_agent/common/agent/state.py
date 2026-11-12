"""Agent state definitions."""

from typing import TypedDict, List, Any
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """State for the GUI agent."""
    messages: List[BaseMessage]
    current_task: str
    metadata: dict[str, Any]