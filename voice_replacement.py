"""Safe installation and restoration for voice replacement VPKs.

The original package ships a batch file disguised as ``addoninfo.txt``.  This
module reproduces its path rules without executing content from the VPK.
"""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import uuid

from nekovpk import read_vpk_entries
from vpk_detector import detect_voice_archive_roles, is_direct_voice_path, read_vpk_file, read_vpk_paths
from manager_storage import VOICE_BACKUP_DIR, ensure_manager_data_layout, migrate_voice_backup_path


VOICE_PREFIX = "sound/player/survivor/voice/"
VOICE_STATE_KEY = "voiceInstallations"
VPK_SUFFIXES = {".vpk", ".vpk1"}

VOICE_ROLES = {
    "namvet": "Bill",
    "biker": "Francis",
    "manager": "Louis",
    "teengirl": "Zoey",
    "coach": "Coach",
    "gambler": "Nick",
    "mechanic": "Ellis",
    "producer": "Rochelle",
}
INFECTED_VOICE_ROLES = {
    "boomer": "Boomer",
    "hunter": "Hunter",
    "smoker": "Smoker",
    "charger": "Charger",
    "jockey": "Jockey",
    "spitter": "Spitter",
    "tank": "Tank",
    "witch": "Witch",
}
VOICE_ROLE_NAMES = {**VOICE_ROLES, **INFECTED_VOICE_ROLES}
TEAM_ONE = {"namvet", "biker", "manager", "teengirl"}
TEAM_ONE_ROOTS = ("left4dead2", "left4dead2_dlc1", "left4dead2_dlc2", "left4dead2_dlc3")
TEAM_TWO_ROOTS = ("left4dead2", "left4dead2_dlc1")


class VoiceReplacementError(ValueError):
    """Raised when a voice package cannot be safely processed."""


class VoiceReplacementConflict(VoiceReplacementError):
    """Raised when another managed voice installation owns target files."""

    def __init__(self, conflicts: list[dict]):
        self.conflicts = conflicts
        names = ", ".join(str(item.get("modName") or item.get("modId")) for item in conflicts)
        super().__init__(f"目标语音目录已被其他语音包占用：{names}")


def _metadata_path(mod_root: Path) -> Path:
    return mod_root / ".l4d2_mod_manager.json"


