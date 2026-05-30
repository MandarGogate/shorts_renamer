"""Structured logging configuration for ShortsSync.

Usage in any module:
    from shortssync.log import get_logger
    logger = get_logger(__name__)

Call ``setup_logging()`` once at application startup (CLI/web entry point)
to configure the root handler. Without it, logs go to stderr at WARNING level
(Python default), which is fine for library use.
"""

import logging
import os
import sys

_CONFIGURED = False

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str) -> logging.Logger:
    """Return a logger for the given module name."""
    return logging.getLogger(name)


def setup_logging(level: str | None = None) -> None:
    """Configure the root logger for ShortsSync.

    *level* defaults to the ``SHORTSSYNC_LOG_LEVEL`` env var, or ``INFO``.
    Safe to call multiple times (only configures once).
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    resolved = (level or os.environ.get("SHORTSSYNC_LOG_LEVEL", "INFO")).upper()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))

    root = logging.getLogger("shortssync")
    root.setLevel(getattr(logging, resolved, logging.INFO))
    root.addHandler(handler)
    root.propagate = False
