from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.infra.paths import logs_dir


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("ffmerge")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logfile = logs_dir() / "app.log"
    file_handler = RotatingFileHandler(logfile, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger

