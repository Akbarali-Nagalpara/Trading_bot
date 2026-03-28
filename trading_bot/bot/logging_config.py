"""Centralized logging configuration for the trading bot."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(console_level: int = logging.WARNING) -> Path:
    """Configure logging and return the log file path.

    File logs always remain detailed (DEBUG) while console logging is configurable.
    """
    project_root = Path(__file__).resolve().parent.parent
    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    log_file = logs_dir / "app.log"
    root_logger = logging.getLogger()

    if root_logger.handlers:
        root_logger.setLevel(logging.DEBUG)
        for handler in root_logger.handlers:
            if isinstance(handler, RotatingFileHandler):
                handler.setLevel(logging.DEBUG)
            elif isinstance(handler, logging.StreamHandler):
                handler.setLevel(console_level)
        return log_file

    root_logger.setLevel(logging.DEBUG)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return log_file
