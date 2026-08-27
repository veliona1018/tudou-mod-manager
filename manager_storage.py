"""Shared storage layout for files created by Tudou Mod Manager."""

from __future__ import annotations

import filecmp
import shutil
import uuid
from pathlib import Path


MANAGER_DATA_DIR = "tudou mod manger"
LEGACY_SPRAY_PREVIEW_DIR = ".l4d2_mod_manager_spray_previews"
LEGACY_VOICE_BACKUP_DIR = ".l4d2_voice_backups"
SPRAY_PREVIEW_DIR = f"{MANAGER_DATA_DIR}/{LEGACY_SPRAY_PREVIEW_DIR}"
VOICE_BACKUP_DIR = f"{MANAGER_DATA_DIR}/{LEGACY_VOICE_BACKUP_DIR}"
SPRAY_STATE_FILE = f"{MANAGER_DATA_DIR}/.l4d2_mod_manager_sprays.json"
IMPORTED_SPRAY_DIR = f"{MANAGER_DATA_DIR}/imported_sprays"
LEGACY_SPRAY_STATE_FILE = ".l4d2_mod_manager_sprays.json"


def _conflict_path(target: Path) -> Path:
    return target.with_name(f"{target.stem}.legacy-{uuid.uuid4().hex[:8]}{target.suffix}")


def _merge_directory(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in list(source.iterdir()):
        destination = target / child.name
        if child.is_dir() and destination.is_dir():
            _merge_directory(child, destination)
            continue
        if destination.exists():
            if child.is_file() and destination.is_file() and filecmp.cmp(child, destination, shallow=False):
                child.unlink()
                continue
            destination = _conflict_path(destination)
        shutil.move(str(child), str(destination))
    try:
        source.rmdir()
    except OSError:
        pass


def _move_legacy_path(root: Path, relative_source: str, relative_target: str) -> None:
    source = root / relative_source
    target = root / relative_target
    if source.is_dir():
        _merge_directory(source, target)
    elif source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if filecmp.cmp(source, target, shallow=False):
                source.unlink()
            else:
                shutil.move(str(source), str(_conflict_path(target)))
        else:
            shutil.move(str(source), str(target))


def ensure_manager_data_layout(root: str | Path) -> Path:
    """Create the Tudou data directory and migrate older manager data once."""

    root_path = Path(root).resolve()
    data_root = root_path / MANAGER_DATA_DIR
    data_root.mkdir(parents=True, exist_ok=True)
    _move_legacy_path(root_path, LEGACY_SPRAY_PREVIEW_DIR, SPRAY_PREVIEW_DIR)
    _move_legacy_path(root_path, LEGACY_VOICE_BACKUP_DIR, VOICE_BACKUP_DIR)
    _move_legacy_path(root_path, LEGACY_SPRAY_STATE_FILE, SPRAY_STATE_FILE)
    return data_root


def migrate_voice_backup_path(relative_path: str) -> str:
    """Update metadata paths written before the shared data directory existed."""

    prefix = f"{LEGACY_VOICE_BACKUP_DIR}/"
    normalized = str(relative_path).replace("\\", "/")
    if normalized.casefold().startswith(prefix.casefold()):
        return f"{VOICE_BACKUP_DIR}/{normalized[len(prefix):]}"
    return normalized
