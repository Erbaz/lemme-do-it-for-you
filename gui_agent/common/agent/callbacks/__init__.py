"""Callbacks package - verbose tracing for the GUI agent."""

import structlog
from langchain_core.callbacks import BaseCallbackHandler
from typing import Any, Dict, Optional

logger = structlog.get_logger("gui_agent.callbacks")


class GuiAgentCallbackHandler(BaseCallbackHandler):
    """Callback handler that logs every ReAct step and refreshes GUI state."""

    ACTION_TOOLS = {"click_element", "type_text", "press_key"}

    def __init__(self, log_to_file: bool = True):
        self.log_to_file = log_to_file
        self._step_count = 0

    def _log(self, message: str, **kwargs) -> None:
        """Log with optional file output."""
        self._step_count += 1
        if self.log_to_file:
            print(f"[CALLBACK #{self._step_count}] {message}")
        logger.info("callback", step=self._step_count, message=message, **kwargs)

    def on_tool_start(
        self,
        serialized: Optional[Dict[str, Any]],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "unknown") if isinstance(serialized, dict) else "unknown"
        self._log(
            f"TOOL START: {tool_name}",
            tool=tool_name,
            input=str(input_str)[:500] if input_str else "",
        )

    def on_tool_end(
        self,
        output: Any,
        **kwargs: Any,
    ) -> None:
        output_str = str(output)[:1000]
        self._log(
            f"TOOL END: output={output_str}",
            output=output_str,
        )

        # Refresh foreground GUI snapshot after action-emitting tools
        tool_name = kwargs.get("name", "")
        if tool_name in self.ACTION_TOOLS:
            try:
                from gui_agent.common.gui_state import gui_state
                gui_state.refresh_foreground_snapshot(max_depth=5)
            except Exception as e:
                logger.error("Failed to refresh GUI state", error=str(e))

    def on_tool_error(
        self,
        error: Exception,
        **kwargs: Any,
    ) -> None:
        self._log(
            f"TOOL ERROR: {error}",
            error=str(error),
        )

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: list,
        **kwargs: Any,
    ) -> None:
        prompt_text = prompts[0] if prompts else ""
        self._log(
            f"LLM START: {len(prompt_text)} chars",
            prompt_preview=prompt_text[:300],
        )

    def on_llm_end(
        self,
        response: Any,
        **kwargs: Any,
    ) -> None:
        try:
            content = response.generations[0][0].text if response.generations else ""
        except Exception:
            content = str(response)[:500]
        self._log(
            f"LLM END: {len(content)} chars",
            response_preview=content[:300],
        )

    def on_llm_error(
        self,
        error: Exception,
        **kwargs: Any,
    ) -> None:
        self._log(
            f"LLM ERROR: {error}",
            error=str(error),
        )

    def on_chain_start(
        self,
        serialized: Optional[Dict[str, Any]],
        inputs: Dict[str, Any],
        **kwargs: Any,
    ) -> None:
        chain_name = serialized.get("name", "unknown") if isinstance(serialized, dict) else "unknown"
        self._log(
            f"CHAIN START: {chain_name}",
            chain=chain_name,
            inputs=str(inputs)[:300],
        )

        # Initialize desktop snapshot at session start
        try:
            from gui_agent.common.gui_state import gui_state
            gui_state.init_desktop_snapshot(max_depth=5)
            # Do NOT refresh foreground here — let it populate on first action
            # so an unrelated focused window (e.g., Notepad already open) does not
            # hijack the agent's initial context
        except Exception as e:
            logger.error("Failed to initialize GUI state", error=str(e))

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        **kwargs: Any,
    ) -> None:
        self._log(
            f"CHAIN END: outputs={str(outputs)[:500]}",
        )
