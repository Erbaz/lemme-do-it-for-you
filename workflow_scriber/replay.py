"""Replay a recorded flow through the real gui_agent tools.

    python -m workflow_scriber.replay myflow.json

Each action carries the selector candidates found when it was recorded
(``args.selectors``); older files derive them from the recorded ``element``.
The first candidate the tool accepts is used, then the rest are dropped. A
tool that takes no selector is called once. Relative file names resolve inside
``recorded_flows/``. Stops at the first action where every candidate fails.

The recording is never modified. After the whole flow succeeds, the pruned
version is written next to it as ``<name>.replayed.json``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import List, Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pythoncom

from gui_agent.windows.tools.uia_tools.click_element import click_element
from gui_agent.windows.tools.uia_tools.mouse_click import mouse_click
from gui_agent.windows.tools.uia_tools.press_key import press_key
from gui_agent.windows.tools.uia_tools.scroll_element import scroll_element

from workflow_scriber import RECORDED_FLOWS_DIR
from workflow_scriber.fingerprint import Fingerprint, candidate_selectors

TOOLS = {
    "click_element": click_element,
    "mouse_click": mouse_click,
    "press_key": press_key,
    "scroll_element": scroll_element,
}

SUCCESS_PREFIX = {
    "click_element": ("Clicked element:", "Double-clicked element:"),
    "mouse_click": ("Clicked ",),
    "press_key": ("Pressed key:",),
    "scroll_element": ("Scrolled ",),
}

SELECTOR_TOOLS = {"click_element", "scroll_element"}

DELAY_S = 0.3


def _flow_path(name: str) -> Path:
    path = Path(name)
    if path.is_absolute() or path.parent != Path("."):
        return path
    candidate = RECORDED_FLOWS_DIR / path
    if candidate.exists() or not path.exists():
        return candidate
    return path


def _candidates_from_element(element: Optional[dict]) -> List[str]:
    if not element:
        return []
    return candidate_selectors(Fingerprint(
        control_type=element.get("control_type", ""),
        name=element.get("name", ""),
        automation_id=element.get("automation_id", ""),
        class_name=element.get("class_name", ""),
        rect=(0, 0, 0, 0),
        pid=0,
        is_password=False,
    ))


def _selectors(action: dict, derive: bool) -> List[str]:
    args = action.get("args", {})
    recorded = args.get("selectors")
    if recorded:
        return list(recorded)
    primary = args.get("selector")
    if not derive:
        return [primary] if primary else []
    candidates = _candidates_from_element(action.get("element"))
    if primary and primary not in candidates:
        candidates.insert(0, primary)
    if candidates:
        return candidates
    return [primary] if primary else []


def _call(tool, args: dict, selector: Optional[str]) -> dict:
    call = {key: value for key, value in args.items() if key in tool.args}
    if selector is not None:
        call["selector"] = selector
    return call


def _succeeded(name: str, result: str) -> bool:
    first = result.strip().splitlines()[0] if result.strip() else ""
    prefixes = SUCCESS_PREFIX.get(name)
    if prefixes:
        return first.startswith(prefixes)
    return not first.lower().startswith(("error", "failed"))


def _replay_path(flow: Path) -> Path:
    if flow.stem.endswith(".replayed"):
        return flow
    return flow.with_name(f"{flow.stem}.replayed{flow.suffix}")


def _write_replay(flow: Path, payload: dict, chosen: dict) -> None:
    for index, selector in chosen.items():
        args = payload["actions"][index].setdefault("args", {})
        args["selector"] = selector
        args.pop("selectors", None)
    payload.setdefault("session", {})["pruned"] = True

    out = _replay_path(flow)
    out.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Replay flow written to {out}")


def replay(flow: Path) -> int:
    payload = json.loads(flow.read_text(encoding="utf-8"))
    actions = payload.get("actions", [])
    pruned = bool(payload.get("session", {}).get("pruned"))
    pythoncom.CoInitialize()

    print(f"Replaying {len(actions)} actions from {flow}")
    chosen = {}
    for index, action in enumerate(actions):
        n = action.get("n")
        name = action.get("tool", "")
        args = action.get("args", {})
        tool = TOOLS.get(name)
        if tool is None:
            print(f"[{n}] FAIL unknown tool: {name}")
            return 1

        if name in SELECTOR_TOOLS:
            attempts = _selectors(action, derive=not pruned)
            if not attempts:
                print(f"[{n}] FAIL {name} has no selector")
                return 1
        else:
            attempts = [None]

        ok = False
        for attempt, selector in enumerate(attempts, start=1):
            call = _call(tool, args, selector)
            result = tool.invoke(call)
            first = result.strip().splitlines()[0] if result.strip() else "(no output)"
            if _succeeded(name, result):
                note = ""
                if len(attempts) > 1:
                    note = f"  (candidate {attempt}/{len(attempts)}: {selector})"
                print(
                    f"[{n}] {name}({json.dumps(call, ensure_ascii=False)})  "
                    f"ok: {first}{note}"
                )
                if name in SELECTOR_TOOLS:
                    chosen[index] = selector
                ok = True
                break
            print(
                f"[{n}] {name} candidate {attempt}/{len(attempts)} "
                f"{selector!r} FAIL: {first}"
            )

        if not ok:
            print(
                f"Stopped at action {n}/{len(actions)}: {name} failed "
                f"all {len(attempts)} candidate(s)."
            )
            return 1
        time.sleep(DELAY_S)

    print(f"Done. {len(actions)}/{len(actions)} tools called, all succeeded.")
    _write_replay(flow, payload, chosen)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python -m workflow_scriber.replay <flow.json>")
        return 2
    flow = _flow_path(argv[0])
    if not flow.exists():
        print(f"Flow not found: {flow}")
        return 2
    return replay(flow)


if __name__ == "__main__":
    sys.exit(main())
