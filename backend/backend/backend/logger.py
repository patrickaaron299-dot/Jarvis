"""
Simple logging setup for the JARVIS backend.
"""

import logging
import os
from pathlib import Path


def setup_logger(name: str = "jarvis") -> logging.Logger:
    """
    Create and return a logger that writes to the console and a log file.

    The log file is stored in the backend/logs directory.
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if setup_logger() is called more than once.
    if logger.handlers:
        return logger

    log_level = os.getenv("JARVIS_LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, log_level, logging.INFO))

    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "jarvis.log"

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# Ready-to-use default logger.
logger = setup_logger()