"""Discovery: a snapshot of every interactable element, with identity.

The walker mirrors ``gui_agent``'s rules and selector grammar (imported, not
copied) but recurses itself so it can keep the properties ``gui_agent`` drops:
process id, ``IsPassword``, and window context. It also keeps elements on
secondary monitors at negative coordinates, which ``_is_mouse_interactable``
silently rejects.

The index is a *snapshot*. It is refreshed on a cache miss rather than polled.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pythoncom
import uiautomation as auto

from gui_agent.windows.tools.uia_tools.get_interactable_elements import (
    INTERACTABLE_TYPES,
    _build_selector,
)

from .fingerprint import INTERACTIVE_TYPES, Fingerprint

#: An ancestor covering this fraction of its top-level window is the window
#: itself, not the thing the human meant to click. Without this a click on an
#: empty Chromium canvas resolves to ``id:app``.
WINDOW_COVER_FRACTION = 0.80

#: Matches ``find_element``'s ``maxDepth=10``, i.e. the deepest element
#: ``click_element`` can replay.
DEFAULT_MAX_DEPTH = 10

#: Minimum seconds between two cache-miss rebuilds.
REFRESH_INTERVAL_S = 0.75


@dataclass(frozen=True)
class DiscoveredElement:
    selector: str
    rect: Tuple[int, int, int, int]
    fingerprint: Fingerprint
    control_type: str
    depth: int
    window_title: str = ""
    window_pid: int = 0


@dataclass
class BuildStats:
    count: int = 0
    elapsed_ms: float = 0.0
    skipped_window_like: int = 0
    skipped_unnameable: int = 0


def _safe_str(element, attr: str) -> str:
    try:
        return getattr(element, attr, "") or ""
    except Exception:
        return ""


def _safe_int(element, attr: str) -> int:
    try:
        return int(getattr(element, attr, 0) or 0)
    except Exception:
        return 0


def _safe_bool(element, attr: str) -> bool:
    try:
        return bool(getattr(element, attr, False))
    except Exception:
        return False


def _is_interactable(element) -> bool:
    """gui_agent's predicate, minus the negative-coordinate rejection."""
    try:
        if getattr(element, "IsOffscreen", True):
            return False
        if not getattr(element, "IsEnabled", False):
            return False
        rect = getattr(element, "BoundingRectangle", None)
        if rect is None or rect.width() <= 0 or rect.height() <= 0:
            return False
    except Exception:
        return False
    if _safe_str(element, "ControlTypeName") in INTERACTABLE_TYPES:
        return True
    return bool(_safe_str(element, "Name") or _safe_str(element, "AutomationId"))


def _make_fingerprint(element, rect: Tuple[int, int, int, int]) -> Fingerprint:
    return Fingerprint(
        control_type=_safe_str(element, "ControlTypeName"),
        name=_safe_str(element, "Name"),
        automation_id=_safe_str(element, "AutomationId"),
        class_name=_safe_str(element, "ClassName"),
        rect=rect,
        pid=_safe_int(element, "ProcessId"),
        is_password=_safe_bool(element, "IsPassword"),
    )


class DiscoveryIndex:
    """Spatial index of interactable elements for click-to-selector mapping."""

    def __init__(self, max_depth: int = DEFAULT_MAX_DEPTH) -> None:
        self._max_depth = max_depth
        self._elements: List[DiscoveredElement] = []
        self._last_build = 0.0
        self.stats = BuildStats()

    @property
    def max_depth(self) -> int:
        return self._max_depth

    @property
    def elements(self) -> List[DiscoveredElement]:
        return self._elements

    def build(self, max_depth: Optional[int] = None) -> int:
        if max_depth is not None:
            self._max_depth = max_depth
        t0 = time.monotonic()
        pythoncom.CoInitialize()

        elements: List[DiscoveredElement] = []
        stats = BuildStats()
        desktop = auto.GetRootControl()
        if desktop is not None:
            self._walk(desktop, elements, stats, depth=1)

        self._elements = elements
        self._last_build = time.monotonic()
        stats.count = len(elements)
        stats.elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
        self.stats = stats
        return len(elements)

    def _walk(
        self,
        parent,
        out: List[DiscoveredElement],
        stats: BuildStats,
        depth: int,
        window_title: str = "",
        window_pid: int = 0,
        window_area: int = 0,
    ) -> None:
        if depth > self._max_depth:
            return
        try:
            children = parent.GetChildren()
        except Exception:
            return

        for child in children:
            try:
                rect = child.BoundingRectangle
            except Exception:
                continue
            if rect is None:
                continue
            r = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
            area = max(0, r[2] - r[0]) * max(0, r[3] - r[1])

            title, pid, context_area = window_title, window_pid, window_area
            if depth == 1:
                title = _safe_str(child, "Name")
                pid = _safe_int(child, "ProcessId")
                context_area = area

            if _is_interactable(child):
                selector = _build_selector(child)
                if not selector:
                    stats.skipped_unnameable += 1
                elif context_area and area >= WINDOW_COVER_FRACTION * context_area:
                    stats.skipped_window_like += 1
                else:
                    out.append(
                        DiscoveredElement(
                            selector=selector,
                            rect=r,
                            fingerprint=_make_fingerprint(child, r),
                            control_type=_safe_str(child, "ControlTypeName"),
                            depth=depth,
                            window_title=title,
                            window_pid=pid,
                        )
                    )

            self._walk(child, out, stats, depth + 1, title, pid, context_area)

    def find_at(self, x: int, y: int) -> Optional[DiscoveredElement]:
        """Pick the element a human meant by (x, y).

        Interactive controls (button, item, edit, ...) win over the decorative
        child under the same point: a taskbar button contains a 24 px icon, and
        ``id:Icon`` is not what the human clicked. Within a tier, smallest area
        wins; ties go to the deeper element.
        """
        best: Optional[DiscoveredElement] = None
        best_key: Optional[Tuple[int, int, int]] = None
        for el in self._elements:
            left, top, right, bottom = el.rect
            if left <= x <= right and top <= y <= bottom:
                area = (right - left) * (bottom - top)
                tier = 0 if el.control_type in INTERACTIVE_TYPES else 1
                key = (tier, area, -el.depth)
                if best_key is None or key < best_key:
                    best = el
                    best_key = key
        return best

    def maybe_refresh(self, min_interval: float = REFRESH_INTERVAL_S) -> bool:
        """Rebuild at most once per interval. Returns True if it rebuilt."""
        if time.monotonic() - self._last_build < min_interval:
            return False
        self.build()
        return True

    def refresh(self) -> int:
        return self.build()

    def __len__(self) -> int:
        return len(self._elements)


__all__ = ["BuildStats", "DiscoveredElement", "DiscoveryIndex"]
