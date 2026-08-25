"""Inspect Left 4 Dead 2 VPK directory trees and infer add-on categories."""

from __future__ import annotations

import argparse
import json
import re
import struct
from pathlib import Path
from typing import BinaryIO


VPK_SIGNATURE = 0x55AA1234
VPK_VERSION_1 = 1
VPK_VERSION_2 = 2

MODEL_EXTENSIONS = (".mdl", ".vvd", ".vtx", ".phy")
WEAPON_MODEL_PREFIXES = (
    "models/weapons/",
    "models/v_models/",
    "models/w_models/",
)
WEAPON_TARGETS = (
    ("grenade_launcher", "grenade_launcher", "榴弹发射器"),
    ("desert_eagle", "desert_eagle", "沙漠之鹰"),
    ("sniper_scout", "sniper_scout", "Scout 狙击枪"),
    ("snip_scout", "sniper_scout", "Scout 狙击枪"),
    ("sniper_awp", "awp", "AWP 狙击枪"),
    ("snip_awp", "awp", "AWP 狙击枪"),
    ("sniper_military", "sniper_military", "军用狙击枪"),
    ("huntingrifle", "hunting_rifle", "猎枪"),
    ("hunting_rifle", "hunting_rifle", "猎枪"),
    ("desert_rifle", "scar", "SCAR-L"),
    ("m16a2", "m16", "M16"),
    ("rifle_m16", "m16", "M16"),
    ("ak47", "ak47", "AK-47"),
    ("scar", "scar", "SCAR-L"),
    ("sg552", "sg552", "SG552"),
    ("smg_mp5", "smg_mp5", "MP5 冲锋枪"),
    ("smg_silenced", "smg_silenced", "消音冲锋枪"),
    ("smg", "smg", "冲锋枪"),
    ("m60", "m60", "M60 重机枪"),
    ("autoshotgun", "autoshotgun", "自动霰弹枪"),
    ("pumpshotgun", "pumpshotgun", "泵动霰弹枪"),
    ("shotgun_chrome", "chrome_shotgun", "铬霰弹枪"),
    ("shotgun_spas", "spas", "SPAS-12"),
    ("molotov", "molotov", "燃烧瓶"),
    ("pipebomb", "pipebomb", "管制炸弹"),
    ("bile_flask", "bile_flask", "胆汁罐"),
    ("fireaxe", "fireaxe", "消防斧"),
    ("chainsaw", "chainsaw", "电锯"),
    ("riotshield", "riotshield", "防暴盾牌"),
    ("crowbar", "crowbar", "撬棍"),
    ("pitchfork", "pitchfork", "干草叉"),
    ("frying_pan", "frying_pan", "平底锅"),
    ("machete", "machete", "砍刀"),
    ("golfclub", "golfclub", "高尔夫球杆"),
    ("cricket_bat", "cricket_bat", "板球棒"),
    ("katana", "katana", "武士刀"),
    ("tonfa", "tonfa", "警棍"),
    ("knife", "knife", "小刀"),
    ("pistol", "pistol", "手枪"),
)
SURVIVOR_TARGETS = (
    ("survivor_namvet", "bill", "Bill"),
    ("survivor_teenangst", "zoey", "Zoey"),
    ("survivor_manager", "louis", "Louis"),
    ("survivor_biker", "francis", "Francis"),
    ("survivor_gambler", "nick", "Nick"),
    ("survivor_coach", "coach", "Coach"),
    ("survivor_mechanic", "ellis", "Ellis"),
    ("survivor_producer", "rochelle", "Rochelle"),
)
INFECTED_TARGETS = (
    ("common_male", "common_male", "普通感染者（男性）"),
    ("common_female", "common_female", "普通感染者（女性）"),
    ("boomer", "boomer", "Boomer"),
    ("hunter", "hunter", "Hunter"),
    ("smoker", "smoker", "Smoker"),
    ("charger", "charger", "Charger"),
    ("jockey", "jockey", "Jockey"),
    ("spitter", "spitter", "Spitter"),
    ("tank", "tank", "Tank"),
    ("witch", "witch", "Witch"),
)
SCRIPT_EXTENSIONS = (".nut", ".txt", ".lst", ".cfg")


