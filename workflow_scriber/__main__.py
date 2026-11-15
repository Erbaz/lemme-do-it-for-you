"""Command line: ``watch`` (record a flow), ``extract`` (scribbles).

    python -m workflow_scriber watch                  # recorded_flows/workflow_<stamp>.json
    python -m workflow_scriber watch -o myflow.json   # recorded_flows/myflow.json
    python -m workflow_scriber extract                # newest recording
    python -m workflow_scriber extract myflow.json    # workflow_scriber/library/myflow/
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from . import RECORDED_FLOWS_DIR


def _flow_path(name: Optional[str]) -> Path:
    if not name:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return RECORDED_FLOWS_DIR / f"workflow_{stamp}.json"
    path = Path(name)
    if path.is_absolute() or path.parent != Path("."):
        return path
    return RECORDED_FLOWS_DIR / path


def _latest_flow() -> Optional[Path]:
    """Newest recording; replay's pruned ``*.replayed.json`` copies are not recordings."""
    recordings = [
        path for path in RECORDED_FLOWS_DIR.glob("*.json")
        if not path.name.endswith(".replayed.json")
    ]
    return max(recordings, key=lambda path: path.stat().st_mtime, default=None)


def cmd_watch(args: argparse.Namespace) -> int:
    from .watcher import watch

    return watch(
        _flow_path(args.out),
        max_depth=args.max_depth,
        quiet=args.quiet,
        events=args.events,
    )


def cmd_extract(args: argparse.Namespace) -> int:
    import json

    from .extract import LIBRARY_DIR, extract, recording_id, write
    from .llm import make_completer

    if args.flow:
        flow_path = _flow_path(args.flow)
    else:
        flow_path = _latest_flow()
        if flow_path is None:
            print(f"No recordings in {RECORDED_FLOWS_DIR}. Run watch first.")
            return 1
    flow = json.loads(flow_path.read_text(encoding="utf-8"))
    out_dir = LIBRARY_DIR / recording_id(flow_path)

    complete, model = make_completer()
    print(f"Asking {model} for scribbles in {flow_path.name} ...")
    try:
        result = extract(flow, out_dir.name, flow_path.name, complete, model=model)
    except ValueError as exc:
        print(f"No scribbles written.\n{exc}")
        return 1
    write(result, out_dir)

    print(f"Wrote {out_dir}")
    for scribble in result.bundle["scribbles"]:
        print(f"\n{scribble['title']}  [{len(scribble['actions'])} actions]")
        print(f"  {scribble['description']}")
        print(f"  python -m workflow_scriber.replay {out_dir / scribble['workflow']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    from .discovery import DEFAULT_MAX_DEPTH

    parser = argparse.ArgumentParser(
        prog="workflow_scriber",
        description="Record human desktop actions as gui_agent tool calls.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    watch = sub.add_parser("watch", help="watch the human and write tool calls")
    watch.add_argument("-o", "--out", default=None,
                       help="output file inside recorded_flows/ "
                            "(default: workflow_<timestamp>.json)")
    watch.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH,
                       help="UIA tree depth to index (default: 10)")
    watch.add_argument("-q", "--quiet", action="store_true",
                       help="do not print each action")
    watch.add_argument("--events", action="store_true",
                       help="probe WinEvents (focus/invoke/selection) and log "
                            "them to <out>.events.txt (off by default)")
    watch.set_defaults(func=cmd_watch)

    extract = sub.add_parser(
        "extract", help="ask the LLM to split a recording into replayable scribbles",
    )
    extract.add_argument("flow", nargs="?", default=None,
                         help="recorded flow (default: newest in recorded_flows/; "
                              "bare names resolve there)")
    extract.set_defaults(func=cmd_extract)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
