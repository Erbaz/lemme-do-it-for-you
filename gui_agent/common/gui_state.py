"""Desktop + foreground snapshot manager for the GUI Agent.

Captures lightweight UI Automation snapshots of the desktop and foreground
window so the LLM can be injected with current GUI context on every turn.
"""

from __future__ import annotations

import threading
from typing import Optional

try:
    import uiautomation as auto
except ImportError:  # pragma: no cover - uiautomation is Windows-only
    auto = None  # type: ignore[assignment]

import structlog

logger = structlog.get_logger("gui_agent.gui_state")


class _GuiState:
    """Internal state holder (module-level singleton)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._desktop_context: Optional[str] = None
        self._foreground_context: Optional[str] = None
        self._initialized = False

    def _safe(self, fn, default: str = "") -> str:
        """Run a UI Automation call safely, returning default on failure."""
        if auto is None:
            return default
        try:
            return fn() or default
        except Exception as e:
            logger.debug("UI Automation call failed", error=str(e))
            return default

    def _element_info(self, element) -> str:
        """Build a short description of a UI element."""
        if element is None:
            return ""
        parts = []
        name = getattr(element, "Name", None) or ""
        class_name = getattr(element, "ClassName", None) or ""
        ctrl_type = getattr(element, "ControlTypeName", None) or ""
        if name:
            parts.append(f'name="{name}"')
        if class_name:
            parts.append(f'class="{class_name}"')
        if ctrl_type:
            parts.append(f"type={ctrl_type}")
        return " | ".join(parts)

    def _walk(self, element, depth: int, max_depth: int) -> list[str]:
        """Recursively walk element tree, collecting short descriptions."""
        if element is None or depth > max_depth:
            return []
        lines = [f"  {'  ' * depth}{self._element_info(element)}"]
        try:
            children = element.GetChildren()
        except Exception:
            children = []
        for child in children:
            lines.extend(self._walk(child, depth + 1, max_depth))
        return lines

    def init_desktop_snapshot(self, max_depth: int = 5) -> None:
        """Capture the desktop snapshot (top-level windows)."""
        with self._lock:
            self._desktop_context = self._safe(
                lambda: self._capture_desktop(max_depth)
            )
            self._foreground_context = None
            self._initialized = True
            logger.info(
                "Desktop snapshot initialized",
                depth=max_depth,
                context_len=len(self._desktop_context or ""),
            )

    def _capture_desktop(self, max_depth: int) -> str:
        if auto is None:
            return "UI Automation not available"
        desktop = auto.GetRootControl()
        lines = ["DESKTOP SNAPSHOT:"]
        lines.extend(self._walk(desktop, 0, max_depth))
        return "\n".join(lines)

    def refresh_foreground_snapshot(self, max_depth: int = 5) -> None:
        """Capture the currently focused/foreground window."""
        with self._lock:
            self._foreground_context = self._safe(
                lambda: self._capture_foreground(max_depth)
            )
            logger.debug(
                "Foreground snapshot refreshed",
                depth=max_depth,
                context_len=len(self._foreground_context or ""),
            )

    def _capture_foreground(self, max_depth: int) -> str:
        if auto is None:
            return "UI Automation not available"
        foreground = auto.GetForegroundControl()
        lines = ["FOREGROUND WINDOW:"]
        lines.extend(self._walk(foreground, 0, max_depth))
        return "\n".join(lines)

    def get_context(self) -> str:
        """Return combined GUI context string for LLM injection."""
        with self._lock:
            parts = []
            if self._desktop_context:
                parts.append(self._desktop_context)
            if self._foreground_context:
                parts.append(self._foreground_context)
            return "\n".join(parts)

    def reset(self) -> None:
        """Clear all snapshots (use before starting a new run)."""
        with self._lock:
            self._desktop_context = None
            self._foreground_context = None
            self._initialized = False


# Module-level singleton
gui_state = _GuiState()


# Module-level wrapper functions so both `import gui_agent.common.gui_state as gui_state`
# and `from gui_agent.common.gui_state import gui_state` work.
def get_context() -> str:
    """Return combined GUI context string for LLM injection."""
    return gui_state.get_context()


def init_desktop_snapshot(max_depth: int = 5) -> None:
    """Capture the desktop snapshot (top-level windows)."""
    gui_state.init_desktop_snapshot(max_depth=max_depth)


def refresh_foreground_snapshot(max_depth: int = 5) -> None:
    """Capture the currently focused/foreground window."""
    gui_state.refresh_foreground_snapshot(max_depth=max_depth)


def reset() -> None:
    """Clear all snapshots (use before starting a new run)."""
    gui_state.reset()


__all__ = ["gui_state", "get_context", "init_desktop_snapshot", "refresh_foreground_snapshot", "reset"]