class VPKFormatError(ValueError):
    """Raised when a file is not a readable VPK directory archive."""


class VPKClassificationError(ValueError):
    """Raised when a readable VPK has no recognizable supported content."""


def _read_cstring(handle: BinaryIO, end: int) -> str:
    raw = bytearray()
    while handle.tell() < end:
        byte = handle.read(1)
        if not byte or byte == b"\x00":
            break
        raw.extend(byte)
    else:
        raise VPKFormatError("unterminated string in VPK directory tree")
    return raw.decode("utf-8", errors="replace")


def read_vpk_paths(file_path: str | Path) -> list[str]:
    """Read only the VPK directory tree and return normalized internal paths."""

    path = Path(file_path)
    with path.open("rb") as handle:
        header = handle.read(12)
        if len(header) != 12:
            raise VPKFormatError("file is too small to be a VPK")

        signature, version, tree_size = struct.unpack("<III", header)
        if signature != VPK_SIGNATURE:
            raise VPKFormatError("invalid VPK signature")
        if version not in (VPK_VERSION_1, VPK_VERSION_2):
            raise VPKFormatError(f"unsupported VPK version: {version}")

        header_size = 12
        if version == VPK_VERSION_2:
            extra_header = handle.read(16)
            if len(extra_header) != 16:
                raise VPKFormatError("truncated VPK v2 header")
            header_size = 28

        tree_end = header_size + tree_size
        handle.seek(header_size)
        paths: list[str] = []

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

                    entry = handle.read(18)
                    if len(entry) != 18:
                        raise VPKFormatError("truncated VPK file entry")
                    _, preload_bytes, _, _, entry_length, terminator = struct.unpack(
                        "<IHHIIH", entry
                    )
                    if terminator != 0xFFFF:
                        raise VPKFormatError("invalid VPK file entry terminator")

                    if handle.tell() + preload_bytes > tree_end:
                        raise VPKFormatError("truncated VPK preload data")
                    handle.seek(preload_bytes, 1)

                    relative_folder = "" if folder == " " else folder
                    relative = "/".join(
                        part for part in (relative_folder, filename) if part
                    )
                    paths.append(f"{relative}.{extension}".lower())

        if handle.tell() > tree_end:
            raise VPKFormatError("VPK directory tree exceeds declared size")

        return paths


def read_vpk_file(file_path: str | Path, relative_path: str) -> bytes | None:
    """Read one embedded file from a VPK, including its preload bytes."""

    path = Path(file_path)
    with path.open("rb") as handle:
        header = handle.read(12)
        if len(header) != 12:
            raise VPKFormatError("file is too small to be a VPK")
        signature, version, tree_size = struct.unpack("<III", header)
        if signature != VPK_SIGNATURE:
            raise VPKFormatError("invalid VPK signature")
        if version not in (VPK_VERSION_1, VPK_VERSION_2):
            raise VPKFormatError(f"unsupported VPK version: {version}")

        header_size = 12
        if version == VPK_VERSION_2:
            extra_header = handle.read(16)
            if len(extra_header) != 16:
                raise VPKFormatError("truncated VPK v2 header")
            header_size = 28

        tree_end = header_size + tree_size
        handle.seek(header_size)
        wanted = relative_path.replace("\\", "/").casefold()
        match: tuple[int, int, int, bytes] | None = None

        def read_string() -> str:
            raw = bytearray()
            while handle.tell() < tree_end:
                byte = handle.read(1)
                if not byte or byte == b"\x00":
                    break
                raw.extend(byte)
            else:
                raise VPKFormatError("unterminated string in VPK directory tree")
            return raw.decode("utf-8", errors="replace")

        while handle.tell() < tree_end:
            extension = read_string()
            if not extension:
                break
            while True:
                folder = read_string()
                if not folder:
                    break
                while True:
                    filename = read_string()
                    if not filename:
                        break
                    _, preload_bytes, archive_index, entry_offset, entry_length, terminator = struct.unpack(
                        "<IHHIIH", handle.read(18)
                    )
                    if terminator != 0xFFFF:
                        raise VPKFormatError("invalid VPK file entry terminator")
                    preload = handle.read(preload_bytes)
                    current_path = "/".join(
                        part for part in ("" if folder == " " else folder, filename) if part
                    )
                    current_path = f"{current_path}.{extension}".casefold()
                    if current_path == wanted:
                        match = (archive_index, entry_offset, entry_length, preload)

        if not match:
            return None

        archive_index, entry_offset, entry_length, preload = match
        if archive_index == 0x7FFF:
            handle.seek(tree_end + entry_offset)
            return preload + handle.read(entry_length)

    archive_stem = path.stem.removesuffix("_dir")
    archive_path = path.with_name(f"{archive_stem}_{archive_index:03d}{path.suffix}")
    with archive_path.open("rb") as archive:
        archive.seek(entry_offset)
        return preload + archive.read(entry_length)


