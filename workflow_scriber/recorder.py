"""Recorder: turn queued hook events into agent tool calls.

One state machine, one clock. Timestamps come from the hook (``t`` / ``ts``),
not from when the worker dequeues, so double-click detection is not distorted
by recording latency.

A click is recorded as the selector of the interactable element under the
cursor. A double-click is modeled as an *upgrade* of the first click record
rather than a second record, so replay does not click twice.

Context for extraction rides along on each record: the focused element, the
foreground window's element when the hit element belongs to another process,
and the window's named controls when the foreground window changes. Typed
characters are redacted while a password field has focus.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .discovery import DiscoveryIndex
from .fingerprint import candidate_selectors
from .normalize import key_text

DOUBLE_CLICK_S = 0.45
DOUBLE_CLICK_PX = 6

FocusProvider = Callable[[], Optional[Dict[str, Any]]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Record:
    tool: str
    args: Dict[str, Any] = field(default_factory=dict)
    note: str = ""
    ts: str = ""
    point: Optional[Dict[str, int]] = None
    element: Optional[Dict[str, Any]] = None
    window: Optional[Dict[str, Any]] = None
    focus: Optional[Dict[str, Any]] = None
    foreground: Optional[Dict[str, Any]] = None
    visible: Optional[List[Dict[str, Any]]] = None
    redacted: bool = False
    updated: bool = False


@dataclass
class _Pending:
    x: int
    y: int
    button: str
    t: float
    ts: str


class Recorder:
    def __init__(
        self, index: DiscoveryIndex, focus: Optional[FocusProvider] = None,
    ) -> None:
        self._index = index
        self._focus = focus
        self._pending: Optional[_Pending] = None
        self._last_click: Optional[tuple] = None
        self._last_title: Optional[str] = None
        self._index_stale = False
        self._records: List[Record] = []

    # -- events -------------------------------------------------------------

    def on_mouse_down(
        self, x: int, y: int, button: str = "left",
        t: Optional[float] = None, ts: str = "",
    ) -> None:
        self._pending = _Pending(
            x=x, y=y, button=button,
            t=time.monotonic() if t is None else t,
            ts=ts or _now_iso(),
        )

    def on_mouse_up(
        self, x: int, y: int, button: str = "left",
        t: Optional[float] = None, ts: str = "",
        window: Optional[Dict[str, Any]] = None,
    ) -> Record:
        t = time.monotonic() if t is None else t
        pending = self._pending or _Pending(x, y, button, t, ts or _now_iso())
        self._pending = None

        if self._last_click is not None:
            record, first_t, first_x, first_y, first_button = self._last_click
            if (
                pending.button == first_button
                and 0.0 <= pending.t - first_t <= DOUBLE_CLICK_S
                and abs(pending.x - first_x) <= DOUBLE_CLICK_PX
                and abs(pending.y - first_y) <= DOUBLE_CLICK_PX
            ):
                record.args["double_click"] = True
                record.updated = True
                self._last_click = None
                return record

        record = self._resolve(pending, window)
        self._records.append(record)
        self._last_click = (
            (record, pending.t, pending.x, pending.y, pending.button)
            if record.tool == "click_element"
            else None
        )
        return record

    def on_key(
        self, name: str, mods: frozenset = frozenset(), ts: str = ""
    ) -> Optional[Record]:
        from .win32_input import _MODIFIER_NAMES, _sendkeys

        if name in _MODIFIER_NAMES:
            return None
        key = _sendkeys(name, frozenset(mods))
        focus = self._focused()
        redacted = bool(focus and focus.get("is_password")) and key_text(key) is not None
        record = Record(
            tool="press_key",
            args={"key": "" if redacted else key},
            note="redacted: typed into a password field" if redacted else "",
            ts=ts or _now_iso(),
            focus=focus,
            redacted=redacted,
        )
        self._records.append(record)
        return record

    def on_scroll(
        self, x: int, y: int, delta: int, horizontal: bool = False,
        ts: str = "",
    ) -> Record:
        if horizontal:
            direction = "right" if delta > 0 else "left"
        else:
            direction = "up" if delta > 0 else "down"

        element = self._element_at(x, y)
        if element is None:
            record = Record(
                tool="scroll_element",
                args={},
                note="no interactable element under cursor",
                ts=ts or _now_iso(),
                point={"x": x, "y": y},
            )
        else:
            candidates = candidate_selectors(element.fingerprint)
            args = {"direction": direction, "amount": "small"}
            if candidates:
                args["selector"] = candidates[0]
                args["selectors"] = candidates
            record = Record(
                tool="scroll_element",
                args=args,
                ts=ts or _now_iso(),
                point={"x": x, "y": y},
                element=element.fingerprint.to_dict(),
            )
        self._records.append(record)
        self._index_stale = True
        return record

    # -- records ------------------------------------------------------------

    def _focused(self) -> Optional[Dict[str, Any]]:
        if self._focus is None:
            return None
        try:
            return self._focus()
        except Exception:  # noqa: BLE001 - UIA can fail on any call
            return None

    def _element_at(self, x: int, y: int):
        element = self._index.find_at(x, y)
        if element is None:
            self._index.maybe_refresh()
            element = self._index.find_at(x, y)
        return element

    def _window_context(
        self, window: Optional[Dict[str, Any]]
    ) -> Optional[List[Dict[str, Any]]]:
        """Named controls of the foreground window, once per window change."""
        title = (window or {}).get("title") or ""
        if not title or title == self._last_title:
            return None
        self._last_title = title
        if not self._index.has_window(title):
            self._index.maybe_refresh()
        return self._index.visible(title) or None

    def _foreground_alternative(
        self, pending: _Pending, element, window: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """The foreground window's element under the cursor, when the hit is not."""
        pid = (window or {}).get("pid") or 0
        if element is None or not pid or not element.fingerprint.pid:
            return None
        if element.fingerprint.pid == pid:
            return None
        alternative = self._index.find_at(pending.x, pending.y, pid=pid)
        if alternative is None:
            return None
        selectors = candidate_selectors(alternative.fingerprint)
        if not selectors:
            return None
        return {"element": alternative.fingerprint.to_dict(), "selectors": selectors}

    def _resolve(
        self, pending: _Pending, window: Optional[Dict[str, Any]]
    ) -> Record:
        if self._index_stale:
            # Scrolling moves items without changing any rect the index already
            # holds, so a hit on the old snapshot is the container, not the item.
            self._index.refresh()
            self._index_stale = False
        visible = self._window_context(window)
        element = self._element_at(pending.x, pending.y)
        candidates = candidate_selectors(element.fingerprint) if element else []
        base = dict(
            ts=pending.ts or _now_iso(),
            point={"x": pending.x, "y": pending.y},
            element=element.fingerprint.to_dict() if element else None,
            window=window,
            focus=self._focused(),
            foreground=self._foreground_alternative(pending, element, window),
            visible=visible,
        )

        if pending.button != "left":
            args: Dict[str, Any] = {"button": pending.button}
            if candidates:
                args["selector"] = candidates[0]
            return Record(
                tool="mouse_click",
                args=args,
                note="mouse_click clicks at the cursor; selector is metadata",
                **base,
            )

        args = {"double_click": False}
        if candidates:
            args["selector"] = candidates[0]
            args["selectors"] = candidates
        return Record(
            tool="click_element",
            args=args,
            note="" if candidates else "no interactable element under cursor",
            **base,
        )

    @property
    def records(self) -> List[Record]:
        return self._records

    def flush(self) -> List[Record]:
        out, self._records = self._records, []
        return out


__all__ = ["Record", "Recorder"]
