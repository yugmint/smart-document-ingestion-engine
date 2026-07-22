# src/utils/logger.py

"""
Centralized logging configuration.

Every module in the pipeline imports `logger` from here so log
level, format, and destination are controlled in exactly one place.

Configure at runtime via the LOG_LEVEL env var, e.g.:

    LOG_LEVEL=DEBUG python -m ingestion.pipeline
"""

import logging
import os
import sys

_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def _build_logger() -> logging.Logger:
    log = logging.getLogger("ingestion")

    if log.handlers:
        # Avoid duplicate handlers if the module is re-imported
        # (common with reload-on-change dev servers / notebooks).
        return log

    log.setLevel(_LEVEL)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT))

    log.addHandler(handler)
    log.propagate = False

    return log


logger = _build_logger()
