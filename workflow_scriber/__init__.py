"""Workflow Scriber — record human desktop actions as gui_agent tool calls.

Phase 0 complete: a click point becomes the selector of the element under the
cursor, and the record is the exact ``(tool, args)`` pair that reproduces the
action. A record is validated by replaying it, not at record time:

    python -m workflow_scriber watch
    python -m workflow_scriber.replay recorded_flows/<flow>.json

Phase 1: one LLM call turns a recording into action annotations and scribbles,
small atomic workflows. Each scribble is a subset of the recording in the same
flow format and states the starting state it needs, so it replays on its own:

    python -m workflow_scriber extract [<flow>.json]   # default: newest recording
    python -m workflow_scriber.replay workflow_scriber/library/<flow>/workflows/<id>.json

Module layout:

    discovery  — snapshot of interactable elements (selector, rect, identity)
    fingerprint — element identity record
    recorder   — hook events -> tool calls (single state machine)
    replay     — run a recorded flow through the real gui_agent tools
    win32_input — hook structs, key tables
    watcher    — watch() entry point, hooks, message loop, session writer
    events     — opt-in WinEvent probe (``watch --events``)
    normalize  — deterministic per-action facts and typing spans
    scribbles  — context card, validation, materialization
    prompt     — the one-shot extraction template
    llm        — chat model configured like gui_agent
    extract    — extraction pipeline and library storage
"""

from pathlib import Path

__version__ = "0.7.0"

RECORDED_FLOWS_DIR = Path(__file__).resolve().parent / "recorded_flows"

__all__ = [
    "RECORDED_FLOWS_DIR",
    "discovery",
    "fingerprint",
    "recorder",
    "replay",
    "win32_input",
    "watcher",
    "normalize",
    "scribbles",
    "prompt",
    "llm",
    "extract",
]
