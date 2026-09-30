"""
Logging setup for SelfCorrectingVisionAgentV3.

Creates a per-session timestamped log file in .logs/ directory.
Uses LlamaIndex's TokenCountingHandler to track prompt/completion tokens.
All log entries are prefixed with ISO timestamps and are never truncated.
"""

import logging
import os
from datetime import datetime
from pathlib import Path

from llama_index.core.callbacks import TokenCountingHandler
from llama_index.core import Settings

# ---------------------------------------------------------------------------
# Session-level configuration
# ---------------------------------------------------------------------------

SESSION_START_TIME: datetime = datetime.now()
LOGS_DIR = Path(__file__).resolve().parent.parent / ".logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

SESSION_TIMESTAMP = SESSION_START_TIME.strftime("%Y-%m-%d_%H-%M-%S")
LOG_FILE_PATH = LOGS_DIR / f"{SESSION_TIMESTAMP}_agent.log"

# ---------------------------------------------------------------------------
# Python logger
# ---------------------------------------------------------------------------

_agent_logger = logging.getLogger(f"vision_agent_{SESSION_TIMESTAMP}")
_agent_logger.setLevel(logging.DEBUG)
_agent_logger.propagate = False

# File handler — append mode (never truncates)
_file_handler = logging.FileHandler(LOG_FILE_PATH, mode="a", encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_file_handler.setFormatter(_file_formatter)
_agent_logger.addHandler(_file_handler)

# Console handler — mirror to stdout for verbose output
_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_console_formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
_console_handler.setFormatter(_console_formatter)
_agent_logger.addHandler(_console_handler)


def get_logger() -> logging.Logger:
    """Return the session logger instance."""
    return _agent_logger


# ---------------------------------------------------------------------------
# LlamaIndex TokenCountingHandler
# ---------------------------------------------------------------------------

_token_counter = TokenCountingHandler(logger=_agent_logger)

# Attach to Settings so every llm.chat() call fires callbacks
Settings.callback_manager.add_handler(_token_counter)


def reset_token_counts() -> None:
    """Reset per-call token counters before a new LLM interaction."""
    _token_counter.reset_counts()


def get_token_snapshot() -> dict:
    """Return current token counts as a snapshot dict."""
    return {
        "prompt_tokens": _token_counter.prompt_llm_token_count,
        "completion_tokens": _token_counter.completion_llm_token_count,
        "total_tokens": _token_counter.total_llm_token_count,
    }


# ---------------------------------------------------------------------------
# Context-size & token-length incrementer
# ---------------------------------------------------------------------------

class TokenIncrementer:
    """
    Tracks cumulative token consumption against the context window.

    Provides a running incrementer that grows with each LLM call,
    showing how close we are to exhausting the context window.
    """

    def __init__(self, context_window: int = 8192):
        self.context_window: int = context_window
        self._cumulative_prompt: int = 0
        self._cumulative_completion: int = 0
        self._cumulative_total: int = 0
        self._call_count: int = 0

    def record_call(self, prompt_tokens: int, completion_tokens: int) -> dict:
        """Record tokens from a completed LLM call and return a summary."""
        self._call_count += 1
        self._cumulative_prompt += prompt_tokens
        self._cumulative_completion += completion_tokens
        self._cumulative_total = self._cumulative_prompt + self._cumulative_completion

        remaining = max(0, self.context_window - self._cumulative_total)
        pct_used = (self._cumulative_total / self.context_window) * 100 if self.context_window else 0
        pct_remaining = 100 - pct_used

        return {
            "call_number": self._call_count,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cumulative_prompt": self._cumulative_prompt,
            "cumulative_completion": self._cumulative_completion,
            "cumulative_total": self._cumulative_total,
            "context_window": self.context_window,
            "remaining_tokens": remaining,
            "percent_used": round(pct_used, 2),
            "percent_remaining": round(pct_remaining, 2),
        }

    def reset(self, context_window: int | None = None) -> None:
        """Reset all counters. Optionally update context window size."""
        self._cumulative_prompt = 0
        self._cumulative_completion = 0
        self._cumulative_total = 0
        self._call_count = 0
        if context_window is not None:
            self.context_window = context_window


# Global incrementer — one per session
_token_incrementer = TokenIncrementer(context_window=8192)


def get_token_incrementer() -> TokenIncrementer:
    """Return the session-wide TokenIncrementer."""
    return _token_incrementer


def update_context_window(context_window: int) -> None:
    """Update the context window size on the incrementer."""
    _token_incrementer.context_window = context_window
