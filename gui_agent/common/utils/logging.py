"""Logging configuration for the GUI agent."""

import logging
import structlog


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
    """
    # Configure Python's standard logging module so logger.info() etc. work
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        force=True,
    )

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(level),
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
    )