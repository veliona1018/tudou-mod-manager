"""Serve the local Mod catalog and its preview files."""

from __future__ import annotations

import argparse
import ctypes
from datetime import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from ctypes import wintypes

from folder_picker import choose_folder

from mod_catalog import (
    IMAGE_EXTENSIONS,
    VPK_EXTENSIONS,
    build_catalog,
    _key,
    load_hidden_tags,
    load_marked_tags,
    load_custom_names,
    load_custom_tags,
    save_hidden_tags,
    save_marked_tags,
    save_custom_names,
    save_custom_tags,
)
from nekovpk import convert_nekovpk_target, map_nekovpk_target
from spray_manager import (
    SprayError,
    apply_spray_collection,
    delete_imported_spray,
    import_spray_images,
    list_spray_assets,
    save_spray_configuration,
    reset_spray_state,
    spray_preview_asset,
    spray_preview_frame,
)
from manager_storage import ensure_manager_data_layout
from voice_replacement import (
    VoiceReplacementConflict,
    VoiceReplacementError,
    inspect_voice_package,
    install_voice_package,
    load_voice_installations,
    restore_voice_package,
)


ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar"}
SETTINGS_KEY_DEFAULT = "defaultFolder"
SETTINGS_KEY_LAST = "lastFolder"
SETTINGS_KEY_DEEPSEEK_API_KEY = "deepseekApiKey"
SETTINGS_KEY_DEEPSEEK_MODEL = "deepseekModel"
SETTINGS_KEY_AI_PROMPTS = "aiPrompts"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_MODELS = {"deepseek-chat", "deepseek-reasoner"}
DEFAULT_AI_PROMPT = (
    "请分析这个求生之路 2（Left 4 Dead 2）Mod。根据提供的 VPK 内部路径和检测证据，"
    "用简体中文说明：1. 它大概是什么；2. 可能替换或影响什么内容；3. 判断依据；"
    "4. 不确定的地方。不要把文件名猜测当成确定事实，也不要编造不存在的内容。"
    "如果只有脚本、界面或材质路径，请解释它们可能的用途。"
)


