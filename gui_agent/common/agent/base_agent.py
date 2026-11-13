"""Agent factory: swap the underlying agent implementation by changing ONE line."""

from typing import Callable, Literal, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

import gui_agent.common.gui_state as gui_state
# ─────────────────────────────────────────────────────────────
# 👇 THE ONE LINE YOU CHANGE: "create_agent" | "deep_agent" | "react_agent"
AGENT_BACKEND: Literal["create_agent", "deep_agent", "react_agent"] = "create_agent"
# ─────────────────────────────────────────────────────────────

KEEP_TOOL_EXCHANGES = 2
GUI_HEADER = "\n\n## CURRENT GUI STATE\n"


# ── Shared logic ─────────────────────────────────────────────

def trim_tool_history(
    messages: Sequence[BaseMessage], keep: int = KEEP_TOOL_EXCHANGES
) -> list[BaseMessage]:
    """Keep the conversation plus only the last `keep` tool exchanges.

    An exchange = one AIMessage with tool_calls + its ToolMessage replies, so
    tool results are never orphaned from their calls. Only the model's view is
    trimmed; graph state is untouched.
    """
    ai_tool_idx = [
        i for i, m in enumerate(messages)
        if isinstance(m, AIMessage) and m.tool_calls
    ]
    if len(ai_tool_idx) <= keep:
        return list(messages)

    cut = ai_tool_idx[-keep]
    head = [
        m for m in messages[:cut]
        if not isinstance(m, ToolMessage)
        and not (isinstance(m, AIMessage) and m.tool_calls)
    ]
    return head + list(messages[cut:])


def gui_suffix() -> str:
    ctx = gui_state.get_context()
    return f"{GUI_HEADER}{ctx}\n" if ctx else ""


# ── Backend 1 & 2: middleware (create_agent, create_deep_agent) ──

def _build_middleware():
    from langchain.agents.middleware import AgentMiddleware

    class GuiStateMiddleware(AgentMiddleware):
        """Before every LLM call: trim old tool results + append fresh GUI state."""

        def _prepare(self, request):
            overrides = {"messages": trim_tool_history(request.messages)}
            extra = gui_suffix()
            if extra:
                if hasattr(request, "system_message"):  # newer langchain
                    base = str(request.system_message.text) if request.system_message else ""
                    overrides["system_message"] = SystemMessage(content=base + extra)
                else:  # langchain 1.0.x
                    overrides["system_prompt"] = (request.system_prompt or "") + extra
            return request.override(**overrides)

        def wrap_model_call(self, request, handler):
            return handler(self._prepare(request))

        async def awrap_model_call(self, request, handler):
            return await handler(self._prepare(request))

    return GuiStateMiddleware()


def _build_create_agent(llm, tools, system_prompt):
    from langchain.agents import create_agent

    return create_agent(
        model=llm,
        tools=list(tools),
        system_prompt=system_prompt,
        middleware=[_build_middleware()],
    )


def _build_deep_agent(llm, tools, system_prompt):
    from deepagents import create_deep_agent

    return create_deep_agent(
        model=llm,
        tools=list(tools),
        system_prompt=system_prompt,
        middleware=[_build_middleware()],
    )


# ── Backend 3: prompt callable (langgraph create_react_agent) ──

def _build_react_agent(llm, tools, system_prompt):
    from langgraph.prebuilt import create_react_agent

    def prompt_callable(state: dict) -> list[BaseMessage]:
        trimmed = trim_tool_history(state.get("messages", []))
        return [SystemMessage(content=system_prompt + gui_suffix())] + trimmed

    return create_react_agent(model=llm, tools=list(tools), prompt=prompt_callable)


# ── Public factory (signature unchanged) ─────────────────────

_BUILDERS: dict[str, Callable] = {
    "create_agent": _build_create_agent,
    "deep_agent": _build_deep_agent,
    "react_agent": _build_react_agent,
}


def langchain_create_agent(
    llm: BaseChatModel,
    tools: Sequence[BaseTool],
    system_prompt: str,
):
    """Create an agent with rolling GUI-state injection.

    Backend is chosen by AGENT_BACKEND. All backends return a compiled
    LangGraph graph invoked with {"messages": [...]}.
    """
    return _BUILDERS[AGENT_BACKEND](llm, tools, system_prompt)