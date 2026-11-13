"""Tracks selectors that have failed to find an element.

Purpose: Stop the LLM from repeatedly trying selectors that already returned
"No elements found" or "Selector is not correct". This reduces tool-call bloat,
prevents context pollution from repeated failure messages, and helps the agent
pivot to a different approach faster.

Usage:
    from gui_agent.common.selector_tracker import SelectorTracker
    tracker = SelectorTracker()
    if tracker.is_failed(selector):
        return "Selector previously failed: ..."  # skip tool execution
    # ... run tool ...
    if not found:
        tracker.record_failure(selector)
"""

import threading


class SelectorTracker:
    """Thread-safe tracker for failed selectors within a single agent run."""

    def __init__(self):
        self._failed = set()
        self._lock = threading.Lock()

    def is_failed(self, selector: str) -> bool:
        with self._lock:
            return selector in self._failed

    def record_failure(self, selector: str) -> None:
        with self._lock:
            self._failed.add(selector)

    def clear(self) -> None:
        with self._lock:
            self._failed.clear()

    def count(self) -> int:
        with self._lock:
            return len(self._failed)


# Module-level singleton for use across tool functions within one agent run.
selector_tracker = SelectorTracker()