def resource_root() -> Path:
    """Return the directory containing bundled web resources or source files."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    return Path(bundle_root).resolve() if bundle_root else Path(__file__).parent.resolve()


def log(message: str) -> None:
    """Write diagnostics when a console is available."""
    if sys.stdout is not None:
        print(message)


def source_version(root: Path) -> str:
    """Return a stable version for the files that make up the local app."""
    paths = [root / "index.html", root / "app.js", root / "styles.css"]
    paths.extend(sorted(root.glob("*.py")))
    digest = hashlib.sha256()
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        digest.update(path.name.encode("utf-8"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        digest.update(str(stat.st_size).encode("ascii"))
    return digest.hexdigest()


def settings_path() -> Path:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.cwd()))
    return local_app_data / "L4D2ModManager" / "settings.json"


def _read_settings() -> dict:
    try:
        payload = json.loads(settings_path().read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def _valid_folder(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    folder = Path(value).expanduser().resolve()
    return folder if folder.is_dir() else None


def default_folder(fallback: Path) -> Path:
    """Return the stable default folder, migrating older settings once."""
    settings = _read_settings()
    saved_default = _valid_folder(settings.get(SETTINGS_KEY_DEFAULT))
    if saved_default:
        return saved_default

    # Older versions only stored lastFolder. Treat that value as the initial
    # default so an existing installation keeps its configured L4D2 folder.
    migrated = _valid_folder(settings.get(SETTINGS_KEY_LAST))
    if migrated:
        save_settings(migrated, migrated)
        return migrated

    return fallback.resolve()


def load_last_folder(fallback: Path) -> Path:
    stable_default = default_folder(fallback)
    settings = _read_settings()
    saved = _valid_folder(settings.get(SETTINGS_KEY_LAST))
    if saved:
        return saved
    return stable_default


def save_settings(default: Path, last: Path) -> None:
    target = settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    settings = _read_settings()
    settings[SETTINGS_KEY_DEFAULT] = str(default.resolve())
    settings[SETTINGS_KEY_LAST] = str(last.resolve())
    target.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_last_folder(folder: Path) -> None:
    settings = _read_settings()
    saved_default = _valid_folder(settings.get(SETTINGS_KEY_DEFAULT))
    save_settings(saved_default or folder, folder)


def deepseek_config() -> tuple[str, str]:
    settings = _read_settings()
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        api_key = str(settings.get(SETTINGS_KEY_DEEPSEEK_API_KEY, "")).strip()
    model = str(settings.get(SETTINGS_KEY_DEEPSEEK_MODEL, DEFAULT_DEEPSEEK_MODEL)).strip()
    return api_key, model or DEFAULT_DEEPSEEK_MODEL


def save_deepseek_config(api_key: str | None, model: str) -> None:
    target = settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    settings = _read_settings()
    if api_key is not None and api_key:
        settings[SETTINGS_KEY_DEEPSEEK_API_KEY] = api_key
    elif api_key is not None:
        settings.pop(SETTINGS_KEY_DEEPSEEK_API_KEY, None)
    settings[SETTINGS_KEY_DEEPSEEK_MODEL] = model
    target.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def load_ai_prompts() -> list[dict[str, str]]:
    prompts = _read_settings().get(SETTINGS_KEY_AI_PROMPTS, [])
    if not isinstance(prompts, list):
        return []
    return [
        {
            "id": str(item.get("id", "")),
            "name": str(item.get("name", "")).strip(),
            "prompt": str(item.get("prompt", "")).strip(),
        }
        for item in prompts
        if isinstance(item, dict)
        and str(item.get("id", "")).strip()
        and str(item.get("name", "")).strip()
        and str(item.get("prompt", "")).strip()
    ]


def save_ai_prompts(prompts: list[dict[str, str]]) -> None:
    target = settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    settings = _read_settings()
    settings[SETTINGS_KEY_AI_PROMPTS] = prompts
    target.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def ai_history_path() -> Path:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.cwd()))
    return local_app_data / "L4D2ModManager" / "ai_history.json"


def load_ai_history(mod_id: str) -> list[dict]:
    try:
        payload = json.loads(ai_history_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = payload.get(mod_id, []) if isinstance(payload, dict) else []
    return entries if isinstance(entries, list) else []


def save_ai_history(mod_id: str, entries: list[dict]) -> None:
    target = ai_history_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload[mod_id] = entries[:50]
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def move_ai_history(old_id: str, new_id: str) -> None:
    if old_id == new_id:
        return
    entries = load_ai_history(old_id)
    if not entries:
        return
    existing = load_ai_history(new_id)
    save_ai_history(new_id, (entries + existing)[:50])
    delete_ai_history(old_id)


def delete_ai_history(mod_id: str) -> None:
    target = ai_history_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict) or mod_id not in payload:
        return
    payload.pop(mod_id, None)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_path(root: Path, relative_path: str) -> Path:
    candidate = (root / Path(relative_path.replace("\\", "/"))).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("archive contains a path outside the Mod folder")
    return candidate


def move_to_recycle_bin(paths: list[Path]) -> None:
    """Move files to the Windows Recycle Bin without permanently deleting them."""
    files = [path for path in paths if path.is_file()]
    if not files:
        return
    if os.name != "nt":
        raise OSError("当前系统不支持回收站删除")

    class SHFileOpStructW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", wintypes.UINT),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    source = "".join(f"{path}\0" for path in files) + "\0"
    operation = SHFileOpStructW(
        hwnd=None,
        wFunc=3,  # FO_DELETE
        pFrom=source,
        pTo=None,
        fFlags=0x0040 | 0x0010 | 0x0004 | 0x0400,  # allow undo, quiet, no UI
        fAnyOperationsAborted=False,
        hNameMappings=None,
        lpszProgressTitle=None,
    )
    shell32 = ctypes.windll.shell32
    shell32.SHFileOperationW.argtypes = [ctypes.POINTER(SHFileOpStructW)]
    shell32.SHFileOperationW.restype = ctypes.c_int
    result = shell32.SHFileOperationW(ctypes.byref(operation))
    if result:
        raise OSError(result, "无法将文件移入回收站")
    if operation.fAnyOperationsAborted:
        raise OSError("回收站删除已取消")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def vpk_file_details(root: Path, mod: dict) -> list[dict]:
    details: list[dict] = []
    groups: dict[str, list[dict]] = {}
    for relative_path in mod.get("vpkFiles", []):
        target = _safe_path(root, relative_path)
        if not target.is_file():
            continue
        info = {
            "path": relative_path,
            "name": target.name,
            "size": target.stat().st_size,
            "duplicate": False,
            "duplicatePaths": [],
        }
        details.append(info)
        groups.setdefault(file_sha256(target), []).append(info)
    for items in groups.values():
        if len(items) < 2:
            continue
        paths = [item["path"] for item in items]
        for item in items:
            item["duplicate"] = True
            item["duplicatePaths"] = [path for path in paths if path != item["path"]]
    return details


def _copy_archive_file(source, target: Path) -> bool:
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as destination:
        shutil.copyfileobj(source, destination)
    return True


def _relative_name(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def scan_workshop_mods(root: Path) -> dict:
    """Find Workshop VPKs that are not already copied into the workspace."""
    workshop_root = (root / "workshop").resolve()
    if not workshop_root.is_dir():
        return {"available": False, "path": str(workshop_root), "mods": []}

    existing_names = {
        path.name.casefold()
        for path in root.rglob("*")
        if path.is_file()
        and workshop_root not in path.resolve().parents
    }
    mods: list[dict] = []
    source_vpks = sorted(
        path
        for path in workshop_root.rglob("*")
        if path.is_file()
        and path.suffix.casefold() in VPK_EXTENSIONS
        and workshop_root in path.resolve().parents
    )
    for vpk_path in source_vpks:
        target_names = {vpk_path.name.casefold()}
        if vpk_path.suffix.casefold() == ".vpk":
            target_names.add(vpk_path.with_suffix(".vpk1").name.casefold())
        if target_names & existing_names:
            continue
        siblings = sorted(
            path
            for path in vpk_path.parent.iterdir()
            if path.is_file()
            and path.stem.casefold() == vpk_path.stem.casefold()
            and path.suffix.casefold() in IMAGE_EXTENSIONS
        )
        source_files = [vpk_path, *siblings]
        relative_vpk = _relative_name(workshop_root, vpk_path)
        mods.append(
            {
                "id": relative_vpk,
                "name": vpk_path.stem,
                "vpkCount": 1,
                "previewCount": len(siblings),
                "files": [
                    {
                        "path": _relative_name(root, path),
                        "name": path.name,
                        "kind": "vpk" if path.suffix.casefold() in VPK_EXTENSIONS else "preview",
                        "size": path.stat().st_size,
                    }
                    for path in source_files
                ],
            }
        )
    return {"available": True, "path": str(workshop_root), "mods": mods}


def copy_workshop_mods(root: Path, mod_ids: list[str]) -> dict:
    scan = scan_workshop_mods(root)
    by_id = {item["id"]: item for item in scan["mods"]}
    imported: list[str] = []
    skipped: list[str] = []
    conflicts: list[str] = []
    missing: list[str] = [mod_id for mod_id in mod_ids if mod_id not in by_id]
    workshop_root = (root / "workshop").resolve()
    for mod_id in dict.fromkeys(mod_ids):
        mod = by_id.get(mod_id)
        if not mod:
            continue
        for item in mod["files"]:
            source = _safe_path(root, item["path"])
            if workshop_root not in source.resolve().parents or not source.is_file():
                missing.append(item["path"])
                continue
            target = (root / source.name).resolve()
            if target.exists():
                if file_sha256(source) == file_sha256(target):
                    skipped.append(item["name"])
                else:
                    conflicts.append(item["name"])
                continue
            shutil.copy2(source, target)
            imported.append(item["name"])
    return {
        "imported": imported,
        "skipped": skipped,
        "conflicts": conflicts,
        "missing": missing,
    }


def _extract_zip(archive: Path, root: Path) -> tuple[list[str], list[str]]:
    imported: list[str] = []
    conflicts: list[str] = []
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            target = _safe_path(root, member.filename)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            with package.open(member) as source:
                if _copy_archive_file(source, target):
                    imported.append(_relative_name(root, target))
                else:
                    conflicts.append(_relative_name(root, target))
    return imported, conflicts


def _extract_tar(archive: Path, root: Path) -> tuple[list[str], list[str]]:
    imported: list[str] = []
    conflicts: list[str] = []
    with tarfile.open(archive, mode="r:*") as package:
        for member in package.getmembers():
            target = _safe_path(root, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ValueError("archive contains an unsupported link or special file")
            source = package.extractfile(member)
            if source is None:
                continue
            with source:
                if _copy_archive_file(source, target):
                    imported.append(_relative_name(root, target))
                else:
                    conflicts.append(_relative_name(root, target))
    return imported, conflicts


def extract_archive(archive: Path, root: Path) -> dict:
    suffix = archive.suffix.casefold()
    if suffix == ".zip":
        imported, conflicts = _extract_zip(archive, root)
    elif suffix in {".tar", ".gz", ".tgz", ".bz2", ".xz"}:
        imported, conflicts = _extract_tar(archive, root)
    elif suffix in {".7z", ".rar"}:
        raise ValueError("当前环境没有可用的 7z/RAR 解压工具，请先安装 7-Zip")
    else:
        raise ValueError("不支持的压缩包格式")
    return {"imported": imported, "conflicts": conflicts}


def _find_mod(root: Path, mod_id: str, catalog: list[dict] | None = None) -> dict | None:
    catalog = catalog if catalog is not None else build_catalog(root)
    return next((mod for mod in catalog if mod["id"] == mod_id), None)


def _update_cached_vpk_states(catalog: list[dict], disabled_paths: list[str]) -> None:
    """Reflect VPK renames in the cached catalog without rescanning contents."""

    disabled = {
        str(path).replace("\\", "/").casefold()
        for path in disabled_paths
    }
    for mod in catalog:
        updated_files = []
        changed = False
        for relative in mod.get("vpkFiles", []):
            normalized = str(relative).replace("\\", "/")
            if normalized.casefold() in disabled and Path(normalized).suffix.casefold() == ".vpk":
                normalized = f"{normalized[:-4]}.vpk1"
                changed = True
            updated_files.append(normalized)
        if not changed:
            continue
        mod["vpkFiles"] = updated_files
        states = {Path(path).suffix.casefold() == ".vpk" for path in updated_files}
        mod["enabled"] = states == {True}
        mod["partiallyEnabled"] = len(states) > 1


def _validate_mod_name(name: str) -> str:
    name = name.strip()
    invalid_characters = '<>:"/\\|?*'
    reserved_names = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if not name or len(name) > 80:
        raise ValueError("名称不能为空，且不能超过 80 个字符")
    if name in {".", ".."} or any(character in name for character in invalid_characters):
        raise ValueError("名称包含 Windows 不允许的文件名字符")
    if name.endswith((".", " ")) or name.upper() in reserved_names:
        raise ValueError("名称不能作为 Windows 文件名使用")
    return name


def _validate_tag_key(key: str) -> str:
    key = key.strip()
    if not key or len(key) > 120 or any(character in key for character in '<>"/\\|?*'):
        raise ValueError("标签标识无效")
    return key


def _validate_tag_label(label: str) -> str:
    label = label.strip()
    if len(label) > 80:
        raise ValueError("标签不能超过 80 个字符")
    return label


def _ai_context(mod: dict) -> dict:
    detections = []
    for detection in mod.get("detections", []):
        detections.append(
            {
                "file": detection.get("name"),
                "addonTitle": detection.get("addonTitle"),
                "categories": detection.get("categories", []),
                "weaponTargets": detection.get("weaponTargets", []),
                "characterTargets": detection.get("characterTargets", []),
                "signals": detection.get("signals", {}),
            }
        )
    return {
        "name": mod.get("name"),
        "vpkFiles": mod.get("vpkFiles", []),
        "preview": mod.get("preview"),
        "categories": mod.get("categories", []),
        "primaryCategories": mod.get("primaryCategories", []),
        "weaponTargets": mod.get("weaponTargets", []),
        "characterTargets": mod.get("characterTargets", []),
        "detections": detections,
    }


def deepseek_analyze(
    mod: dict,
    api_key: str,
    model: str,
    instruction: str = DEFAULT_AI_PROMPT,
) -> str:
    context = json.dumps(_ai_context(mod), ensure_ascii=False, indent=2)
    prompt = (
        f"{instruction.strip()}\n\n"
        f"Mod 检测数据：\n{context}"
    )
    payload = json.dumps(
        {
            "model": model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个谨慎的 L4D2 Mod 文件分析助手，只根据证据作答。",
                },
                {"role": "user", "content": prompt},
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        try:
            details = json.loads(details).get("error", {}).get("message", details)
        except json.JSONDecodeError:
            pass
        raise ValueError(f"DeepSeek 请求失败（HTTP {error.code}）：{details}") from error
    except urllib.error.URLError as error:
        raise ValueError(f"无法连接 DeepSeek：{error.reason}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"DeepSeek 响应读取失败：{error}") from error

    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("DeepSeek 返回了无法识别的结果") from error
    if not isinstance(content, str) or not content.strip():
        raise ValueError("DeepSeek 返回了空分析结果")
    return content.strip()


def _natural_path_key(value: str) -> list[object]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value)]


def toggle_mod_enabled(root: Path, mod: dict, enabled: bool) -> list[str]:
    """Switch every VPK in a Mod between .vpk (enabled) and .vpk1 (disabled)."""
    vpk_files = [
        relative
        for relative in mod.get("vpkFiles", [])
        if Path(relative).suffix.casefold() in VPK_EXTENSIONS
    ]
    if not vpk_files:
        raise ValueError("这个 Mod 没有可切换的 VPK 文件")

    source_targets: list[tuple[Path, Path]] = []
    target_suffix = ".vpk" if enabled else ".vpk1"
    for relative_path in sorted(vpk_files, key=_natural_path_key):
        source = _safe_path(root, relative_path)
        destination = source.with_suffix(target_suffix)
        source_targets.append((source, destination))

    source_paths = {source.resolve() for source, _ in source_targets}
    destination_paths: set[Path] = set()
    for source, destination in source_targets:
        destination = destination.resolve()
        if destination in destination_paths:
            raise ValueError("切换后会产生重复文件")
        destination_paths.add(destination)
        if destination != source.resolve() and destination.exists() and destination not in source_paths:
            raise ValueError(f"目标文件已存在：{destination.name}")

    pending = [(source, destination) for source, destination in source_targets if source.resolve() != destination.resolve()]
    temporary_pairs: list[tuple[Path, Path, Path]] = []
    try:
        for source, destination in pending:
            temporary = source.with_name(f".{source.name}.toggle-{uuid.uuid4().hex}.tmp")
            source.rename(temporary)
            temporary_pairs.append((source, temporary, destination))
        for source, temporary, destination in temporary_pairs:
            temporary.rename(destination)
    except OSError:
        for source, temporary, _ in reversed(temporary_pairs):
            if temporary.exists() and not source.exists():
                temporary.rename(source)
        raise
    return [destination.relative_to(root).as_posix() for _, destination in source_targets]


def rename_mod_files(root: Path, mod: dict, name: str) -> list[str]:
    """Rename a Mod's VPK/image files while preserving split-file suffixes."""

    old_stem = str(mod.get("originalName", ""))
    source_targets: list[tuple[Path, Path]] = []
    vpk_files = sorted(mod.get("vpkFiles", []), key=_natural_path_key)
    multiple_vpks = len(vpk_files) > 1
    for index, relative_path in enumerate(vpk_files, start=1):
        source = _safe_path(root, relative_path)
        part_name = f"{name}{index}" if multiple_vpks else name
        source_targets.append((source, source.with_name(f"{part_name}{source.suffix}")))
    preview_files = list(mod.get("previewFiles", []))
    if not preview_files and mod.get("preview"):
        preview_files = [mod["preview"]]
    multiple_previews = len(preview_files) > 1
    for index, relative_path in enumerate(preview_files, start=1):
        source = _safe_path(root, relative_path)
        part_name = f"{name}{index}" if multiple_previews else name
        source_targets.append((source, source.with_name(f"{part_name}{source.suffix}")))

    source_paths = {source.resolve() for source, _ in source_targets}
    destination_paths: set[Path] = set()
    for source, destination in source_targets:
        destination = destination.resolve()
        if destination in destination_paths:
            raise ValueError("新的文件名会产生重复文件")
        destination_paths.add(destination)
        if destination != source.resolve() and destination.exists() and destination not in source_paths:
            raise ValueError(f"目标文件已存在：{destination.name}")

    pending = [(source, destination) for source, destination in source_targets if source.resolve() != destination.resolve()]
    temporary_pairs: list[tuple[Path, Path, Path]] = []
    try:
        for source, destination in pending:
            temporary = source.with_name(f".{source.name}.rename-{uuid.uuid4().hex}.tmp")
            source.rename(temporary)
            temporary_pairs.append((source, temporary, destination))
        for source, temporary, destination in temporary_pairs:
            temporary.rename(destination)
    except OSError:
        for source, temporary, _ in reversed(temporary_pairs):
            if temporary.exists() and not source.exists():
                temporary.rename(source)
        raise
    return [destination.relative_to(root).as_posix() for _, destination in source_targets]


