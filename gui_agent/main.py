"""CLI entry point for the GUI Agent."""

import os
import sys
import argparse
import time
import threading
from typing import Optional
from pathlib import Path
import structlog

# Load .env from project root (parent of gui_agent)
project_root = Path(__file__).parent.parent
env_path = project_root / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=env_path)
    print(f"Loaded .env from {env_path}")

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui_agent.common.platform.detector import PlatformDetector
from gui_agent.common.utils.logging import setup_logging
from gui_agent.common.utils.file_logging import setup_file_logging, get_log_file
from gui_agent.common.agent.callbacks import GuiAgentCallbackHandler
from gui_agent.common.agent import langchain_create_agent
from gui_agent.windows.tools.registry import TOOL_REGISTRY


# Import system prompt from separate file
from gui_agent.sys_prompt import SYSTEM_PROMPT

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None

logger = structlog.get_logger("gui_agent.main")


# Suppress harmless "Exception ignored in sys.unraisablehook" from
# pythoncom.CoInitialize() calls that never get CoUninitialize() on thread exit.
# This is noise only; COM apartments are cleaned up when threads die.
def _quiet_unraisablehook(hook_args):
    pass  # Suppress all unraisablehook noise


sys.unraisablehook = _quiet_unraisablehook



def load_llm() -> Optional["BaseChatModel"]:
    """Load LLM from environment configuration."""
    if ChatOpenAI is None:
        return None

    # Support multiple providers via MODEL_PROVIDER
    provider = os.getenv("MODEL_PROVIDER", "openrouter").lower()
    model_name = os.getenv("MODEL_NAME", "dots-studio/dots-3-note-preview:free")

    if provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    elif provider == "ollama":
        api_key = "ollama"  # dummy key for ollama
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    else:
        api_key = os.getenv("OPENROUTER_API_KEY")
        base_url = "https://openrouter.ai/api/v1"

    if not api_key:
        return None

    logger.info("Loading LLM", provider=provider, model=model_name, base_url=base_url)

    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
        request_timeout=30.0,
        reasoning_effort="low",  # Enable thinking for complex GUI tasks
    )


def run_agent_with_timeout(agent, inputs, timeout_seconds: int, callbacks=None):
    """Run agent.invoke() in a daemon thread with a real timeout.

    Args:
        agent: CompiledLangGraph agent.
        inputs: Dict to pass to agent.invoke().
        timeout_seconds: Maximum seconds to wait.
        callbacks: Optional list of callback handlers.

    Returns:
        The agent.invoke() result dict.

    Raises:
        TimeoutError: If the agent does not finish within timeout_seconds.
    """
    result_container = {}
    exception_container = {}

    def target():
        try:
            config = {"callbacks": callbacks} if callbacks else {}
            result_container["result"] = agent.invoke(inputs, config=config)
        except Exception as e:  # noqa: BLE001
            exception_container["error"] = e

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        raise TimeoutError(f"Agent invocation timed out after {timeout_seconds}s")

    if "error" in exception_container:
        raise exception_container["error"]

    return result_container.get("result")


def load_tools() -> list:
    """Load all available tools (test tools + UIA tools)."""
    return TOOL_REGISTRY

    
def main():
    parser = argparse.ArgumentParser(description="GUI Agent - Windows GUI Automation")
    parser.add_argument("task", nargs="?", default="test", help="Task for the agent")
    parser.add_argument("--log-level", default="INFO", help="Log level")
    parser.add_argument("--timeout", type=int, default=60, help="Agent invocation timeout in seconds")
    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level)
    log_handler = setup_file_logging()
    log_file = get_log_file()
    print(f"Log file: {log_file}")
    logger.info("Log file initialized", log_file=str(log_file))
    logger.info("Starting GUI Agent", task=args.task, log_level=args.log_level, timeout=args.timeout)

    # Detect platform
    platform = PlatformDetector.detect()
    print(f"Platform: {platform.value}")
    logger.info("Platform detected", platform=platform.value)

    # Load LLM
    llm = load_llm()
    if llm is None:
        print("Warning: No LLM configured (missing API key). Running in test mode.")
        print("Task:", args.task)
        print("Available tools:", ", ".join([t.name for t in load_tools()]))
        return 0
    else:
        print(f"Loaded LLM: {llm.model})")

    # Create agent
    tools = load_tools()
    logger.info("Creating agent", tool_count=len(tools), tool_names=[t.name for t in tools])
    agent = langchain_create_agent(llm, tools, SYSTEM_PROMPT)

    # Invoke agent with timeout
    from langchain_core.messages import HumanMessage
    print(f"Invoking agent with task: {args.task}")
    logger.info("Invoking agent", task=args.task)

    start_time = time.time()
    try:
        result = run_agent_with_timeout(
            agent,
            {"messages": [HumanMessage(content=args.task)]},
            timeout_seconds=args.timeout,
            callbacks=[GuiAgentCallbackHandler()],
        )
        elapsed = time.time() - start_time
        logger.info("Agent invocation completed", elapsed_seconds=elapsed)
    except TimeoutError as e:
        elapsed = time.time() - start_time
        logger.error("Agent invocation timed out", error=str(e), elapsed_seconds=elapsed)
        print(f"Agent invocation timed out after {elapsed:.1f}s: {e}")
        return 1
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("Agent invocation failed", error=str(e), elapsed_seconds=elapsed, exc_info=True)
        print(f"Agent invocation failed after {elapsed:.1f}s: {e}")
        return 1

    # Print result
    for msg in result.get("messages", []):
        if hasattr(msg, "content") and msg.content:
            print(msg.content)

    return 0


if __name__ == "__main__":
    sys.exit(main())