"""One-shot extraction: recording -> annotations + scribbles.

normalize -> context card -> one LLM call -> validate (one repair) ->
materialize -> library/<recording_id>/. Scribbles only ever come from the LLM;
if it cannot produce a valid answer, extraction fails and nothing is written.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import __version__
from .scribbles import (
    SCHEMA_VERSION, context_card, describe_scribbles, validate, workflow_flow,
)
from .llm import Completer
from .normalize import normalize
from .prompt import PROMPT_VERSION, SYSTEM_PROMPT, render_repair, render_user

LIBRARY_DIR = Path(__file__).resolve().parent / "library"
MAX_ATTEMPTS = 2

_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


@dataclass
class Extraction:
    recording_id: str
    card: Dict[str, Any]
    bundle: Dict[str, Any]
    workflows: Dict[str, Dict[str, Any]]
    responses: List[str] = field(default_factory=list)


def recording_id(flow_path: Path) -> str:
    return flow_path.stem.removesuffix(".replayed")


def parse_response(text: str) -> Tuple[Optional[Any], Optional[str]]:
    """The JSON object in an LLM reply, tolerating code fences and stray prose."""
    stripped = _FENCE_RE.sub("", text.strip())
    try:
        return json.loads(stripped), None
    except json.JSONDecodeError:
        pass
    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(stripped[start:end + 1]), None
        except json.JSONDecodeError as exc:
            return None, f"the answer is not valid JSON: {exc}"
    return None, "the answer contains no JSON object"


def extract(
    flow: Dict[str, Any],
    rec_id: str,
    source_flow: str,
    complete: Completer,
    model: str = "",
) -> Extraction:
    normalized = normalize(flow)
    card = context_card(normalized)
    user = render_user(card)

    responses: List[str] = []
    errors: List[str] = []
    response: Optional[Dict[str, Any]] = None
    message = user
    for _ in range(MAX_ATTEMPTS):
        text = complete(SYSTEM_PROMPT, message)
        responses.append(text)
        parsed, parse_error = parse_response(text)
        errors = [parse_error] if parse_error else validate(parsed, normalized)
        if not errors:
            response = parsed
            break
        message = render_repair(user, text, errors)

    if response is None:
        listed = "\n".join(f"- {error}" for error in errors)
        raise ValueError(
            f"the LLM returned no valid answer in {MAX_ATTEMPTS} attempts:\n{listed}"
        )

    scribbles = describe_scribbles(response)
    bundle = {
        "schema_version": SCHEMA_VERSION,
        "recording_id": rec_id,
        "source_flow": source_flow,
        "provenance": {
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "scriber": __version__,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "attempts": len(responses),
        },
        "recording": response["recording"],
        "annotations": [
            {
                "action": ann["action"],
                "observed": ann["observed"],
                "purpose": ann.get("purpose", ""),
            }
            for ann in response["annotations"]
        ],
        "scribbles": scribbles,
    }
    workflows = {
        s["id"]: workflow_flow(s, flow, rec_id, source_flow)
        for s in scribbles
    }
    return Extraction(rec_id, card, bundle, workflows, responses)


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write(extraction: Extraction, out_dir: Path) -> None:
    """Store the bundle, replacing any earlier extraction of the same recording."""
    workflows_dir = out_dir / "workflows"
    if workflows_dir.exists():
        shutil.rmtree(workflows_dir)
    workflows_dir.mkdir(parents=True)
    _write_json(out_dir / "context.json", extraction.card)
    _write_json(out_dir / "scribbles.json", extraction.bundle)
    _write_json(out_dir / "llm_responses.json", extraction.responses)
    for sid, workflow in extraction.workflows.items():
        _write_json(workflows_dir / f"{sid}.json", workflow)


__all__ = ["LIBRARY_DIR", "Extraction", "recording_id", "parse_response", "extract", "write"]