class ModRequestHandler(SimpleHTTPRequestHandler):
    root: Path

    def __init__(self, *args, **kwargs):
        server = args[2] if len(args) > 2 else kwargs.get("server")
        static_root = getattr(server, "static_root", resource_root())
        super().__init__(*args, directory=str(static_root), **kwargs)

    @property
    def mod_root(self) -> Path:
        return getattr(self.server, "mod_root", self.root)

    @property
    def static_root(self) -> Path:
        return getattr(self.server, "static_root", Path(__file__).parent.resolve())

    def _catalog(self, refresh: bool = False) -> list[dict]:
        ensure_manager_data_layout(self.mod_root)
        cached = getattr(self.server, "catalog_cache", None)
        if refresh or cached is None:
            cached = build_catalog(self.mod_root)
            installations = {
                str(item.get("modId")): item
                for item in load_voice_installations(self.mod_root)
            }
            for mod in cached:
                if "voice_replacement" not in mod.get("primaryCategories", []):
                    continue
                record = installations.get(str(mod.get("id")))
                mod["voiceInstalled"] = record is not None
                mod["voiceInstallationId"] = record.get("id") if record else None
            self.server.catalog_cache = cached
        return cached

    def _invalidate_catalog(self) -> None:
        self.server.catalog_cache = None
        self.server.spray_assets_cache = None

    def _spray_index(self, refresh: bool = False) -> dict:
        cached = getattr(self.server, "spray_assets_cache", None)
        if refresh or cached is None:
            cached = list_spray_assets(self.mod_root, self._catalog(refresh=refresh))
            self.server.spray_assets_cache = cached
        return cached

    def _sync_cached_mod_tags(self) -> None:
        """Update tag fields in the existing catalog without rescanning VPKs."""
        cached = getattr(self.server, "catalog_cache", None)
        if cached is None:
            return
        custom_tags = load_custom_tags(self.mod_root)
        marked_tags = load_marked_tags(self.mod_root)
        hidden_tags = load_hidden_tags(self.mod_root)
        for mod in cached:
            values = custom_tags.get(mod["id"], {})
            mod["tagOverrides"] = {
                key: label for key, label in values.items() if not key.startswith("custom:")
            }
            mod["customTags"] = [
                {
                    "id": key.removeprefix("custom:"),
                    "label": label,
                    "marked": key in marked_tags.get(mod["id"], {}),
                }
                for key, label in values.items()
                if key.startswith("custom:")
            ]
            mod["hiddenTags"] = hidden_tags.get(mod["id"], {})

    def _serve_mod_file(self, request_path: str) -> None:
        relative_path = unquote(request_path.removeprefix("/files/"))
        try:
            target = _safe_path(self.mod_root, relative_path)
        except ValueError:
            self.send_error(403, "Invalid file path")
            return
        if not target.is_file():
            self.send_error(404, "File not found")
            return
        content_type = self.extensions_map.get(target.suffix, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(target.stat().st_size))
        self.end_headers()
        with target.open("rb") as source:
            shutil.copyfileobj(source, self.wfile)

    def do_GET(self) -> None:
        request_path = urlsplit(self.path).path
        if request_path == "/api/source-version":
            payload = json.dumps(
                {"version": source_version(self.static_root)},
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if request_path == "/api/ai/config":
            api_key, model = deepseek_config()
            payload = json.dumps(
                {"configured": bool(api_key), "provider": "DeepSeek", "model": model},
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if request_path == "/api/ai/prompts":
            self._send_json(
                200,
                {
                    "default": {"id": "default", "name": "默认 Mod 分析", "prompt": DEFAULT_AI_PROMPT},
                    "custom": load_ai_prompts(),
                },
            )
            return
        if request_path == "/api/mod/ai-history":
            mod_id = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
            self._send_json(200, {"history": load_ai_history(mod_id)})
            return
        if request_path == "/api/mod/file-details":
            mod_id = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
            mod = _find_mod(self.mod_root, mod_id, self._catalog())
            if not mod:
                self._send_json(404, {"error": "找不到这个 Mod"})
                return
            self._send_json(200, {"id": mod_id, "files": vpk_file_details(self.mod_root, mod)})
            return
        if request_path == "/api/mod/nekovpk":
            mod_id = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
            mod = _find_mod(self.mod_root, mod_id, self._catalog())
            if not mod:
                self._send_json(404, {"error": "找不到这个 Mod"})
                return
            info = mod.get("nekovpk")
            if not isinstance(info, dict) or not info.get("vpkPath"):
                self._send_json(400, {"error": "这个 Mod 不是可配置的 NekoVPK"})
                return
            self._send_json(200, info)
            return
        if request_path == "/api/mod/voice":
            mod_id = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
            mod = _find_mod(self.mod_root, mod_id, self._catalog())
            if not mod:
                self._send_json(404, {"error": "找不到这个 Mod"})
                return
            try:
                self._send_json(200, inspect_voice_package(self.mod_root, mod))
            except VoiceReplacementError as error:
                self._send_json(400, {"error": str(error)})
            return
        if request_path == "/api/spray/assets":
            try:
                refresh = "refresh" in parse_qs(urlsplit(self.path).query)
                self._send_json(200, self._spray_index(refresh=refresh))
            except SprayError as error:
                self._send_json(400, {"error": str(error)})
            return
        if request_path == "/api/spray/preview":
            query = parse_qs(urlsplit(self.path).query)
            asset_id = query.get("asset", [""])[0]
            try:
                asset = next(
                    (item for item in self._spray_index().get("assets", []) if item.get("id") == asset_id),
                    None,
                )
                if asset is None:
                    raise SprayError("找不到这个喷漆资源，请先刷新喷漆列表")
                frame_value = query.get("frame", [None])[0]
                if frame_value is not None and asset.get("sourceType") == "imported":
                    content = spray_preview_frame(self.mod_root, asset, int(frame_value))
                else:
                    content = spray_preview_asset(self.mod_root, asset)
            except SprayError as error:
                self._send_json(400, {"error": str(error)})
                return
            except ValueError:
                self._send_json(400, {"error": "预览帧编号无效"})
                return
            self.send_response(200)
            content_type = "image/gif" if asset.get("sourceType") == "imported" and str(asset.get("filename", "")).casefold().endswith(".gif") else "image/png"
            if frame_value is not None:
                content_type = "image/png"
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        if request_path == "/api/catalog":
            refresh = "refresh" in parse_qs(urlsplit(self.path).query)
            payload = json.dumps(
                {
                    "root": str(self.mod_root),
                    "defaultRoot": str(default_folder(Path.cwd())),
                    "mods": self._catalog(refresh),
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if request_path == "/api/workshop/scan":
            self._send_json(200, scan_workshop_mods(self.mod_root))
            return
        if request_path.startswith("/files/"):
            self._serve_mod_file(request_path)
            return
        super().do_GET()

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_POST(self) -> None:
        route = urlsplit(self.path).path
        try:
            if route == "/api/ai/config":
                payload = self._read_json()
                raw_api_key = payload.get("apiKey") if "apiKey" in payload else None
                api_key = None if raw_api_key is None else str(raw_api_key).strip()
                if api_key is not None and len(api_key) > 300:
                    raise ValueError("DeepSeek API Key 格式无效")
                model = str(payload.get("model", DEFAULT_DEEPSEEK_MODEL)).strip()
                if model not in DEEPSEEK_MODELS:
                    raise ValueError("暂不支持这个 DeepSeek 模型")
                current_key, _ = deepseek_config()
                save_deepseek_config(api_key, model)
                self._send_json(200, {"ok": True, "configured": bool(api_key or current_key), "model": model})
                return

            if route == "/api/mod/ai-analyze":
                payload = self._read_json()
                mod = _find_mod(self.mod_root, str(payload.get("id", "")), self._catalog())
                if not mod:
                    self._send_json(404, {"error": "找不到这个 Mod"})
                    return
                api_key, model = deepseek_config()
                if not api_key:
                    self._send_json(400, {"error": "请先配置 DeepSeek API Key"})
                    return
                prompt = str(payload.get("prompt", DEFAULT_AI_PROMPT)).strip()
                if not prompt:
                    raise ValueError("分析提示词不能为空")
                if len(prompt) > 12000:
                    raise ValueError("分析提示词不能超过 12000 个字符")
                analysis = deepseek_analyze(mod, api_key, model, prompt)
                history_entry = {
                    "id": uuid.uuid4().hex,
                    "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "model": model,
                    "promptId": str(payload.get("promptId", "default")),
                    "promptName": str(payload.get("promptName", "默认 Mod 分析")),
                    "prompt": prompt,
                    "analysis": analysis,
                }
                save_ai_history(mod["id"], [history_entry, *load_ai_history(mod["id"])])
                self._send_json(200, {"ok": True, "entry": history_entry})
                return

            if route == "/api/ai/prompts/save":
                payload = self._read_json()
                prompt_id = str(payload.get("id", "")).strip()
                name = str(payload.get("name", "")).strip()
                prompt = str(payload.get("prompt", "")).strip()
                if prompt_id == "default":
                    raise ValueError("默认提示词不能覆盖，请另存为自定义提示词")
                if not prompt_id:
                    prompt_id = f"prompt-{uuid.uuid4().hex}"
                if not name or len(name) > 60:
                    raise ValueError("提示词名称不能为空，且不能超过 60 个字符")
                if not prompt or len(prompt) > 12000:
                    raise ValueError("提示词不能为空，且不能超过 12000 个字符")
                prompts = load_ai_prompts()
                updated = {"id": prompt_id, "name": name, "prompt": prompt}
                found = False
                for index, item in enumerate(prompts):
                    if item["id"] == prompt_id:
                        prompts[index] = updated
                        found = True
                        break
                if not found:
                    prompts.append(updated)
                save_ai_prompts(prompts)
                self._send_json(200, {"ok": True, "prompt": updated, "custom": prompts})
                return

            if route == "/api/ai/prompts/delete":
                payload = self._read_json()
                prompt_id = str(payload.get("id", "")).strip()
                if not prompt_id or prompt_id == "default":
                    raise ValueError("不能删除默认提示词")
                prompts = [item for item in load_ai_prompts() if item["id"] != prompt_id]
                save_ai_prompts(prompts)
                self._send_json(200, {"ok": True, "custom": prompts})
                return

            if route == "/api/mod/rename":
                payload = self._read_json()
                mod_id = str(payload.get("id", ""))
                name = _validate_mod_name(str(payload.get("name", "")))
                mod = _find_mod(self.mod_root, mod_id, self._catalog())
                if not mod:
                    self._send_json(404, {"error": "找不到这个 Mod"})
                    return
                renamed = rename_mod_files(self.mod_root, mod, name)
                names = load_custom_names(self.mod_root)
                names.pop(mod_id, None)
                if mod_id.startswith("series"):
                    names[mod_id] = name
                save_custom_names(self.mod_root, names)
                tags = load_custom_tags(self.mod_root)
                mod_tags = tags.pop(mod_id, None)
                hidden = load_hidden_tags(self.mod_root)
                hidden_tags = hidden.pop(mod_id, None)
                marked = load_marked_tags(self.mod_root)
                marked_tags = marked.pop(mod_id, None)
                has_history = bool(load_ai_history(mod_id))
                renamed_vpks = {
                    relative for relative in renamed
                    if Path(relative).suffix.casefold() in VPK_EXTENSIONS
                }
                renamed_mod = None
                if renamed_vpks and (mod_tags or hidden_tags or has_history):
                    renamed_mod = next(
                        (
                            candidate
                            for candidate in self._catalog(refresh=True)
                            if set(candidate.get("vpkFiles", [])) == renamed_vpks
                        ),
                        None,
                    )
                renamed_id = renamed_mod["id"] if renamed_mod else mod_id
                if not renamed_mod and renamed_vpks and not mod_id.startswith("series"):
                    renamed_id = _key(Path(sorted(renamed_vpks)[0]).stem)
                if mod_tags:
                    tags[renamed_id] = mod_tags
                    save_custom_tags(self.mod_root, tags)
                if hidden_tags:
                    hidden[renamed_id] = hidden_tags
                    save_hidden_tags(self.mod_root, hidden)
                if marked_tags:
                    marked[renamed_id] = marked_tags
                    save_marked_tags(self.mod_root, marked)
                move_ai_history(mod_id, renamed_id)
                self._invalidate_catalog()
                self._send_json(200, {"ok": True, "id": renamed_id, "name": name, "renamed": renamed})
                return

            if route == "/api/mod/toggle":
                payload = self._read_json()
                mod_id = str(payload.get("id", ""))
                enabled = payload.get("enabled")
                if not isinstance(enabled, bool):
                    raise ValueError("启用状态无效")
                mod = _find_mod(self.mod_root, mod_id, self._catalog())
                if not mod:
                    self._send_json(404, {"error": "找不到这个 Mod"})
                    return
                renamed = toggle_mod_enabled(self.mod_root, mod, enabled)
                self._invalidate_catalog()
                self._send_json(200, {"ok": True, "id": mod_id, "enabled": enabled, "renamed": renamed})
                return

            if route == "/api/spray/apply":
                payload = self._read_json()
                assignments = payload.get("assignments")
                if not isinstance(assignments, dict):
                    raise ValueError("喷漆槽位配置无效")
                catalog = self._catalog()
                result = apply_spray_collection(
                    self.mod_root,
                    catalog,
                    assignments,
                    toggle_callback=toggle_mod_enabled,
                )
                _update_cached_vpk_states(catalog, result.get("disabledVpkFiles", []))
                self.server.catalog_cache = catalog
                self.server.spray_assets_cache = None
                self._send_json(200, {"ok": True, **result})
                return

            if route == "/api/spray/import":
                payload = self._read_json()
                result = import_spray_images(self.mod_root, payload.get("images"))
                self._invalidate_catalog()
                self._send_json(200, {"ok": True, **result})
                return

            if route == "/api/spray/config":
                payload = self._read_json()
                asset_id = str(payload.get("assetId", "")).strip()
                if not asset_id:
                    raise ValueError("缺少喷漆素材")
                result = save_spray_configuration(
                    self.mod_root,
                    asset_id,
                    payload.get("configuration"),
                )
                self.server.spray_assets_cache = None
                self._send_json(200, {"ok": True, **result})
                return

            if route == "/api/spray/delete":
                payload = self._read_json()
                asset_id = str(payload.get("assetId", "")).strip()
                result = delete_imported_spray(
                    self.mod_root,
                    asset_id,
                    recycle_callback=move_to_recycle_bin,
                )
                self._invalidate_catalog()
                self._send_json(200, {"ok": True, **result})
                return

            if route == "/api/spray/reset":
                reset_spray_state(self.mod_root)
                self._invalidate_catalog()
                self._send_json(200, {"ok": True})
                return

            if route == "/api/mod/nekovpk/convert":
                payload = self._read_json()
                mod_id = str(payload.get("id", ""))
                target = str(payload.get("target", "")).strip().casefold()
                mod = _find_mod(self.mod_root, mod_id, self._catalog())
                if not mod:
                    self._send_json(404, {"error": "找不到这个 Mod"})
                    return
                info = mod.get("nekovpk")
                if not isinstance(info, dict) or not info.get("vpkPath"):
                    raise ValueError("这个 Mod 不是可配置的 NekoVPK")
                relative_path = str(info["vpkPath"])
                if relative_path not in mod.get("vpkFiles", []):
                    raise ValueError("NekoVPK 文件已发生变化，请刷新目录后重试")
                vpk_path = _safe_path(self.mod_root, relative_path)
                result = convert_nekovpk_target(vpk_path, target)
                self._invalidate_catalog()
                refreshed = self._catalog(refresh=True)
                updated = _find_mod(self.mod_root, mod_id, refreshed)
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "id": mod_id,
                        "result": result,
                        "nekovpk": updated.get("nekovpk") if updated else None,
                    },
                )
                return

            if route == "/api/mod/nekovpk/map":
                payload = self._read_json()
                mod_id = str(payload.get("id", ""))
                target = str(payload.get("target", "")).strip().casefold()
                mod = _find_mod(self.mod_root, mod_id, self._catalog())
                if not mod:
                    self._send_json(404, {"error": "找不到这个 Mod"})
                    return
                info = mod.get("nekovpk")
                if not isinstance(info, dict) or not info.get("vpkPath"):
                    raise ValueError("这个 Mod 不是可配置的 NekoVPK")
                relative_path = str(info["vpkPath"])
                if relative_path not in mod.get("vpkFiles", []):
                    raise ValueError("NekoVPK 文件已发生变化，请刷新目录后重试")
                vpk_path = _safe_path(self.mod_root, relative_path)
                result = map_nekovpk_target(vpk_path, target)
                self._invalidate_catalog()
                refreshed = self._catalog(refresh=True)
                updated = _find_mod(self.mod_root, mod_id, refreshed)
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "id": mod_id,
                        "result": result,
                        "nekovpk": updated.get("nekovpk") if updated else None,
                    },
                )
                return

            if route in {"/api/mod/voice/install", "/api/mod/voice/restore"}:
                payload = self._read_json()
                mod_id = str(payload.get("id", ""))
                mod = _find_mod(self.mod_root, mod_id, self._catalog())
                if not mod:
                    self._send_json(404, {"error": "找不到这个 Mod"})
                    return
                if route.endswith("/restore"):
                    result = restore_voice_package(self.mod_root, mod_id)
                else:
                    result = install_voice_package(
                        self.mod_root,
                        mod,
                        replace_existing=payload.get("replaceExisting") is True,
                    )
                self._invalidate_catalog()
                self._send_json(200, {"ok": True, **result})
                return

            if route == "/api/mod/bulk":
                payload = self._read_json()
                action = str(payload.get("action", "")).strip().casefold()
                raw_ids = payload.get("ids", [])
                if action not in {"enable", "disable", "delete"}:
                    raise ValueError("批量操作无效")
                if not isinstance(raw_ids, list) or not raw_ids:
                    raise ValueError("请至少选择一个 Mod")
                ids = list(dict.fromkeys(str(mod_id) for mod_id in raw_ids if str(mod_id)))
                catalog = self._catalog()
                catalog_by_id = {mod["id"]: mod for mod in catalog}
                missing_ids = [mod_id for mod_id in ids if mod_id not in catalog_by_id]
                if missing_ids:
                    self._send_json(404, {"error": "部分 Mod 已不存在，请刷新目录后重试"})
                    return
                mods = [catalog_by_id[mod_id] for mod_id in ids]

                if action in {"enable", "disable"}:
                    enabled = action == "enable"
                    processed: list[str] = []
                    skipped: list[str] = []
                    for mod in mods:
                        if not mod.get("vpkFiles"):
                            skipped.append(mod["id"])
                            continue
                        toggle_mod_enabled(self.mod_root, mod, enabled)
                        processed.append(mod["id"])
                    self._invalidate_catalog()
                    self._send_json(200, {
                        "ok": True,
                        "action": action,
                        "processed": processed,
                        "skipped": skipped,
                    })
                    return

                relative_paths: list[str] = []
                targets: list[Path] = []
                seen_targets: set[Path] = set()
                for mod in mods:
                    preview_files = mod.get("previewFiles", []) or ([mod.get("preview")] if mod.get("preview") else [])
                    for relative_path in dict.fromkeys([*mod.get("vpkFiles", []), *preview_files]):
                        if not relative_path:
                            continue
                        target = _safe_path(self.mod_root, relative_path)
                        if target.is_file() and target.resolve() not in seen_targets:
                            seen_targets.add(target.resolve())
                            targets.append(target)
                            relative_paths.append(relative_path)
                move_to_recycle_bin(targets)
                self._invalidate_catalog()
                self._send_json(200, {
                    "ok": True,
                    "action": action,
                    "processed": [mod["id"] for mod in mods],
                    "removed": relative_paths,
                    "recycled": True,
                })
                return

            if route == "/api/mod/tag":
                payload = self._read_json()
                mod_id = str(payload.get("id", ""))
                key = _validate_tag_key(str(payload.get("key", "")))
                label = _validate_tag_label(str(payload.get("label", "")))
                if not _find_mod(self.mod_root, mod_id, self._catalog()):
                    self._send_json(404, {"error": "找不到这个 Mod"})
                    return
                tags = load_custom_tags(self.mod_root)
                mod_tags = tags.setdefault(mod_id, {})
                if label:
                    mod_tags[key] = label
                else:
                    mod_tags.pop(key, None)
                    if key.startswith("custom:"):
                        marked = load_marked_tags(self.mod_root)
                        mod_marked = marked.get(mod_id, {})
                        mod_marked.pop(key, None)
                        if mod_marked:
                            marked[mod_id] = mod_marked
                        else:
                            marked.pop(mod_id, None)
                        save_marked_tags(self.mod_root, marked)
                if not mod_tags:
                    tags.pop(mod_id, None)
                save_custom_tags(self.mod_root, tags)
                self._sync_cached_mod_tags()
                self._send_json(200, {"ok": True, "key": key, "label": label})
                return

            if route == "/api/mod/tag/add":
                payload = self._read_json()
                mod_id = str(payload.get("id", ""))
                label = _validate_tag_label(str(payload.get("label", "")))
                if not label:
                    raise ValueError("标签不能为空")
                if not _find_mod(self.mod_root, mod_id, self._catalog()):
                    self._send_json(404, {"error": "找不到这个 Mod"})
                    return
                tags = load_custom_tags(self.mod_root)
                key = f"custom:{uuid.uuid4().hex}"
                tags.setdefault(mod_id, {})[key] = label
                save_custom_tags(self.mod_root, tags)
                self._sync_cached_mod_tags()
                self._send_json(200, {"ok": True, "key": key, "label": label})
                return

            if route == "/api/mod/tag/mark":
                payload = self._read_json()
                mod_id = str(payload.get("id", ""))
                key = _validate_tag_key(str(payload.get("key", "")))
                marked_value = payload.get("marked") is True
                if not key.startswith("custom:"):
                    raise ValueError("只有自定义标签可以手动标记")
                if not _find_mod(self.mod_root, mod_id, self._catalog()):
                    self._send_json(404, {"error": "找不到这个 Mod"})
                    return
                tags = load_custom_tags(self.mod_root)
                if key not in tags.get(mod_id, {}):
                    self._send_json(404, {"error": "找不到这个自定义标签"})
                    return
                marked = load_marked_tags(self.mod_root)
                mod_marked = marked.setdefault(mod_id, {})
                if marked_value:
                    mod_marked[key] = True
                else:
                    mod_marked.pop(key, None)
                if mod_marked:
                    marked[mod_id] = mod_marked
                else:
                    marked.pop(mod_id, None)
                save_marked_tags(self.mod_root, marked)
                self._sync_cached_mod_tags()
                self._send_json(200, {"ok": True, "key": key, "marked": marked_value})
                return

            if route == "/api/mod/tag/delete":
                payload = self._read_json()
                mod_id = str(payload.get("id", ""))
                key = _validate_tag_key(str(payload.get("key", "")))
                label = _validate_tag_label(str(payload.get("label", "")))
                if not _find_mod(self.mod_root, mod_id, self._catalog()):
                    self._send_json(404, {"error": "找不到这个 Mod"})
                    return
                if key.startswith("custom:"):
                    tags = load_custom_tags(self.mod_root)
                    mod_tags = tags.get(mod_id, {})
                    mod_tags.pop(key, None)
                    if mod_tags:
                        tags[mod_id] = mod_tags
                    else:
                        tags.pop(mod_id, None)
                    save_custom_tags(self.mod_root, tags)
                    marked = load_marked_tags(self.mod_root)
                    mod_marked = marked.get(mod_id, {})
                    mod_marked.pop(key, None)
                    if mod_marked:
                        marked[mod_id] = mod_marked
                    else:
                        marked.pop(mod_id, None)
                    save_marked_tags(self.mod_root, marked)
                else:
                    hidden = load_hidden_tags(self.mod_root)
                    hidden.setdefault(mod_id, {})[key] = label or key
                    save_hidden_tags(self.mod_root, hidden)
                self._sync_cached_mod_tags()
                self._send_json(200, {"ok": True, "key": key})
                return

            if route == "/api/mod/tag/restore":
                payload = self._read_json()
                mod_id = str(payload.get("id", ""))
                key = _validate_tag_key(str(payload.get("key", "")))
                hidden = load_hidden_tags(self.mod_root)
                mod_hidden = hidden.get(mod_id, {})
                mod_hidden.pop(key, None)
                if mod_hidden:
                    hidden[mod_id] = mod_hidden
                else:
                    hidden.pop(mod_id, None)
                save_hidden_tags(self.mod_root, hidden)
                self._sync_cached_mod_tags()
                self._send_json(200, {"ok": True, "key": key})
                return

            if route == "/api/mod/delete":
                payload = self._read_json()
                mod = _find_mod(self.mod_root, str(payload.get("id", "")), self._catalog())
                if not mod:
                    self._send_json(404, {"error": "找不到这个 Mod"})
                    return
                removed: list[str] = []
                preview_files = mod.get("previewFiles", []) or ([mod.get("preview")] if mod.get("preview") else [])
                relative_paths = list(dict.fromkeys([*mod["vpkFiles"], *preview_files]))
                targets: list[Path] = []
                for relative_path in relative_paths:
                    if not relative_path:
                        continue
                    target = _safe_path(self.mod_root, relative_path)
                    if target.is_file():
                        targets.append(target)
                        removed.append(relative_path)
                move_to_recycle_bin(targets)
                self._invalidate_catalog()
                self._send_json(200, {"ok": True, "removed": removed, "recycled": True})
                return

            if route == "/api/mod/file-delete":
                payload = self._read_json()
                mod = _find_mod(self.mod_root, str(payload.get("id", "")), self._catalog())
                if not mod:
                    self._send_json(404, {"error": "找不到这个 Mod"})
                    return
                relative_path = str(payload.get("path", "")).replace("\\", "/")
                if relative_path not in mod.get("vpkFiles", []):
                    raise ValueError("这个文件不属于当前 Mod")
                if Path(relative_path).suffix.casefold() not in VPK_EXTENSIONS:
                    raise ValueError("只能移除 VPK 文件")
                target = _safe_path(self.mod_root, relative_path)
                if not target.is_file():
                    self._send_json(404, {"error": "这个 VPK 文件不存在"})
                    return
                move_to_recycle_bin([target])
                self._invalidate_catalog()
                self._send_json(200, {"ok": True, "removed": [relative_path], "recycled": True})
                return

            if route == "/api/select-folder":
                selected = choose_folder()
                if not selected:
                    self._send_json(200, {"ok": False, "cancelled": True})
                    return
                selected_path = Path(selected).resolve()
                if not selected_path.is_dir():
                    raise ValueError("选择的目录不存在")
                self.server.mod_root = selected_path
                self._invalidate_catalog()
                save_last_folder(selected_path)
                self._send_json(200, {"ok": True, "root": str(selected_path)})
                return

            if route == "/api/reset-folder":
                selected_path = default_folder(Path.cwd())
                if not selected_path.is_dir():
                    raise ValueError(f"默认目录不存在：{selected_path}")
                self.server.mod_root = selected_path
                self._invalidate_catalog()
                save_last_folder(selected_path)
                self._send_json(200, {"ok": True, "root": str(selected_path)})
                return

            if route == "/api/import":
                filename = Path(unquote(self.headers.get("X-Filename", ""))).name
                suffix = Path(filename).suffix.casefold()
                if not filename or suffix not in ARCHIVE_EXTENSIONS:
                    self._send_json(400, {"error": "请选择 ZIP 或常见 tar 压缩包"})
                    return
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0:
                    self._send_json(400, {"error": "压缩包为空"})
                    return
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary:
                    remaining = length
                    while remaining:
                        chunk = self.rfile.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        temporary.write(chunk)
                        remaining -= len(chunk)
                    archive_path = Path(temporary.name)
                try:
                    result = extract_archive(archive_path, self.mod_root)
                finally:
                    archive_path.unlink(missing_ok=True)
                self._invalidate_catalog()
                self._send_json(200, {"ok": True, **result})
                return

            if route == "/api/workshop/import":
                payload = self._read_json()
                raw_ids = payload.get("ids", [])
                if not isinstance(raw_ids, list) or not raw_ids:
                    raise ValueError("请至少选择一个 Workshop Mod")
                ids = list(dict.fromkeys(str(mod_id) for mod_id in raw_ids if str(mod_id)))
                result = copy_workshop_mods(self.mod_root, ids)
                self._invalidate_catalog()
                self._send_json(200, {"ok": True, **result})
                return

            self._send_json(404, {"error": "未知操作"})
        except VoiceReplacementConflict as error:
            self._send_json(409, {"error": str(error), "conflicts": error.conflicts})
        except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile, tarfile.TarError) as error:
            self._send_json(400, {"error": str(error)})


def run_server(root: Path, port: int = 8765, static_root: Path | None = None) -> None:
    root = root.resolve()
    handler = type("ConfiguredModRequestHandler", (ModRequestHandler,), {"root": root})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.mod_root = root
    server.static_root = (static_root or resource_root()).resolve()
    server.catalog_cache = None
    server.spray_assets_cache = None
    log(f"Mod catalog: http://127.0.0.1:{port}/")
    log(f"Scanning: {root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("\nStopping Mod catalog")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local L4D2 Mod catalog")
    parser.add_argument("folder", nargs="?", type=Path, default=None)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    root = args.folder.resolve() if args.folder else load_last_folder(Path.cwd().resolve())
    run_server(root, args.port)


if __name__ == "__main__":
    main()
