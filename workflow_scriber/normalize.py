"""Deterministic preprocessing of a raw flow for candidate extraction.

A pure function of the recorded JSON: no LLM, no UIA. Every later stage refers
to actions by their recorded ``n``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

REPLAYABLE_TOOLS = frozenset({
    "click_element", "mouse_click", "press_key", "scroll_element",
})
SELECTOR_TOOLS = frozenset({"click_element", "scroll_element"})

#: SendKeys syntax characters; a bare one is not literal text.
_SENDKEYS_SYNTAX = frozenset("+^%~(){}[]")

_IDENTITY_KEYS = ("control_type", "name", "automation_id", "class_name")

MAX_NAME_LEN = 120


def key_text(key: str) -> Optional[str]:
    """The literal text a recorded ``press_key`` types, or None for a command key."""
    if key == "{SPACE}":
        return " "
    if len(key) == 1 and key not in _SENDKEYS_SYNTAX:
        return key
    if len(key) == 2 and key[0] == "+" and key[1].isalpha():
        return key[1].upper()
    return None


def _identity(element: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    if not element:
        return None
    out = {
        key: str(element[key])[:MAX_NAME_LEN]
        for key in _IDENTITY_KEYS
        if element.get(key)
    }
    return out or None


def _parse_ts(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _has_selector(args: Dict[str, Any]) -> bool:
    return bool(args.get("selector") or args.get("selectors"))


def _normalize_action(index: int, action: Dict[str, Any]) -> Dict[str, Any]:
    tool = action.get("tool", "")
    args = action.get("args") or {}
    element = action.get("element") or {}
    window = action.get("window") or {}
    foreground = (action.get("foreground") or {}).get("element")
    redacted = bool(action.get("redacted"))

    item: Dict[str, Any] = {"n": action.get("n", index + 1), "tool": tool}
    if tool == "press_key":
        item["key"] = args.get("key", "")
        text = None if redacted else key_text(item["key"])
        if text is not None:
            item["text"] = text
    if tool == "scroll_element":
        item["direction"] = args.get("direction", "")
    if tool == "mouse_click":
        item["button"] = args.get("button", "")
    item["double_click"] = bool(args.get("double_click"))

    item["target"] = _identity(element)
    item["window"] = (
        {"process": window.get("process", ""), "title": window.get("title", "")}
        if window else None
    )
    element_pid = element.get("pid") or 0
    window_pid = window.get("pid") or 0
    item["identity_conflict"] = bool(
        element_pid and window_pid and element_pid != window_pid
    )
    item["foreground_target"] = _identity(foreground)
    item["focus"] = _identity(action.get("focus"))
    item["visible"] = action.get("visible") or []
    item["redacted"] = redacted
    item["replayable"] = (
        tool in REPLAYABLE_TOOLS
        and not redacted
        and (tool not in SELECTOR_TOOLS or _has_selector(args))
    )
    return item


def same_control(a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]) -> bool:
    """Same focused control, ignoring Name: an edit's Name is its current text."""
    if a is None or b is None:
        return a is b
    return all(a.get(k) == b.get(k) for k in ("control_type", "automation_id", "class_name"))


def typing_spans(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Runs of consecutive typed characters that went to the same focus."""
    spans: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for action in actions:
        text = action.get("text")
        if text is None:
            current = None
            continue
        focus = action.get("focus")
        if current is not None and same_control(current["focus"], focus):
            current["actions"].append(action["n"])
            current["text"] += text
        else:
            current = {"actions": [action["n"]], "text": text, "focus": focus}
            spans.append(current)
    return spans


def normalize(flow: Dict[str, Any]) -> Dict[str, Any]:
    raw = flow.get("actions") or []
    actions = [_normalize_action(i, a) for i, a in enumerate(raw)]

    prev_ts: Optional[datetime] = None
    prev_title: Optional[str] = None
    for raw_action, action in zip(raw, actions):
        ts = _parse_ts(raw_action.get("ts", ""))
        action["gap_s"] = (
            round((ts - prev_ts).total_seconds(), 1)
            if ts is not None and prev_ts is not None else 0.0
        )
        if ts is not None:
            prev_ts = ts
        window = action["window"]
        action["window_changed"] = bool(window) and window["title"] != prev_title
        if window:
            prev_title = window["title"]

    for action, following in zip(actions, actions[1:] + [None]):
        after = following["focus"] if following else None
        action["focus_after"] = None if same_control(after, action["focus"]) else after

    return {
        "session": flow.get("session") or {},
        "actions": actions,
        "typing_spans": typing_spans(actions),
    }


__all__ = [
    "REPLAYABLE_TOOLS", "SELECTOR_TOOLS", "key_text", "normalize", "typing_spans",
]
