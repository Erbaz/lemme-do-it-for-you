"""Opt-in WinEvent probe.

``watch --events`` installs out-of-context WinEvent hooks for foreground,
focus, invoke, selection and menu-popup events, maps each event to the UIA
element it identifies, and logs one line per event. No hooks are installed
without the flag, and recorded actions are unchanged; this only measures what
the target apps emit.

The ``uiautomation`` package wraps patterns but not UIA events, so the raw
comtypes client is used for ``AccessibleObjectFromEvent`` ->
``ElementFromIAccessible``.

Revert: run without ``--events`` (nothing new is installed). To remove the
probe, delete this file, the ``--events`` argument, and the two guarded blocks
in ``watcher.py``.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Any, Dict, List, Optional, Tuple

import uiautomation as auto
import win32gui
import win32process
from comtypes.automation import VARIANT

from .win32_input import _user32

WINEVENT_OUTOFCONTEXT = 0x0000

EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_SYSTEM_MENUPOPUPSTART = 0x0006
EVENT_OBJECT_FOCUS = 0x8005
EVENT_OBJECT_SELECTION = 0x8006
EVENT_OBJECT_INVOKED = 0x8013

_NAMES = {
    EVENT_SYSTEM_FOREGROUND: "FOREGROUND",
    EVENT_SYSTEM_MENUPOPUPSTART: "MENUPOPUPSTART",
    EVENT_OBJECT_FOCUS: "FOCUS",
    EVENT_OBJECT_SELECTION: "SELECTION",
    EVENT_OBJECT_INVOKED: "INVOKED",
}

_WANTED = (
    EVENT_SYSTEM_FOREGROUND,
    EVENT_SYSTEM_MENUPOPUPSTART,
    EVENT_OBJECT_FOCUS,
    EVENT_OBJECT_SELECTION,
    EVENT_OBJECT_INVOKED,
)

_ELEMENT_EVENTS = frozenset({
    EVENT_OBJECT_FOCUS, EVENT_OBJECT_SELECTION, EVENT_OBJECT_INVOKED,
})

_WINEVENTPROC = ctypes.WINFUNCTYPE(
    None,
    wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
    wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD,
)

_user32.SetWinEventHook.argtypes = (
    wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE,
    _WINEVENTPROC, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
)
_user32.SetWinEventHook.restype = wintypes.HANDLE
_user32.UnhookWinEvent.argtypes = (wintypes.HANDLE,)
_user32.UnhookWinEvent.restype = wintypes.BOOL

_oleacc = ctypes.WinDLL("oleacc", use_last_error=True)
_oleacc.AccessibleObjectFromEvent.restype = ctypes.c_long
_acc_types_ready = False
_PROCESS_NAMES: Dict[int, str] = {}


def install(q: Any) -> Tuple[List[int], Any]:
    """Install the probe hooks. Must run on the thread that pumps messages.

    Returns ``(hooks, callback)``; keep the callback alive until uninstall.
    """

    def _on_event(hook, event, hwnd, id_object, id_child, thread_id, ms_time):
        q.put((
            "winevent", int(event), int(hwnd or 0), int(id_object),
            int(id_child), time.monotonic(), int(ms_time),
        ))

    proc = _WINEVENTPROC(_on_event)
    hooks: List[int] = []
    for event in _WANTED:
        hook = _user32.SetWinEventHook(
            event, event, None, proc, 0, 0, WINEVENT_OUTOFCONTEXT,
        )
        if hook:
            hooks.append(hook)
    return hooks, proc


def uninstall(hooks: List[int]) -> None:
    for hook in hooks:
        _user32.UnhookWinEvent(hook)


def _uiautomation():
    from uiautomation.uiautomation import _AutomationClient

    return _AutomationClient.instance().IUIAutomation


def _uia_module():
    from uiautomation.uiautomation import _AutomationClient

    return _AutomationClient.instance().UIAutomationCore


def _ensure_acc_argtypes() -> None:
    global _acc_types_ready
    if _acc_types_ready:
        return
    module = _uia_module()
    _oleacc.AccessibleObjectFromEvent.argtypes = (
        wintypes.HWND, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(module.IAccessible)),
        ctypes.POINTER(VARIANT),
    )
    _acc_types_ready = True


def _element_from_event(hwnd: int, id_object: int, id_child: int):
    """Map a WinEvent's (hwnd, idObject, idChild) to a UIA Control."""
    _ensure_acc_argtypes()
    module = _uia_module()
    acc = ctypes.POINTER(module.IAccessible)()
    child = VARIANT()
    hr = _oleacc.AccessibleObjectFromEvent(
        hwnd, id_object, id_child, ctypes.byref(acc), ctypes.byref(child),
    )
    if hr < 0 or not acc:
        return None, hr

    child_id = id_child
    try:
        if child.vt == 3:  # VT_I4
            child_id = int(child.value)
    except Exception:
        pass

    try:
        element = _uiautomation().ElementFromIAccessible(acc, child_id)
        if element is None:
            return None, hr
        return auto.Control.CreateControlFromElement(element), hr
    except Exception:
        return None, hr
    finally:
        try:
            acc.contents.Release()
        except Exception:
            pass


def _focused() -> Optional[Any]:
    try:
        return auto.GetFocusedControl()
    except Exception:
        return None


def _from_point(x: int, y: int) -> Optional[Any]:
    try:
        return auto.ControlFromPoint(x, y)
    except Exception:
        return None


def _from_handle(hwnd: int) -> Optional[Any]:
    try:
        element = _uiautomation().ElementFromHandle(hwnd)
        if element is None:
            return None
        return auto.Control.CreateControlFromElement(element)
    except Exception:
        return None


def _rect(ctrl: Any) -> Optional[Tuple[int, int, int, int]]:
    try:
        r = ctrl.BoundingRectangle
        return (int(r.left), int(r.top), int(r.right), int(r.bottom))
    except Exception:
        return None


def _describe(ctrl: Any) -> str:
    try:
        root = ""
        top = ctrl.GetTopLevelControl()
        if top is not None:
            try:
                root = (
                    f" root={top.ControlTypeName} name={top.Name!r} "
                    f"class={top.ClassName!r}"
                )
            except Exception:
                root = ""
        return (
            f"{ctrl.ControlTypeName} name={ctrl.Name!r} "
            f"id={ctrl.AutomationId!r} class={ctrl.ClassName!r} "
            f"pid={ctrl.ProcessId} rect={_rect(ctrl)}{root}"
        )
    except Exception as exc:
        return f"<element unavailable: {exc}>"


def _process_name(pid: int) -> str:
    if pid not in _PROCESS_NAMES:
        try:
            import psutil

            _PROCESS_NAMES[pid] = psutil.Process(pid).name()
        except Exception:
            _PROCESS_NAMES[pid] = ""
    return _PROCESS_NAMES[pid]


def _window(hwnd: int) -> str:
    if not hwnd:
        return "<no hwnd>"
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return (
            f"hwnd=0x{hwnd:X} pid={pid} {_process_name(pid)} "
            f"title={win32gui.GetWindowText(hwnd)!r} "
            f"class={win32gui.GetClassName(hwnd)!r}"
        )
    except Exception as exc:
        return f"hwnd=0x{hwnd:X} <window unavailable: {exc}>"


class EventReporter:
    """Turn queued WinEvents into one readable line each."""

    def __init__(self) -> None:
        self._last_down: Optional[Tuple[int, int, float]] = None
        self.lines: List[str] = []

    def note_mouse_down(self, x: int, y: int, t: float) -> None:
        self._last_down = (x, y, t)

    def _emit(self, line: str) -> None:
        self.lines.append(line)
        print(line, flush=True)

    def _dt(self, t: float) -> str:
        if self._last_down is None:
            return ""
        return f" dt={(t - self._last_down[2]) * 1000:+.0f}ms"

    def handle(
        self, event: int, hwnd: int, id_object: int, id_child: int,
        t: float, ms_time: int,
    ) -> None:
        name = _NAMES.get(event, f"0x{event:04X}")
        head = (
            f"[event {time.strftime('%H:%M:%S')}.{int(t % 1 * 1000):03d}] "
            f"{name:<14} idObject={id_object} idChild={id_child} "
            f"{_window(hwnd)}{self._dt(t)}"
        )

        ctrl: Optional[Any] = None
        note = ""
        if event in _ELEMENT_EVENTS:
            ctrl, hr = _element_from_event(hwnd, id_object, id_child)
            if ctrl is None:
                note = f" <event element unavailable hr=0x{hr & 0xFFFFFFFF:08X}>"
                if event == EVENT_OBJECT_FOCUS:
                    ctrl = _focused()
                    if ctrl is not None:
                        note = " <focus fallback>"
                elif self._last_down is not None:
                    x, y, _ = self._last_down
                    ctrl = _from_point(x, y)
                    if ctrl is not None:
                        note = " <point fallback>"
        else:
            ctrl = _from_handle(hwnd)

        if ctrl is None:
            self._emit(head + note + "  <no element>")
            return

        inside = ""
        rect = _rect(ctrl)
        if rect is not None and self._last_down is not None:
            x, y, _ = self._last_down
            hit = rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]
            inside = f" contains_click={'yes' if hit else 'no'}"

        self._emit(head + note + inside + "  " + _describe(ctrl))


__all__ = ["EventReporter", "install", "uninstall"]