def read_vpk_addon_title(file_path: str | Path) -> str | None:
    """Read the optional human-readable title from addoninfo.txt."""

    try:
        content = read_vpk_file(file_path, "addoninfo.txt")
    except (OSError, VPKFormatError):
        return None
    if not content:
        return None
    text = content.decode("utf-8", errors="replace")
    match = re.search(r"(?i)\baddontitle\s+\"([^\"]+)\"", text)
    return match.group(1).strip() if match else None


def _has_path(paths: list[str], *prefixes: str) -> list[str]:
    return [path for path in paths if any(path.startswith(prefix) for prefix in prefixes)]


def identify_character_targets(paths: list[str]) -> list[dict]:
    """Map recognizable model/material paths to a concrete survivor or infected target."""

    found: dict[tuple[str, str], dict] = {}
    for path in paths:
        lower_path = path.lower()
        is_survivor_resource = lower_path.startswith(
            (
                "models/survivors/",
                "models/player/survivor/",
                "materials/models/survivors/",
                "materials/models/player/survivor/",
            )
        )
        is_infected_resource = lower_path.startswith(
            (
                "models/infected/",
                "models/player/infected/",
                "materials/models/infected/",
                "materials/models/player/infected/",
            )
        )
        if not (is_survivor_resource or is_infected_resource):
            continue

        for pattern, target_id, display_name in SURVIVOR_TARGETS:
            if pattern in lower_path and is_survivor_resource:
                key = ("survivor", target_id)
                found.setdefault(
                    key,
                    {"side": "survivor", "id": target_id, "name": display_name, "evidence": []},
                )["evidence"].append(path)
        for pattern, target_id, display_name in INFECTED_TARGETS:
            if pattern in lower_path and is_infected_resource:
                key = ("infected", target_id)
                found.setdefault(
                    key,
                    {"side": "infected", "id": target_id, "name": display_name, "evidence": []},
                )["evidence"].append(path)

    for target in found.values():
        target["evidence"] = target["evidence"][:12]
    return sorted(found.values(), key=lambda target: (target["side"], target["name"]))


def identify_weapon_targets(paths: list[str]) -> list[dict]:
    """Map weapon model paths to the weapon they replace."""

    found: dict[str, dict] = {}
    for path in paths:
        lower_path = path.lower()
        if not lower_path.startswith(WEAPON_MODEL_PREFIXES) or not lower_path.endswith(MODEL_EXTENSIONS):
            continue
        for pattern, target_id, display_name in WEAPON_TARGETS:
            if pattern not in lower_path:
                continue
            found.setdefault(
                target_id,
                {"id": target_id, "name": display_name, "evidence": []},
            )["evidence"].append(path)

    for target in found.values():
        target["evidence"] = target["evidence"][:12]
    return sorted(found.values(), key=lambda target: target["name"])


