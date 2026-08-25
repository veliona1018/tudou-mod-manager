"""Local NekoVPK inspection and survivor-target conversion helpers.

This module is intentionally separate from the normal VPK catalog and mutation
paths.  It only activates for archives containing a ``nekovpk/*.neko7z``
member.
"""

from __future__ import annotations

import os
import fnmatch
import shutil
import struct
import subprocess
import tempfile
import uuid
import zlib
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from vpk_detector import VPKFormatError, read_vpk_file, read_vpk_paths


NEKOVPK_SUFFIX = ".neko7z"
NEKOVPK_BACKUP_SUFFIX = ".nekobak"
VPK_SIGNATURE = 0x55AA1234
VPK_VERSION_1 = 1
VPK_VERSION_2 = 2
EMBEDDED_ARCHIVE_INDEX = 0x7FFF


# These patterns mirror the survivor entries in NekoVPK's TaggedAssets.jsonc.
# Keep the complete target set here so conversion removes stale UI resources as
# well as the model and arm files.
SURVIVOR_TARGETS = (
    {
        "id": "bill",
        "name": "Bill",
        "patterns": (
            "materials/vgui/s_panel_namvet.*",
            "materials/vgui/s_panel_namvet_incap.*",
            "materials/vgui/select_bill.*",
            "models/survivors/survivor_namvet.*",
            "models/survivors/namvet/namvet_deathpose.*",
            "models/weapons/arms/v_arms_bill.*",
        ),
    },
    {
        "id": "zoey",
        "name": "Zoey",
        "patterns": (
            "materials/vgui/s_panel_teenangst.*",
            "materials/vgui/s_panel_teenangst_incap.*",
            "materials/vgui/select_zoey.*",
            "models/survivors/survivor_teenangst.*",
            "models/survivors/survivor_teenangst_light.*",
            "models/weapons/arms/v_arms_zoey.*",
        ),
    },
    {
        "id": "louis",
        "name": "Louis",
        "patterns": (
            "materials/vgui/s_panel_manager.*",
            "materials/vgui/s_panel_manager_incap.*",
            "materials/vgui/select_louis.*",
            "models/survivors/survivor_manager.*",
            "models/weapons/arms/v_arms_louis.*",
        ),
    },
    {
        "id": "francis",
        "name": "Francis",
        "patterns": (
            "materials/vgui/s_panel_biker.*",
            "materials/vgui/s_panel_biker_incap.*",
            "materials/vgui/select_francis.*",
            "models/survivors/survivor_biker.*",
            "models/survivors/survivor_biker_light.*",
            "models/weapons/arms/v_arms_francis.*",
        ),
    },
    {
        "id": "nick",
        "name": "Nick",
        "patterns": (
            "materials/vgui/s_panel_gambler.*",
            "materials/vgui/s_panel_gambler_incap.*",
            "materials/vgui/s_panel_lobby_gambler.*",
            "materials/vgui/select_nick.*",
            "models/survivors/survivor_gambler.*",
            "models/weapons/arms/v_arms_gambler_new.*",
        ),
    },
    {
        "id": "coach",
        "name": "Coach",
        "patterns": (
            "materials/vgui/s_panel_coach.*",
            "materials/vgui/s_panel_coach_incap.*",
            "materials/vgui/s_panel_lobby_coach.*",
            "models/survivors/survivor_coach.*",
            "models/weapons/arms/v_arms_coach_new.*",
        ),
    },
    {
        "id": "ellis",
        "name": "Ellis",
        "patterns": (
            "materials/vgui/s_panel_mechanic.*",
            "materials/vgui/s_panel_mechanic_incap.*",
            "materials/vgui/s_panel_lobby_mechanic.*",
            "models/survivors/survivor_mechanic.*",
            "models/weapons/arms/v_arms_mechanic_new.*",
        ),
    },
    {
        "id": "rochelle",
        "name": "Rochelle",
        "patterns": (
            "materials/vgui/s_panel_producer.*",
            "materials/vgui/s_panel_producer_incap.*",
            "materials/vgui/s_panel_lobby_producer.*",
            "models/survivors/survivor_producer.*",
            "models/weapons/arms/v_arms_producer_new.*",
        ),
    },
)
TARGET_BY_ID = {target["id"]: target for target in SURVIVOR_TARGETS}


class NekoVPKError(ValueError):
    """Raised when a NekoVPK archive cannot be safely inspected or changed."""


