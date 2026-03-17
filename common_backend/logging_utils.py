from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def get_activity_logger() -> logging.Logger:
    logs_dir = Path("common_backend") / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "activity.log"

    logger = logging.getLogger("fitquest.activity")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(log_file, maxBytes=1_500_000, backupCount=5, encoding="utf-8")
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger
