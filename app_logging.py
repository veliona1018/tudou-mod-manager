"""Small, dependency-free runtime logging shared by the launcher and server."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path

LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUP_COUNT = 3
LOG_READ_MAX_BYTES = 1024 * 1024
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


def log_files() -> list[Path]:
    """Return the current log and any existing rotated files."""

    path = log_path()
    try:
        return [path, *sorted(path.parent.glob(f"{path.name}.*"))]
    except OSError:
        return [path]


def read_log(max_bytes: int = LOG_READ_MAX_BYTES) -> dict[str, object]:
    """Read the newest part of the log without allowing diagnostics to fail startup."""

    path = log_path()
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raw = b""
    except OSError as error:
        raise OSError(f"无法读取日志文件：{error}") from error
    truncated = len(raw) > max_bytes
    if truncated:
        raw = raw[-max_bytes:]
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        size = 0
    return {
        "path": str(path),
        "content": raw.decode("utf-8", errors="replace"),
        "size": size,
        "truncated": truncated,
        "maxBytes": max_bytes,
    }


def clear_logs() -> int:
    """Remove the current log and its rotated backups, returning the file count."""

    close_logging()
    removed = 0
    for path in log_files():
        try:
            if path.exists():
                path.unlink()
                removed += 1
        except OSError as error:
            raise OSError(f"无法清理日志文件：{path.name}：{error}") from error
    return removed


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