def _normalize_member(name: str) -> str:
    value = name.replace("\\", "/").strip()
    while value.startswith("./"):
        value = value[2:]
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise NekoVPKError(f"NekoVPK 内部路径不安全：{name}")
    return "/".join(path.parts).casefold()


def _find_tar() -> str:
    tar = shutil.which("tar")
    if tar:
        return tar
    raise NekoVPKError("未找到系统 tar 工具，暂时无法读取 NekoVPK 的 .neko7z 文件")


def _run_tar(tar: str, args: list[str], *, text: bool = False) -> str | bytes:
    try:
        completed = subprocess.run(
            [tar, *args],
            check=True,
            capture_output=True,
            text=text,
            encoding="utf-8" if text else None,
            errors="replace" if text else None,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        details = ""
        if isinstance(error, subprocess.CalledProcessError):
            details = (error.stderr or "").strip()
        raise NekoVPKError(f"读取 .neko7z 失败{f'：{details}' if details else ''}") from error
    return completed.stdout


def _list_7z_members(archive: Path) -> dict[str, str]:
    tar = _find_tar()
    output = _run_tar(tar, ["-tf", str(archive)], text=True)
    members: dict[str, str] = {}
    for raw_name in str(output).splitlines():
        name = raw_name.strip()
        if not name or name.endswith("/"):
            continue
        normalized = _normalize_member(name)
        if normalized in members and members[normalized] != name:
            raise NekoVPKError(f".neko7z 内部存在重复路径：{name}")
        members[normalized] = name
    if not members:
        raise NekoVPKError(".neko7z 内没有可读取的文件")
    return members


def _extract_7z_member(archive: Path, member: str) -> bytes:
    tar = _find_tar()
    output = _run_tar(tar, ["-xOf", str(archive), member])
    if not isinstance(output, bytes):
        raise NekoVPKError("读取 .neko7z 文件内容失败")
    return output


@contextmanager
def _with_nested_archive(vpk_path: Path):
    paths = read_vpk_paths(vpk_path)
    nested_paths = [
        path
        for path in paths
        if path.startswith("nekovpk/") and path.endswith(NEKOVPK_SUFFIX)
    ]
    if len(nested_paths) != 1:
        if not nested_paths:
            raise NekoVPKError("这个 VPK 不是 NekoVPK 格式")
        raise NekoVPKError("这个 VPK 包含多个 .neko7z，暂不自动修改")
    data = read_vpk_file(vpk_path, nested_paths[0])
    if not data:
        raise NekoVPKError("NekoVPK 的 .neko7z 文件为空")
    with tempfile.TemporaryDirectory(prefix="l4d2-nekovpk-") as temp_dir:
        archive = Path(temp_dir) / "content.neko7z"
        archive.write_bytes(data)
        yield nested_paths[0], archive, _list_7z_members(archive)


def _target_matches(path: str, target: dict) -> bool:
    normalized = path.casefold()
    return any(
        fnmatch.fnmatchcase(normalized, pattern.casefold())
        for pattern in target["patterns"]
    )


def _target_file_paths(paths: list[str] | set[str], target: dict) -> list[str]:
    return sorted(path for path in paths if _target_matches(path, target))


def _has_required_model_set(paths: set[str], target: dict) -> bool:
    model = any(
        path.startswith("models/survivors/")
        and _target_matches(path, target)
        for path in paths
    )
    arms = any(
        path.startswith("models/weapons/arms/")
        and _target_matches(path, target)
        for path in paths
    )
    return model and arms


def _target_summary(target: dict, paths: set[str], *, source: str) -> dict:
    files = _target_file_paths(paths, target)
    return {
        "id": target["id"],
        "name": target["name"],
        "fileCount": len(files),
        "source": source,
    }


def inspect_nekovpk(vpk_path: str | Path) -> dict:
    """Inspect one VPK and return its NekoVPK target choices."""

    path = Path(vpk_path)
    outer_paths = set(read_vpk_paths(path))
    current_targets = {
        target["id"]: target
        for target in SURVIVOR_TARGETS
        if _has_required_model_set(outer_paths, target)
    }
    backup_paths: set[str] = set()
    backup_path = _backup_path(path)
    if backup_path.is_file():
        try:
            backup_paths = set(read_vpk_paths(backup_path))
        except (OSError, VPKFormatError):
            backup_paths = set()
        if not any(
            item.startswith("nekovpk/") and item.endswith(NEKOVPK_SUFFIX)
            for item in backup_paths
        ):
            backup_paths = set()
    backup_targets = {
        target["id"]: target
        for target in SURVIVOR_TARGETS
        if _has_required_model_set(backup_paths, target)
    }
    with _with_nested_archive(path) as (nested_path, archive, members):
        inner_paths = set(members)
        available: dict[str, dict] = {}
        for target in SURVIVOR_TARGETS:
            if _has_required_model_set(inner_paths, target):
                available[target["id"]] = _target_summary(target, inner_paths, source="neko7z")
            elif target["id"] in current_targets:
                available[target["id"]] = _target_summary(target, outer_paths, source="vpk")
            elif target["id"] in backup_targets:
                available[target["id"]] = _target_summary(target, backup_paths, source="备份")
        current = next(iter(current_targets), None)
        return {
            "format": "nekovpk",
            "nestedPath": nested_path,
            "currentTarget": current,
            "currentName": TARGET_BY_ID[current]["name"] if current else None,
            "targets": [available[target["id"]] for target in SURVIVOR_TARGETS if target["id"] in available],
            "innerFileCount": len(inner_paths),
        }


def _read_cstring(handle: BinaryIO, end: int) -> str:
    raw = bytearray()
    while handle.tell() < end:
        byte = handle.read(1)
        if not byte or byte == b"\x00":
            break
        raw.extend(byte)
    else:
        raise VPKFormatError("VPK 字符串没有正确结束")
    return raw.decode("utf-8", errors="replace")


def read_vpk_entries(file_path: str | Path) -> dict[str, bytes]:
    """Read embedded VPK entries for the isolated NekoVPK rewrite path."""

    path = Path(file_path)
    with path.open("rb") as handle:
        header = handle.read(12)
        if len(header) != 12:
            raise VPKFormatError("VPK 文件过小")
        signature, version, tree_size = struct.unpack("<III", header)
        if signature != VPK_SIGNATURE or version not in (VPK_VERSION_1, VPK_VERSION_2):
            raise VPKFormatError("不支持的 VPK 格式")
        header_size = 12
        if version == VPK_VERSION_2:
            if len(handle.read(16)) != 16:
                raise VPKFormatError("VPK v2 头部不完整")
            header_size = 28
        tree_end = header_size + tree_size
        entries: list[tuple[str, int, int, int, bytes]] = []
        handle.seek(header_size)
        while handle.tell() < tree_end:
            extension = _read_cstring(handle, tree_end)
            if not extension:
                break
            while True:
                folder = _read_cstring(handle, tree_end)
                if not folder:
                    break
                while True:
                    filename = _read_cstring(handle, tree_end)
                    if not filename:
                        break
                    raw_entry = handle.read(18)
                    if len(raw_entry) != 18:
                        raise VPKFormatError("VPK 文件条目不完整")
                    _, preload_bytes, archive_index, offset, length, terminator = struct.unpack(
                        "<IHHIIH", raw_entry
                    )
                    if terminator != 0xFFFF:
                        raise VPKFormatError("VPK 文件条目标记无效")
                    preload = handle.read(preload_bytes)
                    if len(preload) != preload_bytes:
                        raise VPKFormatError("VPK 预加载数据不完整")
                    relative = "/".join(
                        part for part in ("" if folder == " " else folder, filename) if part
                    )
                    entries.append((f"{relative}.{extension}", archive_index, offset, length, preload))
        if handle.tell() > tree_end:
            raise VPKFormatError("VPK 目录树超出声明范围")

        embedded = bytearray()
        handle.seek(tree_end)
        embedded.extend(handle.read())

    external_cache: dict[Path, bytes] = {}
    result: dict[str, bytes] = {}
    for relative, archive_index, offset, length, preload in entries:
        if archive_index == EMBEDDED_ARCHIVE_INDEX:
            if offset + length > len(embedded):
                raise VPKFormatError(f"VPK 数据超出范围：{relative}")
            payload = bytes(embedded[offset : offset + length])
        else:
            archive_stem = path.stem.removesuffix("_dir")
            archive_path = path.with_name(f"{archive_stem}_{archive_index:03d}{path.suffix}")
            if archive_path not in external_cache:
                try:
                    external_cache[archive_path] = archive_path.read_bytes()
                except OSError as error:
                    raise VPKFormatError(f"找不到 VPK 分卷：{archive_path.name}") from error
            archive_data = external_cache[archive_path]
            if offset + length > len(archive_data):
                raise VPKFormatError(f"VPK 分卷数据超出范围：{relative}")
            payload = archive_data[offset : offset + length]
        normalized = relative.replace("\\", "/").casefold()
        if normalized in result:
            raise VPKFormatError(f"VPK 包含重复路径：{relative}")
        result[normalized] = preload + payload
    return result


def write_vpk_entries(file_path: str | Path, entries: dict[str, bytes]) -> None:
    """Write a compact embedded VPK v1 archive."""

    grouped: dict[str, dict[str, list[tuple[str, str, bytes]]]] = {}
    for relative, content in entries.items():
        normalized = relative.replace("\\", "/").strip("/").casefold()
        if not normalized or ".." in PurePosixPath(normalized).parts:
            raise NekoVPKError(f"无法写入不安全的 VPK 路径：{relative}")
        folder, filename = normalized.rsplit("/", 1) if "/" in normalized else (" ", normalized)
        if "." in filename:
            stem, extension = filename.rsplit(".", 1)
        else:
            stem, extension = filename, ""
        grouped.setdefault(extension, {}).setdefault(folder, []).append(
            (stem, filename, bytes(content))
        )

    tree = bytearray()
    payload = bytearray()
    for extension, folders in sorted(grouped.items()):
        tree.extend(extension.encode("utf-8") + b"\x00")
        for folder, files in sorted(folders.items()):
            tree.extend(folder.encode("utf-8") + b"\x00")
            for stem, _, content in sorted(files, key=lambda item: item[0]):
                tree.extend(stem.encode("utf-8") + b"\x00")
                tree.extend(
                    struct.pack(
                        "<IHHIIH",
                        zlib.crc32(content) & 0xFFFFFFFF,
                        0,
                        EMBEDDED_ARCHIVE_INDEX,
                        len(payload),
                        len(content),
                        0xFFFF,
                    )
                )
                payload.extend(content)
            tree.extend(b"\x00")
        tree.extend(b"\x00")
    tree.extend(b"\x00")
    Path(file_path).write_bytes(struct.pack("<III", VPK_SIGNATURE, VPK_VERSION_1, len(tree)) + tree + payload)


def _backup_path(vpk_path: Path) -> Path:
    return vpk_path.with_name(vpk_path.name + NEKOVPK_BACKUP_SUFFIX)


def convert_nekovpk_target(vpk_path: str | Path, target_id: str) -> dict:
    """Switch one NekoVPK archive to a prebuilt survivor target."""

    path = Path(vpk_path)
    target_id = str(target_id).strip().casefold()
    if target_id not in TARGET_BY_ID:
        raise NekoVPKError("不支持的生还者角色")
    info = inspect_nekovpk(path)
    target = TARGET_BY_ID[target_id]
    if target_id not in {item["id"] for item in info["targets"]}:
        raise NekoVPKError(f"这个 NekoVPK 没有预置 {target['name']} 资源")
    if info.get("currentTarget") == target_id:
        return {"changed": False, "target": target_id, "backup": None}

    backup = _backup_path(path)
    if not backup.exists():
        shutil.copy2(path, backup)
    base_path = backup if backup.is_file() else path
    base_entries = read_vpk_entries(base_path)
    nested_data = read_vpk_file(path, info["nestedPath"])
    if not nested_data:
        raise NekoVPKError("无法重新读取 NekoVPK 资源包")

    with tempfile.TemporaryDirectory(prefix="l4d2-nekovpk-convert-") as temp_dir:
        nested_archive = Path(temp_dir) / "content.neko7z"
        nested_archive.write_bytes(nested_data)
        members = _list_7z_members(nested_archive)
        current_outer = {
            relative: content
            for relative, content in base_entries.items()
            if _target_matches(relative, target)
        }
        base_target_members = _target_file_paths(set(base_entries), target)
        for relative in list(base_entries):
            if any(_target_matches(relative, candidate) for candidate in SURVIVOR_TARGETS):
                del base_entries[relative]

        target_members = _target_file_paths(set(members), target)
        if target_members:
            for relative in target_members:
                base_entries[relative] = _extract_7z_member(nested_archive, members[relative])
        elif base_target_members:
            base_entries.update({relative: current_outer[relative] for relative in base_target_members if relative in current_outer})
        else:
            raise NekoVPKError(f".neko7z 中没有完整的 {target['name']} 资源")

        temp_output = path.with_name(f".{path.name}.nekovpk-{uuid.uuid4().hex}.tmp")
        try:
            write_vpk_entries(temp_output, base_entries)
            os.replace(temp_output, path)
        finally:
            try:
                temp_output.unlink()
            except FileNotFoundError:
                pass

    return {"changed": True, "target": target_id, "targetName": target["name"], "backup": str(backup)}
