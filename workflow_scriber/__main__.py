"""Command line: ``watch`` (record a flow).

    python -m workflow_scriber watch                  # recorded_flows/workflow_<stamp>.json
    python -m workflow_scriber watch -o myflow.json   # recorded_flows/myflow.json
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


def cmd_watch(args: argparse.Namespace) -> int:
    from .watcher import watch

    return watch(
        _flow_path(args.out),
        max_depth=args.max_depth,
        quiet=args.quiet,
        events=args.events,
    )


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

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
