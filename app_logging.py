"""Small, dependency-free runtime logging shared by the launcher and server."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path

LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUP_COUNT = 3
_LOGGER: logging.Logger | None = None


def log_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.cwd()
    return base / "L4D2ModManager" / "logs" / "manager.log"


def _logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER

    logger = logging.getLogger("tudou_mod_manager")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
            delay=True,
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(process)d] %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)
    except (OSError, ValueError):
        # Diagnostics must never prevent the manager from starting.
        logger.addHandler(logging.NullHandler())
    _LOGGER = logger
    return logger


def write_log(
    message: str,
    *,
    component: str = "app",
    error: bool = False,
    exc_info: bool = False,
) -> None:
    """Append a diagnostic line without allowing logging failures to escape."""

    try:
        logger = _logger()
        formatted = f"[{component}] {message}"
        if error:
            logger.error(formatted, exc_info=exc_info)
        else:
            logger.info(formatted)
    except Exception:
        return


def close_logging() -> None:
    """Close file handlers when a process is shutting down or tests finish."""

    global _LOGGER
    logger = _LOGGER
    if logger is None:
        return
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    _LOGGER = None
