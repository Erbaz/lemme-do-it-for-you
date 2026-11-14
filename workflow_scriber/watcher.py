"""Watch the human, write down the tool calls the GUI agent would have made.

Phase 0 runtime. The hook callbacks only enqueue ``(t, x, y, ...)``; all UIA
work happens on one worker thread. Foreground capture happens in the callback,
because by the time the worker runs the window may already have changed.

Run:

    python -m workflow_scriber watch
"""

from __future__ import annotations

import ctypes
import json
import queue
import signal
import threading
import time
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pythoncom
import win32gui
import win32process

from . import __version__
from .discovery import DEFAULT_MAX_DEPTH, DiscoveryIndex
from .recorder import Record, Recorder
from .win32_input import (
    HC_ACTION,
    LLKHF_INJECTED,
    LLMHF_INJECTED,
    PM_REMOVE,
    WH_KEYBOARD_LL,
    WH_MOUSE_LL,
    WM_KEYDOWN,
    WM_LBUTTONDOWN,
    WM_LBUTTONUP,
    WM_MBUTTONDOWN,
    WM_MBUTTONUP,
    WM_MOUSEHWHEEL,
    WM_MOUSEWHEEL,
    WM_RBUTTONDOWN,
    WM_RBUTTONUP,
    WM_SYSKEYDOWN,
    _HOOKPROC,
    _KBDLLHOOKSTRUCT,
    _MSLLHOOKSTRUCT,
    _base_name,
    _current_mods,
    _kernel32,
    _user32,
)

_PROCESS_NAMES: Dict[int, str] = {}


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _wheel_delta(mouse_data: int) -> int:
    delta = (mouse_data >> 16) & 0xFFFF
    return delta - 0x10000 if delta >= 0x8000 else delta


def _foreground() -> Dict[str, Any]:
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return {}
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    return {
        "hwnd": int(hwnd),
        "title": win32gui.GetWindowText(hwnd),
        "class": win32gui.GetClassName(hwnd),
        "pid": int(pid),
    }


def _with_process(window: Dict[str, Any]) -> Dict[str, Any]:
    if not window or "pid" not in window:
        return window
    pid = window["pid"]
    name = _PROCESS_NAMES.get(pid)
    if name is None:
        try:
            import psutil

            name = psutil.Process(pid).name()
        except Exception:
            name = ""
        _PROCESS_NAMES[pid] = name
    return {**window, "process": name}


def _worker(
    q: "queue.Queue", recorder: Recorder, quiet: bool, reporter=None
) -> None:
    pythoncom.CoInitialize()
    while True:
        event = q.get()
        if event is None:
            break

        record: Optional[Record] = None
        try:
            kind = event[0]
            if kind == "mouse_down":
                _, x, y, button, t, ts, _fg = event
                recorder.on_mouse_down(x, y, button, t, ts)
                if reporter is not None:
                    reporter.note_mouse_down(x, y, t)
            elif kind == "winevent":
                _, ev, hwnd, id_object, id_child, t, ms_time = event
                if reporter is not None:
                    reporter.handle(ev, hwnd, id_object, id_child, t, ms_time)
            elif kind == "mouse_up":
                _, x, y, button, t, ts, fg = event
                record = recorder.on_mouse_up(
                    x, y, button, t, ts, _with_process(fg)
                )
            elif kind == "scroll":
                _, x, y, delta, horizontal, ts = event
                record = recorder.on_scroll(x, y, delta, horizontal, ts)
            elif kind == "key":
                _, name, mods, ts = event
                record = recorder.on_key(name, mods, ts)
        except Exception as exc:
            if not quiet:
                print(f"  ! worker error: {exc}", flush=True)
            continue

        if record is not None and not quiet:
            _print_record(record, len(recorder.records))


def _print_record(record: Record, n: int) -> None:
    if record.updated:
        print(
            f"[{n:>3}]   ^ upgraded to double_click  "
            f"{record.args.get('selector', '')}",
            flush=True,
        )
        return

    if record.tool == "click_element":
        detail = record.args.get("selector", "<unresolved>")
        if record.args.get("double_click"):
            detail += "  (double)"
    elif record.tool == "mouse_click":
        detail = f"button={record.args.get('button')}"
        selector = record.args.get("selector")
        if selector:
            detail += f"  target={selector}"
    elif record.tool == "press_key":
        detail = record.args.get("key", "")
    else:
        detail = record.args.get("selector", record.args.get("direction", ""))
    print(
        f"[{n:>3}] {record.tool:<14} {detail}"
        + (f"  {record.note}" if record.note else ""),
        flush=True,
    )


def _write_session(
    records: list, out: Path, session_id: str, started: str
) -> None:
    actions = []
    for n, record in enumerate(records, start=1):
        item: Dict[str, Any] = {
            "n": n,
            "ts": record.ts,
            "tool": record.tool,
            "args": record.args,
        }
        for key, value in (
            ("note", record.note),
            ("point", record.point),
            ("element", record.element),
            ("window", record.window),
        ):
            if value:
                item[key] = value
        actions.append(item)

    session = {
        "session": {
            "id": session_id,
            "started": started,
            "scriber": __version__,
            "note": "each action is the (tool, args) pair that reproduces it",
        },
        "actions": actions,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(session, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def watch(
    out: Path, max_depth: int = DEFAULT_MAX_DEPTH, quiet: bool = False,
    events: bool = False,
) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)

    index = DiscoveryIndex(max_depth=max_depth)
    count = index.build()
    recorder = Recorder(index)

    started = _iso()
    session_id = "s_" + datetime.now().strftime("%Y%m%d_%H%M%S")

    if not quiet:
        print(
            f"Indexed {count} interactable elements in "
            f"{index.stats.elapsed_ms:.0f} ms (depth {max_depth})",
            flush=True,
        )
        print("Watching. Do your thing; Ctrl+C to stop.", flush=True)
        print(f"Writing {out}", flush=True)
        print("", flush=True)

    q: "queue.Queue" = queue.Queue()
    reporter = None
    if events:
        from .events import EventReporter

        reporter = EventReporter()
    worker = threading.Thread(
        target=_worker, args=(q, recorder, quiet, reporter), daemon=True
    )
    worker.start()

    stop = threading.Event()

    def _request_stop(signum, frame):
        stop.set()

    signal.signal(signal.SIGINT, _request_stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _request_stop)

    def _mouse_proc(n_code, w_param, l_param):
        if n_code == HC_ACTION:
            info = ctypes.cast(l_param, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
            if info.flags & LLMHF_INJECTED:
                return _user32.CallNextHookEx(None, n_code, w_param, l_param)

            x, y = info.pt.x, info.pt.y
            if w_param in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN):
                button = {
                    WM_LBUTTONDOWN: "left",
                    WM_RBUTTONDOWN: "right",
                    WM_MBUTTONDOWN: "middle",
                }[w_param]
                q.put(("mouse_down", x, y, button, time.monotonic(), _iso(), _foreground()))
            elif w_param in (WM_LBUTTONUP, WM_RBUTTONUP, WM_MBUTTONUP):
                button = {
                    WM_LBUTTONUP: "left",
                    WM_RBUTTONUP: "right",
                    WM_MBUTTONUP: "middle",
                }[w_param]
                q.put(("mouse_up", x, y, button, time.monotonic(), _iso(), _foreground()))
            elif w_param == WM_MOUSEWHEEL:
                q.put(("scroll", x, y, _wheel_delta(info.mouseData), False, _iso()))
            elif w_param == WM_MOUSEHWHEEL:
                q.put(("scroll", x, y, _wheel_delta(info.mouseData), True, _iso()))
        return _user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _key_proc(n_code, w_param, l_param):
        if n_code == HC_ACTION:
            info = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            if info.flags & LLKHF_INJECTED:
                return _user32.CallNextHookEx(None, n_code, w_param, l_param)
            if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                q.put(("key", _base_name(info.vkCode), _current_mods(), _iso()))
        return _user32.CallNextHookEx(None, n_code, w_param, l_param)

    mouse_proc = _HOOKPROC(_mouse_proc)
    key_proc = _HOOKPROC(_key_proc)
    module = _kernel32.GetModuleHandleW(None)
    mouse_hook = _user32.SetWindowsHookExW(WH_MOUSE_LL, mouse_proc, module, 0)
    if not mouse_hook:
        raise OSError(f"SetWindowsHookExW(mouse) failed: {ctypes.get_last_error()}")
    key_hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, key_proc, module, 0)
    if not key_hook:
        _user32.UnhookWindowsHookEx(mouse_hook)
        raise OSError(f"SetWindowsHookExW(keyboard) failed: {ctypes.get_last_error()}")

    event_hooks: list = []
    event_proc = None  # keep the callback alive for the hooks' lifetime
    if events:
        from .events import install

        event_hooks, event_proc = install(q)
        if not quiet:
            print(
                f"Event probe on: {len(event_hooks)} WinEvent hooks "
                "(foreground/focus/invoke/selection/menu popup)",
                flush=True,
            )

    msg = wintypes.MSG()
    try:
        while not stop.is_set():
            if _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                _user32.TranslateMessage(ctypes.byref(msg))
                _user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.005)
    except KeyboardInterrupt:
        pass
    finally:
        if event_hooks:
            from .events import uninstall

            uninstall(event_hooks)
        _user32.UnhookWindowsHookEx(key_hook)
        _user32.UnhookWindowsHookEx(mouse_hook)
        q.put(None)
        worker.join(timeout=30.0)
        records = recorder.flush()
        _write_session(records, out, session_id, started)
        print("", flush=True)
        print(f"Done. {len(records)} actions written to {out}", flush=True)
        if reporter is not None:
            log = out.with_name(out.stem + ".events.txt")
            log.write_text(
                "\n".join(reporter.lines) + ("\n" if reporter.lines else ""),
                encoding="utf-8",
            )
            print(f"Event log: {log}", flush=True)
    return 0


__all__ = ["Recorder", "watch"]
