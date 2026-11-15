"""Chat model for one-shot extraction, configured like the GUI agent.

Mirrors ``gui_agent.main.load_llm``. That module cannot be imported because it
loads .env and builds the agent at import time.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Dict, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUEST_TIMEOUT_S = 180.0

Completer = Callable[[str, str], str]


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_path)


def model_config() -> Dict[str, str]:
    provider = os.getenv("MODEL_PROVIDER", "openrouter").lower()
    model = os.getenv("MODEL_NAME", "dots-studio/dots-3-note-preview:free")
    if provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        base_url = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY") or ""
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    elif provider == "ollama":
        api_key = "ollama"
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    else:
        api_key = os.getenv("OPENROUTER_API_KEY") or ""
        base_url = "https://openrouter.ai/api/v1"
    return {"provider": provider, "model": model, "api_key": api_key, "base_url": base_url}


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(
        part.get("text", "") if isinstance(part, dict) else str(part)
        for part in content
    )


def make_completer() -> Tuple[Completer, str]:
    """A ``complete(system, user) -> text`` function and the model name."""
    _load_env()
    config = model_config()
    if not config["api_key"]:
        raise RuntimeError(
            "no LLM API key configured: set OPENROUTER_API_KEY or OPENAI_API_KEY in .env"
        )
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=config["model"],
        api_key=config["api_key"],
        base_url=config["base_url"],
        temperature=0,
        request_timeout=REQUEST_TIMEOUT_S,
    )

    def complete(system: str, user: str) -> str:
        reply = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        return _content_text(reply.content)

    return complete, config["model"]


__all__ = ["Completer", "make_completer", "model_config"]
