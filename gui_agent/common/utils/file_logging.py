"""File-based structured logging for GUI Agent runs.

Writes all structlog output to a timestamped txt file in gui_agent/.logs/.
Logs are flushed on process exit (via atexit) so each run gets its own file.
"""

import atexit
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog
from structlog.types import Processor


class FileLogHandler:
    """Captures structlog output to a per-run txt file."""

    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"run_{self.timestamp}.txt"
        self._file = open(self.log_file, "w", encoding="utf-8", buffering=1)
        self._stdout = sys.stdout
        self._stderr = sys.stderr

        # Register flush on exit
        atexit.register(self.close)

    def write(self, message: str) -> None:
        """Write a message to the log file."""
        self._file.write(message)
        self._file.flush()

    def flush(self) -> None:
        """Flush the underlying file."""
        self._file.flush()

    def close(self) -> None:
        """Close the log file."""
        try:
            self._file.close()
        except Exception:
            pass


# Global handler instance
_handler: Optional[FileLogHandler] = None


def setup_file_logging(log_dir: Optional[str] = None) -> FileLogHandler:
    """Initialize file logging for the current run.

    Args:
        log_dir: Path to the logs directory. Defaults to gui_agent/.logs/

    Returns:
        The FileLogHandler instance.
    """
    global _handler

    if log_dir is None:
        # Default: gui_agent/.logs/ relative to project root (3 levels up from this file)
        log_dir = Path(__file__).parent.parent.parent / ".logs"
    else:
        log_dir = Path(log_dir)

    handler = FileLogHandler(log_dir)
    _handler = handler

    # Also tee stdout/stderr to the log file so all output is captured
    class Tee:
        def __init__(self, original, handler):
            self.original = original
            self.handler = handler

        def write(self, message):
            self.original.write(message)
            self.handler.write(message)

        def flush(self):
            self.original.flush()
            self.handler.flush()

    sys.stdout = Tee(sys.stdout, handler)
    sys.stderr = Tee(sys.stderr, handler)

    return handler


def close_file_logging() -> None:
    """Close the file logging handler."""
    global _handler
    if _handler:
        _handler.close()
        _handler = None


def get_log_file() -> Optional[str]:
    """Return the path to the current log file."""
    return str(_handler.log_file) if _handler else None


def file_log_processor(logger, method_name, event_dict):
    """structlog processor that writes to the log file."""
    if _handler:
        # Format the event dict as a readable line
        timestamp = event_dict.pop("timestamp", "")
        level = event_dict.pop("level", method_name)
        event = event_dict.pop("event", "")
        rest = " ".join(f"{k}={v}" for k, v in event_dict.items())
        line = f"{timestamp} [{level.upper():7}] {event} {rest}\n"
        _handler.write(line)
    return event_dict