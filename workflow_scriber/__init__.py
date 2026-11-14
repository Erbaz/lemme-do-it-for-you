"""Workflow Scriber — record human desktop actions as gui_agent tool calls.

Phase 0 complete: a click point becomes the selector of the element under the
cursor, and the record is the exact ``(tool, args)`` pair that reproduces the
action. A record is validated by replaying it, not at record time:

    python -m workflow_scriber watch
    python -m workflow_scriber.replay recorded_flows/<flow>.json

Module layout:

    discovery  — snapshot of interactable elements (selector, rect, identity)
    fingerprint — element identity record
    recorder   — hook events -> tool calls (single state machine)
    replay     — run a recorded flow through the real gui_agent tools
    win32_input — hook structs, key tables
    watcher    — watch() entry point, hooks, message loop, session writer
    events     — opt-in WinEvent probe (``watch --events``)
"""

from pathlib import Path

__version__ = "0.5.0"

RECORDED_FLOWS_DIR = Path(__file__).resolve().parent / "recorded_flows"

__all__ = [
    "RECORDED_FLOWS_DIR",
    "discovery",
    "fingerprint",
    "recorder",
    "replay",
    "win32_input",
    "watcher",
]