def _read_metadata(mod_root: Path) -> dict:
    try:
        payload = json.loads(_metadata_path(mod_root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_metadata(mod_root: Path, payload: dict) -> None:
    target = _metadata_path(mod_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_voice_installations(mod_root: str | Path) -> list[dict]:
    root = Path(mod_root).resolve()
    ensure_manager_data_layout(root)
    records = _read_metadata(root).get(VOICE_STATE_KEY, [])
    normalized = []
    changed = False
    for record in records:
        if not isinstance(record, dict) or not record.get("id"):
            continue
        updated = dict(record)
        backup_dir = migrate_voice_backup_path(str(updated.get("backupDir", "")))
        if backup_dir != updated.get("backupDir"):
            updated["backupDir"] = backup_dir
            changed = True
        normalized.append(updated)
    if changed:
        save_voice_installations(root, normalized)
    return normalized


def save_voice_installations(mod_root: str | Path, records: list[dict]) -> None:
    root = Path(mod_root).resolve()
    ensure_manager_data_layout(root)
    payload = _read_metadata(root)
    payload[VOICE_STATE_KEY] = records
    _save_metadata(root, payload)


def _safe_relative(root: Path, relative: str | Path) -> Path:
    candidate = (root / Path(str(relative).replace("\\", "/"))).resolve()
    if candidate != root and root not in candidate.parents:
        raise VoiceReplacementError("语音路径超出了允许的游戏目录")
    return candidate


def _game_root(mod_root: Path) -> Path:
    root = mod_root.resolve()
    if root.name.casefold() == "addons":
        return root.parent
    for candidate in (root, *root.parents):
        if candidate.name.casefold() == "left4dead2":
            return candidate
    raise VoiceReplacementError("无法从当前 Mod 目录定位 left4dead2 游戏目录")


def _game_parent(mod_root: Path) -> Path:
    return _game_root(mod_root).parent


def _voice_paths(vpk_path: Path) -> list[str]:
    return _voice_paths_from_paths(read_vpk_paths(vpk_path))


def _voice_paths_from_paths(paths: list[str]) -> list[str]:
    return sorted(path for path in paths if is_direct_voice_path(path))


def _group_voice_paths(paths: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for path in paths:
        parts = path.split("/")
        if len(parts) < 6 or parts[:2] != ["sound", "player"] or parts[3] != "voice":
            continue
        role = parts[2] if parts[2] in INFECTED_VOICE_ROLES else parts[4]
        if role in VOICE_ROLE_NAMES:
            grouped.setdefault(role, []).append(path)
    return grouped


def detect_voice_roles(paths: list[str]) -> list[dict]:
    """Return survivor or infected roles represented by WAVs or archives."""

    grouped = _group_voice_paths(paths)
    archive_roles = detect_voice_archive_roles(paths)
    return [
        {
            "id": role,
            "name": VOICE_ROLE_NAMES[role],
            "side": "infected" if role in INFECTED_VOICE_ROLES else "survivor",
            "fileCount": len(grouped.get(role, [])),
            "sourceType": "archive" if role not in grouped else "wav",
            "archiveFiles": archive_roles.get(role, []),
        }
        for role in VOICE_ROLE_NAMES
        if role in grouped or role in archive_roles
    ]


def detect_voice_replacement_mode(file_path: str | Path, paths: list[str] | None = None) -> str | None:
    """Classify a voice VPK as a direct addon or an external install package."""
    paths = paths if paths is not None else read_vpk_paths(file_path)
    direct_voice = any(is_direct_voice_path(path) for path in paths)
    if not direct_voice and not detect_voice_archive_roles(paths):
        return None
    if not direct_voice:
        return "manual"
    if any(Path(path).suffix.casefold() in {".bat", ".cmd"} for path in paths):
        return "manual"
    addoninfo = read_vpk_file(file_path, "addoninfo.txt") or b""
    text = addoninfo.decode("utf-8", errors="replace").lstrip().casefold()
    if text.startswith("@echo off") or re.search(
        r"(?m)^\s*(?:set|if\s+exist|goto|copy|xcopy|robocopy|chcp)\b", text
    ):
        return "manual"
    return "automatic"


def _role_game_roots(game_parent: Path, role: str) -> list[tuple[str, Path]]:
    root_names = TEAM_ONE_ROOTS if role in TEAM_ONE else TEAM_TWO_ROOTS
    result = []
    for root_name in root_names:
        candidate = game_parent / root_name
        if candidate.is_dir():
            result.append((root_name, candidate))
    return result


def _target_plan(game_parent: Path, role: str, source_paths: list[str]) -> dict:
    target_dirs = []
    overwrite = 0
    new_files = 0
    missing_directories = []
    filenames = [path.rsplit("/", 1)[-1] for path in source_paths]
    for root_name, root in _role_game_roots(game_parent, role):
        voice_dir = root / "sound" / "player" / "survivor" / "voice" / role
        if not voice_dir.is_dir():
            missing_directories.append(f"{root_name}/sound/player/survivor/voice/{role}")
            continue
        existing = sum((voice_dir / filename).is_file() for filename in filenames)
        target_dirs.append(
            {
                "root": root_name,
                "path": voice_dir.relative_to(game_parent).as_posix(),
                "fileCount": len(filenames),
                "overwrite": existing,
                "new": len(filenames) - existing,
            }
        )
        overwrite += existing
        new_files += len(filenames) - existing
    return {
        "id": role,
        "name": VOICE_ROLE_NAMES[role],
        "side": "survivor",
        "sourceFileCount": len(source_paths),
        "targetDirectories": target_dirs,
        "overwriteCount": overwrite,
        "newCount": new_files,
        "missingDirectories": missing_directories,
        "installable": bool(target_dirs),
    }


def _planned_target_paths(roles: list[dict], grouped: dict[str, list[str]]) -> set[str]:
    targets: set[str] = set()
    for role in roles:
        source_paths = grouped.get(role["id"], [])
        for directory in role.get("targetDirectories", []):
            for source_path in source_paths:
                filename = source_path.rsplit("/", 1)[-1]
                targets.add(f"{directory['path']}/{filename}".replace("\\", "/").casefold())
    return targets


def _record_target_paths(record: dict) -> set[str]:
    return {
        str(item.get("target", "")).replace("\\", "/").lstrip("./").casefold()
        for item in record.get("files", [])
        if item.get("target")
    }


def _find_voice_installation_conflicts(records: list[dict], target_paths: set[str]) -> list[dict]:
    conflicts = []
    for record in records:
        record_paths = _record_target_paths(record)
        if not record_paths or record_paths & target_paths:
            conflicts.append(record)
    return conflicts


def _find_voice_vpk(mod_root: Path, mod: dict) -> Path:
    candidates = [
        _safe_relative(mod_root, relative)
        for relative in mod.get("vpkFiles", [])
        if Path(relative).suffix.casefold() in VPK_SUFFIXES
    ]
    voice_candidates = []
    for path in candidates:
        paths = read_vpk_paths(path)
        if _voice_paths_from_paths(paths) or detect_voice_archive_roles(paths):
            voice_candidates.append(path)
    if len(voice_candidates) != 1:
        if not voice_candidates:
            raise VoiceReplacementError("这个 Mod 没有可识别的语音文件")
        raise VoiceReplacementError("一个 Mod 包含多个语音 VPK，暂不自动安装")
    return voice_candidates[0]


def inspect_voice_package(mod_root: str | Path, mod: dict) -> dict:
    """Return a no-write installation preview for a voice replacement Mod."""

    root = Path(mod_root).resolve()
    ensure_manager_data_layout(root)
    vpk_path = _find_voice_vpk(root, mod)
    game_parent = _game_parent(root)
    paths = read_vpk_paths(vpk_path)
    direct_paths = _voice_paths_from_paths(paths)
    grouped = _group_voice_paths(direct_paths)
    archive_roles = detect_voice_archive_roles(paths)
    manual_only = not direct_paths and bool(archive_roles)
    roles = []
    for role in VOICE_ROLE_NAMES:
        if role in grouped:
            if role in VOICE_ROLES:
                plan = _target_plan(game_parent, role, grouped[role])
            else:
                plan = {
                    "id": role,
                    "name": VOICE_ROLE_NAMES[role],
                    "side": "infected",
                    "sourceFileCount": len(grouped[role]),
                    "targetDirectories": [],
                    "overwriteCount": 0,
                    "newCount": 0,
                    "missingDirectories": [],
                    "installable": False,
                }
            plan["sourceType"] = "wav"
            plan["archiveFiles"] = archive_roles.get(role, [])
            roles.append(plan)
        elif role in archive_roles:
            roles.append(
                {
                    "id": role,
                    "name": VOICE_ROLE_NAMES[role],
                    "side": "infected" if role in INFECTED_VOICE_ROLES else "survivor",
                    "sourceFileCount": 0,
                    "sourceType": "archive",
                    "archiveFiles": archive_roles[role],
                    "targetDirectories": [],
                    "missingDirectories": [],
                    "overwriteCount": 0,
                    "newCount": 0,
                    "installable": False,
                }
            )
    installations = load_voice_installations(root)
    current = next((item for item in installations if item.get("modId") == mod.get("id")), None)
    other = [item for item in installations if item.get("modId") != mod.get("id")]
    target_paths = _planned_target_paths(roles, grouped)
    return {
        "format": "voice_replacement",
        "vpkPath": vpk_path.relative_to(root).as_posix(),
        "gameRoot": _game_root(root).as_posix(),
        "gameParent": game_parent.as_posix(),
        "sourceFileCount": sum(len(paths) for paths in grouped.values()),
        "sourceArchiveCount": sum(len(paths) for paths in archive_roles.values()),
        "sourceFiles": sorted(archive_path for paths in archive_roles.values() for archive_path in paths),
        "manualOnly": manual_only,
        "roles": roles,
        "installed": current is not None,
        "installationId": current.get("id") if current else None,
        "activeInstallations": [
            {"id": item.get("id"), "modId": item.get("modId"), "modName": item.get("modName")}
            for item in installations
        ],
        "conflicts": [
            {"id": item.get("id"), "modId": item.get("modId"), "modName": item.get("modName")}
            for item in _find_voice_installation_conflicts(other, target_paths)
        ],
    }


def _backup_path(root: Path, installation_id: str, target_relative: str) -> Path:
    backup_root = root / VOICE_BACKUP_DIR / installation_id
    return _safe_relative(backup_root, target_relative)


def _target_relative(game_parent: Path, target: Path) -> str:
    return target.resolve().relative_to(game_parent.resolve()).as_posix()


def _restore_record(mod_root: Path, record: dict, *, remove_backup: bool = True) -> None:
    game_parent = Path(str(record["gameParent"])).resolve()
    backup_root = _safe_relative(mod_root, record["backupDir"])
    for item in reversed(record.get("files", [])):
        target = _safe_relative(game_parent, item["target"])
        backup = _safe_relative(backup_root, item["backup"])
        if item.get("existed"):
            if not backup.is_file():
                raise VoiceReplacementError(f"缺少语音备份文件：{backup.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.voice-restore-{uuid.uuid4().hex}.tmp")
            shutil.copyfile(backup, temporary)
            os.replace(temporary, target)
        elif target.is_file():
            target.unlink()
    if remove_backup:
        shutil.rmtree(_safe_relative(mod_root, record["backupDir"]), ignore_errors=True)


def _stage_current_record(game_parent: Path, record: dict, stage_root: Path) -> list[dict]:
    staged = []
    for item in record.get("files", []):
        target = _safe_relative(game_parent, item["target"])
        stage = _safe_relative(stage_root, item["target"])
        existed = target.is_file()
        if existed:
            stage.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, stage)
        staged.append({"target": item["target"], "stage": item["target"], "existed": existed})
    return staged


def _restore_staged_record(game_parent: Path, stage_root: Path, staged: list[dict]) -> None:
    for item in reversed(staged):
        target = _safe_relative(game_parent, item["target"])
        stage = _safe_relative(stage_root, item["stage"])
        if item.get("existed"):
            if not stage.is_file():
                raise VoiceReplacementError(f"缺少替换回滚文件：{stage.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.voice-rollback-{uuid.uuid4().hex}.tmp")
            shutil.copyfile(stage, temporary)
            os.replace(temporary, target)
        elif target.is_file():
            target.unlink()


def _restore_partial(game_parent: Path, record: dict, written: list[dict], backup_root: Path) -> None:
    for item in reversed(written):
        target = _safe_relative(game_parent, item["target"])
        backup = _safe_relative(backup_root, item["backup"])
        if item.get("existed") and backup.is_file():
            shutil.copyfile(backup, target)
        elif not item.get("existed") and target.is_file():
            target.unlink()


def restore_voice_package(mod_root: str | Path, mod_id: str) -> dict:
    root = Path(mod_root).resolve()
    ensure_manager_data_layout(root)
    records = load_voice_installations(root)
    record = next((item for item in records if item.get("modId") == mod_id), None)
    if not record:
        raise VoiceReplacementError("这个 Mod 当前没有已安装的语音替换记录")
    _restore_record(root, record)
    save_voice_installations(root, [item for item in records if item.get("id") != record.get("id")])
    return {"restored": True, "installationId": record.get("id"), "modId": mod_id}


def install_voice_package(
    mod_root: str | Path,
    mod: dict,
    *,
    replace_existing: bool = False,
) -> dict:
    """Install a voice package with backups and rollback on failure."""

    root = Path(mod_root).resolve()
    ensure_manager_data_layout(root)
    vpk_path = _find_voice_vpk(root, mod)
    game_parent = _game_parent(root)
    grouped = _group_voice_paths(_voice_paths(vpk_path))
    roles = [_target_plan(game_parent, role, grouped[role]) for role in VOICE_ROLES if role in grouped]
    plans = [role for role in roles if role["installable"]]
    if not plans:
        raise VoiceReplacementError("没有找到可安装的游戏语音目录")

    records = load_voice_installations(root)
    target_paths = _planned_target_paths(plans, grouped)
    conflicts = _find_voice_installation_conflicts(
        [item for item in records if item.get("modId") != mod.get("id")],
        target_paths,
    )
    if conflicts and not replace_existing:
        raise VoiceReplacementConflict(conflicts)
    if any(item.get("modId") == mod.get("id") for item in records):
        raise VoiceReplacementError("这个 Mod 已经安装过语音替换，请先恢复原始语音后再安装")
    old_records = list(records)
    staged_conflicts: list[dict] = []
    stage_root: Path | None = None
    if replace_existing:
        stage_root = root / VOICE_BACKUP_DIR / f".pending-{uuid.uuid4().hex}"
        try:
            for record in conflicts:
                staged_conflicts.extend(_stage_current_record(game_parent, record, stage_root))
                _restore_record(root, record, remove_backup=False)
        except Exception:
            if stage_root:
                _restore_staged_record(game_parent, stage_root, staged_conflicts)
                shutil.rmtree(stage_root, ignore_errors=True)
            raise
        records = [item for item in records if item.get("modId") == mod.get("id")]

    entries = read_vpk_entries(vpk_path)
    source_entries = {
        path: content
        for path, content in entries.items()
        if path.startswith(VOICE_PREFIX) and path.endswith(".wav")
    }
    installation_id = uuid.uuid4().hex
    backup_dir = (Path(VOICE_BACKUP_DIR) / installation_id).as_posix()
    backup_root = root / backup_dir
    written: list[dict] = []
    record = {
        "id": installation_id,
        "modId": str(mod.get("id", "")),
        "modName": str(mod.get("name", "")),
        "vpkPath": vpk_path.relative_to(root).as_posix(),
        "gameParent": game_parent.as_posix(),
        "backupDir": backup_dir,
        "installedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "files": [],
    }

    try:
        for role in plans:
            for target_dir in role["targetDirectories"]:
                target_base = _safe_relative(game_parent, target_dir["path"])
                for source_path in grouped[role["id"]]:
                    filename = source_path.rsplit("/", 1)[-1]
                    target = _safe_relative(target_base, filename)
                    target_relative = _target_relative(game_parent, target)
                    backup_relative = target_relative
                    backup = _backup_path(root, installation_id, backup_relative)
                    existed = target.is_file()
                    if existed:
                        backup.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(target, backup)
                    content = source_entries.get(source_path)
                    if content is None:
                        raise VoiceReplacementError(f"VPK 中缺少语音内容：{source_path}")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = target.with_name(f".{target.name}.voice-install-{uuid.uuid4().hex}.tmp")
                    temporary.write_bytes(content)
                    os.replace(temporary, target)
                    item = {"target": target_relative, "backup": backup_relative, "existed": existed}
                    written.append(item)
                    record["files"].append(item)
        save_voice_installations(root, [*records, record])
    except Exception:
        _restore_partial(game_parent, record, written, backup_root)
        shutil.rmtree(backup_root, ignore_errors=True)
        if replace_existing:
            if stage_root:
                _restore_staged_record(game_parent, stage_root, staged_conflicts)
            save_voice_installations(root, old_records)
        raise

    if replace_existing:
        for old in conflicts:
            shutil.rmtree(_safe_relative(root, old["backupDir"]), ignore_errors=True)
        if stage_root:
            shutil.rmtree(stage_root, ignore_errors=True)
    return {
        "installed": True,
        "installationId": installation_id,
        "modId": str(mod.get("id", "")),
        "fileCount": len(record["files"]),
        "backupDir": backup_dir,
    }
