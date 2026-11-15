"""Scribbles: concise workflows inferred from one recording.

The LLM only chooses recorded action ids and writes descriptions. Everything
executable is copied from the recording here, so each scribble is a raw-flow
subset that ``workflow_scriber.replay`` can replay on its own.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional

from . import __version__
from .normalize import SELECTOR_TOOLS

SCHEMA_VERSION = 3
MAX_DESCRIPTION_LEN = 600

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


# --- context card ------------------------------------------------------------

def _compact_visible(visible: List[Dict[str, Any]]) -> List[str]:
    out = []
    for item in visible:
        control = str(item.get("control_type", "")).removesuffix("Control")
        out.append(f'{item.get("name", "")} [{control}]')
    return out


def context_card(normalized: Dict[str, Any]) -> Dict[str, Any]:
    """What the LLM sees: compact per-action facts, empty fields dropped."""
    actions = []
    for action in normalized["actions"]:
        item = {
            key: value for key, value in action.items()
            if key not in ("replayable", "visible")
            and value not in (None, False, "", [], {}, 0.0)
        }
        if action["visible"]:
            item["visible"] = _compact_visible(action["visible"])
        if not action["replayable"]:
            item["replayable"] = False
        actions.append(item)
    session = normalized["session"]
    return {
        "recording": {"id": session.get("id", ""), "started": session.get("started", "")},
        "actions": actions,
        "typing_spans": [
            {key: value for key, value in span.items() if value is not None}
            for span in normalized["typing_spans"]
        ],
    }


# --- validation --------------------------------------------------------------

def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _int_list(value: Any) -> Optional[List[int]]:
    if isinstance(value, list) and value and all(_is_int(v) for v in value):
        return value
    return None


def _validate_annotations(response: Dict[str, Any], by_n: Dict[int, Dict]) -> List[str]:
    annotations = response.get("annotations")
    if not isinstance(annotations, list):
        return ["annotations must be a list"]
    errors: List[str] = []
    seen = set()
    for i, ann in enumerate(annotations):
        where = f"annotations[{i}]"
        if not isinstance(ann, dict):
            errors.append(f"{where} must be an object")
            continue
        n = ann.get("action")
        if not _is_int(n) or n not in by_n:
            errors.append(f"{where}.action {n!r} is not a recorded action")
            continue
        if n in seen:
            errors.append(f"action {n} is annotated more than once")
        seen.add(n)
        if not _is_text(ann.get("observed")):
            errors.append(f"{where}.observed must be a non-empty string")
        if not isinstance(ann.get("purpose", ""), str):
            errors.append(f"{where}.purpose must be a string")
    missing = sorted(set(by_n) - seen)
    if missing:
        errors.append(f"actions not annotated: {missing}")
    return errors


def _validate_scribble(
    i: int, scribble: Any, by_n: Dict[int, Dict], position: Dict[int, int],
    ids: set, action_sets: Dict[tuple, str],
) -> List[str]:
    where = f"scribbles[{i}]"
    if not isinstance(scribble, dict):
        return [f"{where} must be an object"]
    errors: List[str] = []

    sid = scribble.get("id")
    if not isinstance(sid, str) or not _ID_RE.match(sid):
        errors.append(f"{where}.id must be snake_case (a-z, 0-9, _), at most 64 chars")
    elif sid in ids:
        errors.append(f"{where}.id {sid!r} is duplicated")
    else:
        ids.add(sid)
        where = f"scribble {sid!r}"

    if not _is_text(scribble.get("title")):
        errors.append(f"{where}.title must be a non-empty string")
    description = scribble.get("description")
    if not _is_text(description):
        errors.append(f"{where}.description must be a non-empty string")
    elif len(description) > MAX_DESCRIPTION_LEN:
        errors.append(f"{where}.description must be at most {MAX_DESCRIPTION_LEN} chars")

    actions = _int_list(scribble.get("actions"))
    if actions is None:
        errors.append(f"{where}.actions must be a non-empty list of action ids")
        return errors
    unknown = [n for n in actions if n not in by_n]
    if unknown:
        errors.append(f"{where}.actions has unknown action ids {unknown}")
        return errors
    if any(position[a] >= position[b] for a, b in zip(actions, actions[1:])):
        errors.append(f"{where}.actions must be in recording order without repeats")
    not_replayable = [n for n in actions if not by_n[n]["replayable"]]
    if not_replayable:
        errors.append(f"{where}.actions {not_replayable} are not replayable")
    other = action_sets.get(tuple(actions))
    if other is not None:
        errors.append(f"{where} has the same actions as scribble {other!r}")
    elif isinstance(sid, str):
        action_sets[tuple(actions)] = sid

    steps = scribble.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append(f"{where}.steps must be a non-empty list")
    else:
        covered: List[int] = []
        for j, step in enumerate(steps):
            if not isinstance(step, dict) or not _is_text(step.get("intent")):
                errors.append(f"{where}.steps[{j}] needs a non-empty intent")
                continue
            step_actions = _int_list(step.get("actions"))
            if step_actions is None:
                errors.append(f"{where}.steps[{j}].actions must be a non-empty list")
                continue
            covered.extend(step_actions)
        if covered != actions:
            errors.append(
                f"{where}.steps must split the scribble's actions into consecutive "
                f"groups, every action exactly once, in order"
            )

    return errors


def _indexes(normalized: Dict[str, Any]):
    by_n = {a["n"]: a for a in normalized["actions"]}
    position = {a["n"]: i for i, a in enumerate(normalized["actions"])}
    return by_n, position


def validate(response: Any, normalized: Dict[str, Any]) -> List[str]:
    """Every reason the response cannot be materialized. Empty means valid."""
    if not isinstance(response, dict):
        return ["the answer must be a JSON object"]
    by_n, position = _indexes(normalized)
    errors: List[str] = []

    recording = response.get("recording")
    if not (
        isinstance(recording, dict)
        and _is_text(recording.get("title"))
        and _is_text(recording.get("summary"))
    ):
        errors.append("recording.title and recording.summary must be non-empty strings")

    errors.extend(_validate_annotations(response, by_n))

    scribbles = response.get("scribbles")
    if not isinstance(scribbles, list) or not scribbles:
        errors.append("scribbles must be a non-empty list")
        return errors
    ids: set = set()
    action_sets: Dict[tuple, str] = {}
    for i, scribble in enumerate(scribbles):
        errors.extend(_validate_scribble(
            i, scribble, by_n, position, ids, action_sets,
        ))
    return errors


# --- materialization ---------------------------------------------------------

def describe_scribbles(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Validated scribbles, each pointing at the workflow file it materializes to."""
    out = []
    for scribble in response["scribbles"]:
        out.append({
            "id": scribble["id"],
            "title": scribble["title"],
            "description": scribble["description"],
            "actions": scribble["actions"],
            "steps": [
                {"intent": step["intent"], "actions": step["actions"]}
                for step in scribble["steps"]
            ],
            "workflow": f'workflows/{scribble["id"]}.json',
        })
    return out


def workflow_flow(
    scribble: Dict[str, Any], flow: Dict[str, Any], recording_id: str, source_flow: str,
) -> Dict[str, Any]:
    """The scribble as a raw-flow file: recorded actions copied, renumbered.

    On an identity conflict the foreground selectors go first so replay targets
    what the user saw; the recorded selectors stay as fallbacks.
    """
    raw_by_n = {a.get("n", i + 1): a for i, a in enumerate(flow.get("actions") or [])}
    actions = []
    for new_n, source_n in enumerate(scribble["actions"], start=1):
        action = copy.deepcopy(raw_by_n[source_n])
        action.pop("visible", None)
        action["n"] = new_n
        action["source_n"] = source_n
        foreground = (action.get("foreground") or {}).get("selectors") or []
        if foreground and action.get("tool") in SELECTOR_TOOLS:
            args = action.setdefault("args", {})
            recorded = args.get("selectors") or (
                [args["selector"]] if args.get("selector") else []
            )
            merged = list(dict.fromkeys(foreground + recorded))
            args["selectors"] = merged
            args["selector"] = merged[0]
        actions.append(action)

    source_session = flow.get("session") or {}
    session: Dict[str, Any] = {
        "id": f'{recording_id}/{scribble["id"]}',
        "started": source_session.get("started", ""),
        "scriber": __version__,
        "source_flow": source_flow,
        "scribble": scribble["id"],
        "note": "Scribble. Actions are copied from the source flow; "
                "source_n is the recorded action number.",
    }
    if source_session.get("pruned"):
        session["pruned"] = True
    return {"session": session, "actions": actions}


__all__ = [
    "SCHEMA_VERSION", "context_card", "validate", "describe_scribbles", "workflow_flow",
]
