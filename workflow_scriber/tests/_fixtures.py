"""A small recorded flow covering every normalization case."""

from __future__ import annotations

import copy
from typing import Any, Dict, List

EXPLORER = {"hwnd": 1, "title": "Documents - File Explorer", "class": "CabinetWClass",
            "pid": 100, "process": "explorer.exe"}
EDIT_FOCUS = {"control_type": "EditControl", "name": "Name", "automation_id": "",
              "class_name": "Edit", "pid": 100, "is_password": False}


def _element(name: str, control_type: str = "ButtonControl", pid: int = 100) -> Dict[str, Any]:
    return {"control_type": control_type, "name": name, "automation_id": "",
            "class_name": "", "rect": [0, 0, 10, 10], "pid": pid, "is_password": False}


def _click(n: int, name: str, pid: int = 100, **extra) -> Dict[str, Any]:
    action = {
        "n": n, "ts": f"2026-11-15T10:00:{n:02d}+00:00", "tool": "click_element",
        "args": {"double_click": False, "selector": f"name:{name}",
                 "selectors": [f"name:{name}"]},
        "point": {"x": 5, "y": 5}, "element": _element(name, pid=pid), "window": EXPLORER,
    }
    action.update(extra)
    return action


def _key(n: int, key: str, focus=EDIT_FOCUS, **extra) -> Dict[str, Any]:
    action = {"n": n, "ts": f"2026-11-15T10:00:{n:02d}+00:00", "tool": "press_key",
              "args": {"key": key}, "focus": focus}
    action.update(extra)
    return action


def flow() -> Dict[str, Any]:
    """1 open, 2 conflict with foreground alt, 3 no selector, 4-7 "Test",
    8 ENTER, 9 Close, 10 redacted key."""
    actions: List[Dict[str, Any]] = [
        _click(1, "File Explorer", visible=[
            {"control_type": "ButtonControl", "name": "New", "selector": "name:New"},
        ]),
        _click(2, "Separator", pid=200, foreground={
            "element": _element("New"), "selectors": ["name:New", "class:Button"],
        }),
        {"n": 3, "ts": "2026-11-15T10:00:03+00:00", "tool": "click_element",
         "args": {"double_click": False}, "note": "no interactable element under cursor",
         "point": {"x": 1, "y": 1}, "window": EXPLORER},
        _key(4, "+t"),
        _key(5, "e"),
        _key(6, "s"),
        _key(7, "t"),
        _key(8, "{ENTER}"),
        _click(9, "Close"),
        _key(10, "", redacted=True,
             focus=dict(EDIT_FOCUS, name="Password", is_password=True)),
    ]
    return {"session": {"id": "s_test", "started": "2026-11-15T10:00:00+00:00",
                        "scriber": "0.6.0"},
            "actions": actions}


VALID_RESPONSE: Dict[str, Any] = {
    "recording": {"title": "Create a folder", "summary": "Created a folder named Test."},
    "annotations": [
        {"action": n, "observed": f"action {n}", "purpose": ""}
        for n in range(1, 11)
    ],
    "scribbles": [
        {
            "id": "explorer_create_folder",
            "title": "Create a folder in File Explorer",
            "description": "Opens File Explorer and creates a named folder.",
            "actions": [1, 2, 4, 5, 6, 7, 8],
            "steps": [
                {"intent": "Open File Explorer", "actions": [1]},
                {"intent": "Create a new folder", "actions": [2]},
                {"intent": "Name it", "actions": [4, 5, 6, 7, 8]},
            ],
        },
        {
            "id": "open_file_explorer",
            "title": "Open File Explorer",
            "description": "Opens File Explorer from the taskbar.",
            "actions": [1],
            "steps": [{"intent": "Open File Explorer", "actions": [1]}],
        },
    ],
}


def valid_response() -> Dict[str, Any]:
    return copy.deepcopy(VALID_RESPONSE)