def classify_paths(paths: list[str]) -> dict:
    """Classify an add-on from its internal paths using explainable heuristics."""

    normalized = sorted(set(path.replace("\\", "/").lower() for path in paths))
    signals: dict[str, list[str]] = {
        "map": [],
        "survivor_model": [],
        "infected_model": [],
        "weapon_model": [],
        "prop_model": [],
        "spray": [],
        "sound": [],
        "voice_replacement": [],
        "texture": [],
        "ui": [],
        "script": [],
    }

    for path in normalized:
        if path.startswith("maps/") and path.endswith(".bsp"):
            signals["map"].append(path)
        elif path.startswith("missions/") and path.endswith((".txt", ".res")):
            signals["map"].append(path)
        elif path.startswith("maps/") and path.endswith(".nav"):
            signals["map"].append(path)

        if path.endswith(MODEL_EXTENSIONS) and path.startswith("models/"):
            if path.startswith(("models/survivors/", "models/player/survivor/")):
                signals["survivor_model"].append(path)
            elif path.startswith(("models/infected/", "models/player/infected/")):
                signals["infected_model"].append(path)
            elif path.startswith(WEAPON_MODEL_PREFIXES):
                signals["weapon_model"].append(path)
            else:
                signals["prop_model"].append(path)

        if path.startswith("materials/vgui/logos/"):
            signals["spray"].append(path)
        if path.startswith("sound/"):
            signals["sound"].append(path)
            if path.startswith(
                (
                    "sound/player/survivor/voice/",
                    "sound/player/infected/voice/",
                    "sound/vo/",
                )
            ):
                signals["voice_replacement"].append(path)
        if path.startswith(("materials/", "particles/")):
            signals["texture"].append(path)
        if path.startswith("resource/ui/") and path.endswith((".res", ".txt")):
            signals["ui"].append(path)
        if path.startswith("scripts/") and path.endswith(SCRIPT_EXTENSIONS):
            signals["script"].append(path)

    # A single BSP or model is more meaningful than thousands of supporting materials.
    scores = {
        "map": (100 if any(path.endswith(".bsp") for path in signals["map"]) else 20)
        if signals["map"]
        else 0,
        "survivor_model": 100 if signals["survivor_model"] else 0,
        "infected_model": 100 if signals["infected_model"] else 0,
        "weapon_model": 60 if signals["weapon_model"] else 0,
        "prop_model": 50 if signals["prop_model"] else 0,
        "spray": 100 if signals["spray"] else 0,
        "sound": 30 if signals["sound"] else 0,
        "voice_replacement": 100 if signals["voice_replacement"] else 0,
        "texture": 10 if signals["texture"] else 0,
        "ui": 70 if signals["ui"] else 0,
        "script": 60 if signals["script"] else 0,
    }
    active = [key for key, score in scores.items() if score > 0]
    priority = [
        "map",
        "survivor_model",
        "infected_model",
        "spray",
        "weapon_model",
        "prop_model",
        "ui",
        "voice_replacement",
        "script",
        "sound",
        "texture",
    ]
    ranked = sorted(active, key=lambda key: (-scores[key], priority.index(key)))
    if signals["map"]:
        # Campaign packages commonly contain infected, survivor and weapon
        # resources. The map manifest/BSP is the owning content in that case.
        primary = "map"
        ranked = ["map", *(key for key in ranked if key != "map")]
    else:
        primary = ranked[0] if ranked else "unknown"
    confidence = "high" if ranked and scores[primary] >= 3 else "medium" if ranked else "low"
    character_targets = identify_character_targets(normalized)

    return {
        "primary": primary,
        "categories": ranked,
        "confidence": confidence,
        "file_count": len(normalized),
        "characterTargets": character_targets,
        "weaponTargets": identify_weapon_targets(normalized),
        "signals": {key: values[:12] for key, values in signals.items() if values},
        "scores": {key: scores[key] for key in ranked},
    }


def analyze_vpk(file_path: str | Path) -> dict:
    path = Path(file_path)
    paths = read_vpk_paths(path)
    result = classify_paths(paths)
    if result["primary"] == "unknown":
        raise VPKClassificationError(
            "VPK directory is readable, but no supported content signature was found"
        )
    result.update(
        {
            "file": str(path),
            "name": path.name,
            "addonTitle": read_vpk_addon_title(path),
        }
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect the content type of L4D2 VPK files")
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()

    for file_path in args.files:
        try:
            print(json.dumps(analyze_vpk(file_path), ensure_ascii=False, indent=2))
        except (OSError, VPKFormatError, VPKClassificationError) as error:
            print(json.dumps({"file": str(file_path), "error": str(error)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
