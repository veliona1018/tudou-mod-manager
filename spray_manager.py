"""Inspect individual L4D2 spray assets and build a selected spray VPK."""

from __future__ import annotations

import hashlib
import base64
import io
import json
import math
import re
import shutil
import struct
import tempfile
import uuid
import zlib
from pathlib import Path, PurePosixPath

from nekovpk import write_vpk_entries
from vpk_detector import read_vpk_file, read_vpk_paths
from manager_storage import (
    IMPORTED_SPRAY_DIR,
    SPRAY_PREVIEW_DIR,
    SPRAY_STATE_FILE,
    ensure_manager_data_layout,
)


SPRAY_MANIFEST_PATH = "scripts/sprays_manifest.txt"
SPRAY_ROOT = "materials/vgui/logos/"
SPRAY_COLLECTION_VPK = "L4D2ModManager_SprayCollection.vpk"
SPRAY_COLLECTION_STATE = SPRAY_STATE_FILE
SPRAY_CONFIG_FILE = f"{IMPORTED_SPRAY_DIR.rsplit('/', 1)[0]}/.l4d2_mod_manager_spray_configs.json"
SPRAY_PREVIEW_CACHE_DIR = SPRAY_PREVIEW_DIR
SPRAY_LOOSE_BACKUP_DIR = f"{IMPORTED_SPRAY_DIR.rsplit('/', 1)[0]}/spray_loose_backups"
SPRAY_VPK_BACKUP_DIR = f"{IMPORTED_SPRAY_DIR.rsplit('/', 1)[0]}/spray_vpk_backups"
SPRAY_STANDARD_SLOTS = tuple(str(index) for index in range(1, 17))
IMPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_IMPORTED_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMPORTED_IMAGE_DIMENSION = 1024
MAX_SPRAY_VTF_DIMENSION = 512
MAX_ANIMATED_SPRAY_VTF_DIMENSION = 256
MIN_SPRAY_MIP_DIMENSION = 1
# L4D2 spray animation is reliably accepted in the same 16-frame layout used
# by the known-working website-generated VTF.
MAX_SPRAY_VTF_FRAMES = 16
SPRAY_MIPMAP_LEVELS = (512, 256, 128, 64, 32)
MIN_CONFIG_DURATION_MS = 20
MAX_CONFIG_DURATION_MS = 5000
MAX_GRADIENT_STEPS = 32
_MANIFEST_PAIR = re.compile(r'"([^"\r\n]+)"\s+"([^"\r\n]+)"')
_BASE_TEXTURE = re.compile(r'(\$basetexture"?\s+")[^"]+("?)', re.IGNORECASE)


class SprayError(ValueError):
    """Raised when a spray package cannot be read or combined safely."""


def load_spray_configurations(root: str | Path) -> dict[str, dict]:
    root_path = Path(root).resolve()
    ensure_manager_data_layout(root_path)
    path = root_path / SPRAY_CONFIG_FILE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_spray_configurations(root: Path, configurations: dict[str, dict]) -> None:
    path = root / SPRAY_CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(configurations, ensure_ascii=False, indent=2), encoding="utf-8")


def _imported_asset(root: Path, asset_id: str) -> dict:
    asset = next((item for item in _imported_spray_assets(root) if item["id"] == asset_id), None)
    if asset is None:
        raise SprayError("配置引用了不存在的导入图片")
    return asset


def _imported_frame_count(path: Path) -> int:
    try:
        from PIL import Image
        with Image.open(path) as image:
            return max(1, int(getattr(image, "n_frames", 1)))
    except (ImportError, OSError, EOFError) as error:
        raise SprayError(f"无法读取导入图片：{path.name}") from error


def _config_frame(asset: dict, frame: object) -> int:
    try:
        value = int(frame)
    except (TypeError, ValueError) as error:
        raise SprayError(f"图片帧编号无效：{asset['filename']}") from error
    if value < 0 or value >= _imported_frame_count(Path(asset["_absolutePath"])):
        raise SprayError(f"图片帧编号超出范围：{asset['filename']}")
    return value


def _config_duration(value: object, default: int = 100) -> int:
    try:
        duration = int(value)
    except (TypeError, ValueError) as error:
        raise SprayError("帧持续时间必须是数字") from error
    if not MIN_CONFIG_DURATION_MS <= duration <= MAX_CONFIG_DURATION_MS:
        raise SprayError(f"帧持续时间必须在 {MIN_CONFIG_DURATION_MS} 到 {MAX_CONFIG_DURATION_MS} 毫秒之间")
    return duration


def _validate_spray_configuration(root: Path, asset_id: str, configuration: object) -> dict:
    if not isinstance(configuration, dict):
        raise SprayError("喷漆配置无效")
    base_asset = _imported_asset(root, asset_id)
    base_asset["_absolutePath"] = str((root / base_asset["importedPath"]).resolve())
    mode = str(configuration.get("mode", "static")).casefold()
    if mode not in {"static", "dynamic", "gradient"}:
        raise SprayError("喷漆模式只能是静态、动态或渐变")

    if mode == "static":
        return {"mode": mode, "frame": _config_frame(base_asset, configuration.get("frame", 0))}

    if mode == "dynamic":
        source = str(configuration.get("source", "images")).casefold()
        if source == "gif":
            gif_asset_id = str(configuration.get("assetId", asset_id))
            gif_asset = _imported_asset(root, gif_asset_id)
            if Path(gif_asset["importedPath"]).suffix.casefold() != ".gif":
                raise SprayError("直接播放模式只能选择 GIF 图片")
            return {
                "mode": mode,
                "source": source,
                "assetId": gif_asset_id,
                "frameDurationMs": _config_duration(configuration.get("frameDurationMs", 100)),
            }
        raw_frames = configuration.get("frames")
        if not isinstance(raw_frames, list) or not raw_frames:
            raise SprayError("动态喷漆至少需要一张图片")
        if len(raw_frames) > MAX_SPRAY_VTF_FRAMES:
            raise SprayError(f"动态喷漆最多支持 {MAX_SPRAY_VTF_FRAMES} 帧")
        frames = []
        for item in raw_frames:
            if not isinstance(item, dict):
                raise SprayError("动态喷漆帧配置无效")
            source_asset = _imported_asset(root, str(item.get("assetId", "")))
            source_asset["_absolutePath"] = str((root / source_asset["importedPath"]).resolve())
            frames.append({
                "assetId": source_asset["id"],
                "frame": _config_frame(source_asset, item.get("frame", 0)),
                "durationMs": _config_duration(item.get("durationMs", 100)),
            })
        return {"mode": mode, "source": "images", "frames": frames}

    raw_mipmaps = configuration.get("mipmaps")
    if not isinstance(raw_mipmaps, list):
        # Keep older saved configurations usable by assigning their last
        # keyframe to any newly introduced distance levels.
        legacy_keyframes = configuration.get("keyframes")
        if isinstance(legacy_keyframes, list) and legacy_keyframes:
            raw_mipmaps = [legacy_keyframes[min(index, len(legacy_keyframes) - 1)] for index in range(len(SPRAY_MIPMAP_LEVELS))]
    if not isinstance(raw_mipmaps, list) or len(raw_mipmaps) != len(SPRAY_MIPMAP_LEVELS):
        raise SprayError("渐变需要为 512、256、128、64、32 五个距离级别分别选择图片")
    mipmaps = []
    for item in raw_mipmaps:
        if not isinstance(item, dict):
            raise SprayError("渐变距离图片配置无效")
        source_asset = _imported_asset(root, str(item.get("assetId", "")))
        source_asset["_absolutePath"] = str((root / source_asset["importedPath"]).resolve())
        mipmaps.append({
            "assetId": source_asset["id"],
            "frame": _config_frame(source_asset, item.get("frame", 0)),
        })
    return {"mode": mode, "mipmaps": mipmaps}


def save_spray_configuration(root: str | Path, asset_id: str, configuration: object) -> dict:
    root_path = Path(root).resolve()
    ensure_manager_data_layout(root_path)
    normalized = _validate_spray_configuration(root_path, asset_id, configuration)
    configurations = load_spray_configurations(root_path)
    configurations[asset_id] = normalized
    _save_spray_configurations(root_path, configurations)
    return {"assetId": asset_id, "configuration": normalized}


def _normalize_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip().lstrip("/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        raise SprayError(f"喷漆文件路径不安全：{value}")
    return "/".join(path.parts).casefold()


def _manifest_pairs(content: bytes) -> list[tuple[str, str]]:
    text = content.decode("utf-8", errors="replace")
    pairs = []
    for slot, filename in _MANIFEST_PAIR.findall(text):
        if slot.casefold() in {"sprays_manifest", "manifest"}:
            continue
        try:
            pairs.append((slot.strip(), _normalize_path(filename)))
        except SprayError:
            continue
    return list(dict.fromkeys(pairs))


def _resource_path(filename: str, extension: str) -> str:
    normalized = _normalize_path(filename)
    if not normalized.endswith(extension):
        normalized = f"{normalized.rsplit('.', 1)[0]}{extension}"
    if normalized.startswith("materials/"):
        return normalized
    return f"{SPRAY_ROOT}{normalized.rsplit('/', 1)[-1]}"


def _asset_id(mod_id: str, vpk_path: str, slot: str, filename: str) -> str:
    normalized_vpk = PurePosixPath(vpk_path.replace("\\", "/"))
    if normalized_vpk.suffix.casefold() in {".vpk", ".vpk1"}:
        normalized_vpk = normalized_vpk.with_suffix(".vpk")
    value = "|".join((str(mod_id), normalized_vpk.as_posix(), slot, filename))
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:20]


def _legacy_asset_id(mod_id: str, vpk_path: str, slot: str, filename: str) -> str:
    value = "|".join((str(mod_id), vpk_path, slot, filename))
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:20]


def _imported_spray_assets(root: Path) -> list[dict]:
    imported_root = root / IMPORTED_SPRAY_DIR
    if not imported_root.is_dir():
        return []
    assets = []
    for path in sorted(imported_root.iterdir(), key=lambda item: item.name.casefold()):
        if not path.is_file() or path.suffix.casefold() not in {".png", ".gif"}:
            continue
        relative = path.relative_to(root).as_posix()
        asset_id = f"imported:{hashlib.sha1(relative.encode('utf-8')).hexdigest()[:20]}"
        display_name = path.stem.rsplit("-", 1)[0] or path.stem
        frame_count = 1
        if path.suffix.casefold() == ".gif":
            try:
                frame_count = min(MAX_SPRAY_VTF_FRAMES, _imported_frame_count(path))
            except SprayError:
                frame_count = 1
        assets.append(
            {
                "id": asset_id,
                "sourceType": "imported",
                "modId": "imported",
                "modName": f"导入 · {display_name}",
                "vpkPath": relative,
                "sourceSlot": "导入图片",
                "filename": path.name,
                "importedPath": relative,
                "preview": f"/api/spray/preview?asset={asset_id}",
                "enabled": True,
                "frameCount": frame_count,
            }
        )
    return assets


def _spray_mods(catalog: list[dict]) -> list[dict]:
    return [
        mod for mod in catalog
        if "spray" in mod.get("primaryCategories", [])
        and str(mod.get("id")) != SPRAY_COLLECTION_VPK.removesuffix(".vpk")
    ]


def _active_spray_vpk_paths(root: Path, catalog: list[dict]) -> list[str]:
    """Find every enabled spray VPK that could override the collection manifest.

    Workshop files are not always present in the catalog, and a copied VPK can
    also be missing catalog metadata after an interrupted operation.  The game
    treats ``sprays_manifest.txt`` as a shared resource, so leaving any active
    spray package mounted can hide the collection's manifest.
    """

    candidates: dict[str, Path] = {}
    for path in root.rglob("*.vpk"):
        if not path.is_file() or path.name.casefold() == SPRAY_COLLECTION_VPK.casefold():
            continue
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            continue
        candidates[relative.casefold()] = path

    active_paths: set[str] = set()
    for relative, vpk in candidates.items():
        try:
            internal_paths = read_vpk_paths(vpk)
        except (OSError, ValueError):
            continue
        if any(path.casefold() == SPRAY_MANIFEST_PATH.casefold() for path in internal_paths):
            active_paths.add(relative)

    # Keep the catalog argument in the signature so this routine remains tied
    # to the same operation boundary as the existing toggle callback.  Catalog
    # entries are useful for future metadata-based exclusions, while the
    # filesystem scan is authoritative for hidden Workshop packages.
    _ = catalog
    return sorted(active_paths)


def _disable_spray_vpk(
    root: Path,
    relative: str,
    toggle_callback,
) -> tuple[list[str], str | None]:
    """Disable one spray VPK while preserving a pre-existing ``.vpk1``.

    A previous interrupted toggle can leave both ``foo.vpk`` and
    ``foo.vpk1``.  The normal toggle API correctly refuses to overwrite the
    latter, but that would leave the active package mounted and its manifest
    could still override the collection.  Move the stale disabled copy into a
    manager backup first, then use the normal atomic toggle operation.
    """

    source = (root / relative).resolve()
    destination = source.with_suffix(".vpk1")
    if not source.is_file():
        raise SprayError(f"找不到待停用的喷漆包：{relative}")

    backup_relative: str | None = None
    if destination.exists():
        try:
            backup_root = root / SPRAY_VPK_BACKUP_DIR / uuid.uuid4().hex
            backup_target = backup_root / Path(relative)
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(destination), str(backup_target))
            backup_relative = backup_target.relative_to(root).as_posix()
        except OSError as error:
            raise SprayError(f"无法备份已存在的停用副本：{relative}") from error

    try:
        renamed = toggle_callback(root, {"vpkFiles": [relative]}, False)
    except Exception:
        if backup_relative:
            backup_target = root / backup_relative
            if backup_target.is_file() and not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(backup_target), str(destination))
        raise
    return renamed, backup_relative


def _move_loose_spray_files_to_backup(root: Path) -> list[str]:
    """Move loose standard spray files out of the game search path safely."""

    if root.name.casefold() != "addons":
        return []
    game_root = root.parent
    loose_root = game_root / "materials" / "vgui" / "logos"
    targets = [
        loose_root / f"{slot}{extension}"
        for slot in SPRAY_STANDARD_SLOTS
        for extension in (".vmt", ".vtf")
        if (loose_root / f"{slot}{extension}").is_file()
    ]
    if not targets:
        return []

    backup_root = root / SPRAY_LOOSE_BACKUP_DIR / uuid.uuid4().hex
    moved: list[str] = []
    try:
        for target in targets:
            relative = target.relative_to(game_root)
            destination = backup_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(destination))
            moved.append(relative.as_posix())
    except OSError:
        # Put already moved files back if the backup operation is interrupted.
        for relative in reversed(moved):
            source = backup_root / relative
            target = game_root / relative
            if source.is_file() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(target))
        raise
    return moved


def _find_asset(root: Path, catalog: list[dict], asset_id: str) -> dict:
    imported = next((asset for asset in _imported_spray_assets(root) if asset["id"] == asset_id), None)
    if imported:
        return imported
    for mod in _spray_mods(catalog):
        for relative_vpk in mod.get("vpkFiles", []):
            if not relative_vpk.casefold().endswith((".vpk", ".vpk1")):
                continue
            vpk = (root / relative_vpk).resolve()
            manifest = read_vpk_file(vpk, SPRAY_MANIFEST_PATH)
            if not manifest:
                continue
            for slot, filename in _manifest_pairs(manifest):
                vtf_path = _resource_path(filename, ".vtf")
                asset = {
                    "id": _asset_id(mod["id"], relative_vpk, slot, filename),
                    "sourceType": "mod",
                    "modId": mod["id"],
                    "modName": mod.get("name", mod["id"]),
                    "vpkPath": relative_vpk,
                    "slot": slot,
                    "filename": filename,
                    "vtfPath": vtf_path,
                    "vmtPath": _resource_path(filename, ".vmt"),
                }
                if asset["id"] == asset_id:
                    return asset
    raise SprayError("找不到这个喷漆资源")


def list_spray_assets(root: str | Path, catalog: list[dict]) -> dict:
    root_path = Path(root).resolve()
    ensure_manager_data_layout(root_path)
    assets: list[dict] = _imported_spray_assets(root_path)
    configurations = load_spray_configurations(root_path)
    for asset in assets:
        configuration = configurations.get(asset["id"])
        if isinstance(configuration, dict):
            asset["configuration"] = configuration
    slots: set[str] = set()
    legacy_ids: dict[str, str] = {}
    for mod in _spray_mods(catalog):
        for relative_vpk in mod.get("vpkFiles", []):
            if not relative_vpk.casefold().endswith((".vpk", ".vpk1")):
                continue
            vpk = (root_path / relative_vpk).resolve()
            manifest = read_vpk_file(vpk, SPRAY_MANIFEST_PATH)
            if not manifest:
                continue
            for slot, filename in _manifest_pairs(manifest):
                vtf_path = _resource_path(filename, ".vtf")
                if not read_vpk_file(vpk, vtf_path):
                    continue
                asset = {
                    "id": _asset_id(mod["id"], relative_vpk, slot, filename),
                    "sourceType": "mod",
                    "modId": mod["id"],
                    "modName": mod.get("name", mod["id"]),
                    "vpkPath": relative_vpk,
                    "sourceSlot": slot,
                    "filename": filename,
                    "vtfPath": vtf_path,
                    "vmtPath": _resource_path(filename, ".vmt"),
                    "preview": f"/api/spray/preview?asset={_asset_id(mod['id'], relative_vpk, slot, filename)}",
                    "enabled": mod.get("enabled") is True,
                }
                assets.append(asset)
                legacy_ids[_legacy_asset_id(mod["id"], relative_vpk, slot, filename)] = asset["id"]
                slots.add(slot)

    state = {}
    state_path = root_path / SPRAY_COLLECTION_STATE
    try:
        import json
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("assignments"), dict):
            state = payload
    except (OSError, ValueError):
        state = {}
    assignments = {
        str(slot): legacy_ids.get(str(asset_id), str(asset_id))
        for slot, asset_id in state.get("assignments", {}).items()
    }
    return {
        "assets": assets,
        "slots": sorted(slots, key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value.casefold())),
        "assignments": assignments,
        "collectionVpk": SPRAY_COLLECTION_VPK,
    }


def _rgb565(value: int) -> tuple[int, int, int]:
    return (
        ((value >> 11) & 0x1F) * 255 // 31,
        ((value >> 5) & 0x3F) * 255 // 63,
        (value & 0x1F) * 255 // 31,
    )


def _decode_dxt1(data: bytes, width: int, height: int) -> bytes:
    output = bytearray(width * height * 4)
    for block_y in range((height + 3) // 4):
        for block_x in range((width + 3) // 4):
            offset = (block_y * ((width + 3) // 4) + block_x) * 8
            color0, color1, indices = struct.unpack_from("<HHI", data, offset)
            colors = list(map(_rgb565, (color0, color1)))
            if color0 > color1:
                colors.extend(
                    (
                        tuple((2 * colors[0][i] + colors[1][i]) // 3 for i in range(3)),
                        tuple((colors[0][i] + 2 * colors[1][i]) // 3 for i in range(3)),
                    )
                )
                alphas = [255] * 4
            else:
                colors.append(tuple((colors[0][i] + colors[1][i]) // 2 for i in range(3)))
                colors.append((0, 0, 0))
                alphas = [255, 255, 255, 0]
            for local_y in range(4):
                for local_x in range(4):
                    x, y = block_x * 4 + local_x, block_y * 4 + local_y
                    if x >= width or y >= height:
                        continue
                    color_index = (indices >> (2 * (local_y * 4 + local_x))) & 3
                    target = (y * width + x) * 4
                    output[target:target + 4] = bytes((*colors[color_index], alphas[color_index]))
    return bytes(output)


def _decode_dxt5(data: bytes, width: int, height: int) -> bytes:
    output = bytearray(width * height * 4)
    for block_y in range((height + 3) // 4):
        for block_x in range((width + 3) // 4):
            offset = (block_y * ((width + 3) // 4) + block_x) * 16
            alpha0, alpha1 = data[offset], data[offset + 1]
            alpha_bits = int.from_bytes(data[offset + 2:offset + 8], "little")
            alpha_values = [alpha0, alpha1]
            if alpha0 > alpha1:
                alpha_values.extend(
                    ((6 - index) * alpha0 + index * alpha1) // 7
                    for index in range(1, 7)
                )
            else:
                alpha_values.extend(
                    ((4 - index) * alpha0 + index * alpha1) // 5
                    for index in range(1, 5)
                )
                alpha_values.extend((0, 255))

            color_offset = offset + 8
            color0, color1, color_indices = struct.unpack_from("<HHI", data, color_offset)
            colors = [_rgb565(color0), _rgb565(color1)]
            colors.extend(
                (
                    tuple((2 * colors[0][channel] + colors[1][channel]) // 3 for channel in range(3)),
                    tuple((colors[0][channel] + 2 * colors[1][channel]) // 3 for channel in range(3)),
                )
            )
            for local_y in range(4):
                for local_x in range(4):
                    x, y = block_x * 4 + local_x, block_y * 4 + local_y
                    if x >= width or y >= height:
                        continue
                    pixel_index = local_y * 4 + local_x
                    color_index = (color_indices >> (2 * pixel_index)) & 3
                    alpha_index = (alpha_bits >> (3 * pixel_index)) & 7
                    target = (y * width + x) * 4
                    output[target:target + 4] = bytes((*colors[color_index], alpha_values[alpha_index]))
    return bytes(output)


def _decode_dxt3(data: bytes, width: int, height: int) -> bytes:
    """Decode DXT3 blocks, which store explicit 4-bit alpha values."""

    output = bytearray(width * height * 4)
    blocks_wide = (width + 3) // 4
    for block_y in range((height + 3) // 4):
        for block_x in range(blocks_wide):
            offset = (block_y * blocks_wide + block_x) * 16
            alpha_data = data[offset:offset + 8]
            color0, color1, color_indices = struct.unpack_from("<HHI", data, offset + 8)
            colors = [_rgb565(color0), _rgb565(color1)]
            colors.extend(
                (
                    tuple((2 * colors[0][channel] + colors[1][channel]) // 3 for channel in range(3)),
                    tuple((colors[0][channel] + 2 * colors[1][channel]) // 3 for channel in range(3)),
                )
            )
            alpha_bits = int.from_bytes(alpha_data, "little")
            for local_y in range(4):
                for local_x in range(4):
                    x, y = block_x * 4 + local_x, block_y * 4 + local_y
                    if x >= width or y >= height:
                        continue
                    pixel_index = local_y * 4 + local_x
                    color_index = (color_indices >> (2 * pixel_index)) & 3
                    alpha = ((alpha_bits >> (4 * pixel_index)) & 0xF) * 17
                    target = (y * width + x) * 4
                    output[target:target + 4] = bytes((*colors[color_index], alpha))
    return bytes(output)


def _mip_size(image_format: int, width: int, height: int) -> int:
    if image_format in {13}:
        return ((width + 3) // 4) * ((height + 3) // 4) * 8
    if image_format in {14, 15}:
        return ((width + 3) // 4) * ((height + 3) // 4) * 16
    if image_format in {0, 1, 11, 12}:
        return width * height * 4
    if image_format in {2, 3}:
        return width * height * 3
    if image_format in {4, 5, 8}:
        return width * height * (2 if image_format == 5 else 1)
    if image_format == 6:
        return width * height * 2
    raise SprayError(f"暂不支持的 VTF 图像格式：{image_format}")


def _decode_vtf(data: bytes) -> tuple[int, int, bytes]:
    if len(data) < 64 or data[:4] != b"VTF\x00":
        raise SprayError("不是有效的 VTF 文件")
    header_size = struct.unpack_from("<I", data, 12)[0]
    width, height = struct.unpack_from("<HH", data, 16)
    frame_count = max(1, struct.unpack_from("<H", data, 24)[0])
    image_format = struct.unpack_from("<I", data, 52)[0]
    mip_count = max(1, data[56])
    low_format = struct.unpack_from("<I", data, 57)[0]
    low_width, low_height = data[61], data[62]
    offset = header_size
    if low_width and low_height and low_format != 0xFFFFFFFF:
        offset += _mip_size(low_format, low_width, low_height)
    for mip_level in range(mip_count - 1, 0, -1):
        mip_width = max(1, width >> mip_level)
        mip_height = max(1, height >> mip_level)
        offset += _mip_size(image_format, mip_width, mip_height) * frame_count
    size = _mip_size(image_format, width, height)
    pixels = data[offset:offset + size]
    if len(pixels) != size:
        raise SprayError("VTF 图像数据不完整")
    if image_format == 13:
        decoded = _decode_dxt1(pixels, width, height)
    elif image_format in {0, 1, 2, 3, 4, 5, 6, 8, 11, 12}:
        decoded = bytearray(width * height * 4)
        for index in range(width * height):
            if image_format in {0, 1, 11, 12}:
                value = pixels[index * 4:index * 4 + 4]
                if image_format == 0:
                    rgba = value
                elif image_format == 1:
                    rgba = (value[3], value[0], value[1], value[2])
                elif image_format == 11:
                    rgba = (value[1], value[2], value[3], value[0])
                else:
                    rgba = (value[2], value[1], value[0], value[3])
            elif image_format in {2, 3}:
                value = pixels[index * 3:index * 3 + 3]
                rgba = (*value, 255) if image_format == 2 else (value[2], value[1], value[0], 255)
            elif image_format == 4:
                value = struct.unpack_from("<H", pixels, index * 2)[0]
                rgba = (*_rgb565(value), 255)
            elif image_format == 5:
                value = pixels[index]
                rgba = (value, value, value, 255)
            elif image_format == 6:
                value, alpha = pixels[index * 2:index * 2 + 2]
                rgba = (value, value, value, alpha)
            else:
                value = pixels[index]
                rgba = (255, 255, 255, value)
            decoded[index * 4:index * 4 + 4] = bytes(rgba)
    elif image_format == 14:
        decoded = _decode_dxt3(pixels, width, height)
    elif image_format == 15:
        decoded = _decode_dxt5(pixels, width, height)
    else:
        raise SprayError(f"暂不支持的 VTF 图像格式：{image_format}")
    return width, height, bytes(decoded)


def _png(width: int, height: int, pixels: bytes) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    rows = b"".join(b"\x00" + pixels[row * width * 4:(row + 1) * width * 4] for row in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b"")


def _spray_preview_cache_path(root: Path, asset: dict) -> Path:
    source = (root / asset["vpkPath"]).resolve()
    try:
        stat = source.stat()
        stamp = f"{stat.st_mtime_ns}:{stat.st_size}"
    except OSError:
        stamp = "missing"
    cache_key = hashlib.sha1(f"{asset['id']}|{stamp}".encode("utf-8")).hexdigest()
    return root / SPRAY_PREVIEW_CACHE_DIR / f"{cache_key}.png"


def spray_preview_asset(root: str | Path, asset: dict) -> bytes:
    root_path = Path(root).resolve()
    ensure_manager_data_layout(root_path)
    if asset.get("sourceType") == "imported":
        imported_path = (root_path / str(asset.get("importedPath", ""))).resolve()
        if imported_path.is_file() and root_path in imported_path.parents:
            return imported_path.read_bytes()
        raise SprayError("找不到导入的喷漆图片")
    cache_path = _spray_preview_cache_path(root_path, asset)
    try:
        return cache_path.read_bytes()
    except OSError:
        pass
    vpk = (root_path / asset["vpkPath"]).resolve()
    content = read_vpk_file(vpk, asset["vtfPath"])
    if not content:
        raise SprayError("找不到喷漆图像文件")
    width, height, pixels = _decode_vtf(content)
    preview = _png(width, height, pixels)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(preview)
    except OSError:
        pass
    return preview


def spray_preview_frame(root: str | Path, asset: dict, frame: int = 0) -> bytes:
    """Return one frame of an imported image for the configuration preview."""
    if asset.get("sourceType") != "imported":
        return spray_preview_asset(root, asset)
    root_path = Path(root).resolve()
    imported_path = (root_path / str(asset.get("importedPath", ""))).resolve()
    if not imported_path.is_file() or root_path not in imported_path.parents:
        raise SprayError("找不到导入的喷漆图片")
    try:
        from PIL import Image
    except ImportError as error:
        raise SprayError("预览 GIF 需要 Pillow 支持") from error
    try:
        with Image.open(imported_path) as image:
            frame_count = max(1, int(getattr(image, "n_frames", 1)))
            image.seek(max(0, min(int(frame), frame_count - 1)))
            rgba = image.convert("RGBA")
            return _png(rgba.width, rgba.height, rgba.tobytes())
    except (OSError, ValueError, EOFError) as error:
        raise SprayError("无法读取导入喷漆的预览帧") from error


def spray_preview(root: str | Path, catalog: list[dict], asset_id: str) -> bytes:
    root_path = Path(root).resolve()
    return spray_preview_asset(root_path, _find_asset(root_path, catalog, asset_id))


def _rewrite_vmt(content: bytes | None, slot: str) -> bytes:
    value = content.decode("utf-8", errors="replace") if content else (
        '"LightmappedGeneric"\n'
        '{\n'
        f'\t"$basetexture" "vgui/logos/{slot}"\n'
        '\t"$translucent" "1"\n'
        '\t"$decal" "1"\n'
        '\t"$decalscale" "0.250"\n'
        '}'
    )
    replacement = f'\\1vgui/logos/{slot}\\2'
    value, count = _BASE_TEXTURE.subn(replacement, value, count=1)
    if count == 0:
        value = (
            '"LightmappedGeneric"\n'
            '{\n'
            f'\t"$basetexture" "vgui/logos/{slot}"\n'
            '\t"$translucent" "1"\n'
            '\t"$decal" "1"\n'
            '\t"$decalscale" "0.250"\n'
            '}'
        )
    return value.encode("utf-8")


def _dynamic_imported_spray_vmt(slot: str, frame_rate: float = 10.0) -> bytes:
    """Create the material proxy that advances a multi-frame spray texture."""
    frame_rate_text = f"{max(0.2, min(50.0, frame_rate)):.6g}"
    return (
        '"UnlitGeneric"\n'
        '{\n'
        '\t"$translucent" 1\n'
        f'\t"$basetexture" "vgui/logos/{slot}"\n'
        '\t"$vertexcolor" 1\n'
        '\t"$vertexalpha" 1\n'
        '\t"$no_fullbright" 1\n'
        '\t"$ignorez" 1\n'
        '\t"Proxies"\n'
        '\t{\n'
        '\t\t"AnimatedTexture"\n'
        '\t\t{\n'
        '\t\t\t"animatedTextureVar" "$basetexture"\n'
        '\t\t\t"animatedTextureFrameNumVar" "$frame"\n'
        f'\t\t\t"animatedTextureFrameRate" "{frame_rate_text}"\n'
        '\t\t}\n'
        '\t}\n'
        '}\n'
    ).encode("ascii")


def _encode_imported_gif_vtf(path: Path) -> tuple[bytes, float]:
    """Encode a GIF using the website-compatible multi-frame VTF layout."""

    try:
        from gif_to_vtf import encode_frames_to_vtf_bytes
        frames, durations = _load_imported_gif_frames(path)
        frames, tick = _expand_timed_frames_with_tick(frames, durations)
        return encode_frames_to_vtf_bytes(frames), 1000 / tick
    except (ImportError, OSError, ValueError) as error:
        raise SprayError(f"生成动态喷漆失败：{error}") from error


def _fit_spray_frame(image, max_dimension=MAX_SPRAY_VTF_DIMENSION):
    from PIL import Image

    image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    if not image.width or not image.height:
        raise SprayError("导入图片尺寸无效")
    side = 1
    while side < max(image.size):
        side *= 2
    side = max(32, min(max_dimension, side))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(image, ((side - image.width) // 2, (side - image.height) // 2))
    return canvas


def _prepare_imported_spray_frames(path: Path) -> list:
    try:
        from PIL import Image
    except ImportError as error:
        raise SprayError("导入图片需要 Pillow 图像组件") from error
    try:
        with Image.open(path) as source:
            frame_count = max(1, int(getattr(source, "n_frames", 1)))
            if frame_count > MAX_SPRAY_VTF_FRAMES:
                raise SprayError(f"GIF 帧数过多，最多支持 {MAX_SPRAY_VTF_FRAMES} 帧")
            max_dimension = (
                MAX_ANIMATED_SPRAY_VTF_DIMENSION
                if path.suffix.casefold() == ".gif"
                else MAX_SPRAY_VTF_DIMENSION
            )
            frames = []
            for frame_index in range(frame_count):
                source.seek(frame_index)
                frames.append(_fit_spray_frame(source.convert("RGBA"), max_dimension))
            return frames
    except SprayError:
        raise
    except (OSError, EOFError) as error:
        raise SprayError(f"无法读取导入图片：{path.name}") from error


def _load_imported_frame(path: Path, frame_index: int):
    from PIL import Image

    try:
        with Image.open(path) as image:
            image.seek(frame_index)
            return image.convert("RGBA").copy()
    except (OSError, EOFError, ValueError) as error:
        raise SprayError(f"无法读取图片帧：{path.name}") from error


def _load_imported_gif_frames(path: Path) -> tuple[list, list[int]]:
    from PIL import Image

    frames = []
    durations = []
    try:
        with Image.open(path) as image:
            count = max(1, int(getattr(image, "n_frames", 1)))
            for frame_index in range(count):
                image.seek(frame_index)
                frames.append(image.convert("RGBA").copy())
                raw_duration = image.info.get("duration", 100)
                durations.append(_config_duration(raw_duration if raw_duration and int(raw_duration) > 0 else 100))
    except (OSError, EOFError, ValueError) as error:
        raise SprayError(f"无法读取 GIF：{path.name}") from error
    return frames, durations


def _expand_timed_frames(frames: list, durations: list[int]) -> list:
    expanded, _ = _expand_timed_frames_with_tick(frames, durations)
    return expanded


def _expand_timed_frames_with_tick(frames: list, durations: list[int]) -> tuple[list, int]:
    if not frames or len(frames) != len(durations):
        raise SprayError("动态喷漆帧数据不完整")
    tick = durations[0]
    for duration in durations[1:]:
        tick = math.gcd(tick, duration)
    tick = max(MIN_CONFIG_DURATION_MS, min(100, tick))
    repeats = [max(1, round(duration / tick)) for duration in durations]
    total = sum(repeats)
    if total > MAX_SPRAY_VTF_FRAMES:
        scale = MAX_SPRAY_VTF_FRAMES / total
        repeats = [max(1, round(value * scale)) for value in repeats]
    expanded = []
    for frame, repeat in zip(frames, repeats):
        expanded.extend([frame] * repeat)
    if len(expanded) > MAX_SPRAY_VTF_FRAMES:
        expanded = expanded[:MAX_SPRAY_VTF_FRAMES]
    return expanded, tick


def _configured_spray_frame_data(root: Path, configuration: dict) -> tuple[list, int]:
    """Return encoded frames and the millisecond tick used by the VMT proxy."""
    mode = configuration["mode"]
    if mode == "dynamic" and configuration.get("source") == "gif":
        asset = _imported_asset(root, configuration["assetId"])
        frames, _ = _load_imported_gif_frames((root / asset["importedPath"]).resolve())
        duration = configuration["frameDurationMs"]
        return _expand_timed_frames_with_tick(frames, [duration] * len(frames))

    def load_frame(item: dict):
        asset = _imported_asset(root, item["assetId"])
        return _load_imported_frame((root / asset["importedPath"]).resolve(), item["frame"])

    if mode == "dynamic":
        frame_items = configuration["frames"]
        frames = [load_frame(item) for item in frame_items]
        durations = [item["durationMs"] for item in frame_items]
        return _expand_timed_frames_with_tick(frames, durations)
    raise SprayError("渐变喷漆应使用距离 mipmap 配置")


def _configured_spray_frames(root: Path, configuration: dict) -> list:
    return _configured_spray_frame_data(root, configuration)[0]


def _configured_spray_mipmaps(root: Path, configuration: dict) -> list:
    """Load one selected image for each distance mipmap level."""

    from PIL import Image

    mipmaps = []
    for size, item in zip(SPRAY_MIPMAP_LEVELS, configuration["mipmaps"]):
        asset = _imported_asset(root, item["assetId"])
        source = _load_imported_frame((root / asset["importedPath"]).resolve(), item["frame"])
        fitted = _fit_spray_frame(source, MAX_SPRAY_VTF_DIMENSION)
        if fitted.size != (MAX_SPRAY_VTF_DIMENSION, MAX_SPRAY_VTF_DIMENSION):
            fitted = fitted.resize((MAX_SPRAY_VTF_DIMENSION, MAX_SPRAY_VTF_DIMENSION), Image.Resampling.LANCZOS)
        mipmaps.append(fitted.resize((size, size), Image.Resampling.LANCZOS) if size != MAX_SPRAY_VTF_DIMENSION else fitted)
    return mipmaps


def _encode_gradient_vtf(root: Path, configuration: dict) -> bytes:
    """Encode a distance-based spray as one-frame DXT1 mipmaps."""

    mipmaps = _configured_spray_mipmaps(root, configuration)
    image_data = b"".join(_encode_dxt1(image) for image in reversed(mipmaps))
    header = bytearray(64)
    struct.pack_into("<4sII", header, 0, b"VTF\x00", 7, 1)
    struct.pack_into("<I", header, 12, 64)
    struct.pack_into("<HH", header, 16, MAX_SPRAY_VTF_DIMENSION, MAX_SPRAY_VTF_DIMENSION)
    # Match the known-working website VTF: DXT1 with the standard spray flags.
    # ONEBITALPHA (0x1000) is not present in the reference file and can change
    # how the engine treats the texture's alpha channel.
    struct.pack_into("<I", header, 20, 0x220C)
    struct.pack_into("<H", header, 24, 1)
    struct.pack_into("<I", header, 52, 13)
    header[56] = len(SPRAY_MIPMAP_LEVELS)
    struct.pack_into("<I", header, 57, 13)
    header[63] = 1
    return bytes(header) + image_data


def _pack_rgb565(color: tuple[int, int, int]) -> int:
    red, green, blue = color
    return (
        ((red * 31 + 127) // 255) << 11
        | ((green * 63 + 127) // 255) << 5
        | ((blue * 31 + 127) // 255)
    )


def _dxt1_block(pixels: list[tuple[int, int, int, int]]) -> bytes:
    transparent = any(alpha < 128 for _, _, _, alpha in pixels)
    opaque_pixels = [(red, green, blue) for red, green, blue, alpha in pixels if alpha >= 128]
    if not opaque_pixels:
        return struct.pack("<HHI", 0, 0, 0xFFFFFFFF)

    low = tuple(min(pixel[channel] for pixel in opaque_pixels) for channel in range(3))
    high = tuple(max(pixel[channel] for pixel in opaque_pixels) for channel in range(3))
    low_endpoint = _pack_rgb565(low)
    high_endpoint = _pack_rgb565(high)
    if transparent:
        color0, color1 = sorted((low_endpoint, high_endpoint))
    else:
        color0, color1 = max(low_endpoint, high_endpoint), min(low_endpoint, high_endpoint)
        if color0 == color1:
            color0 = min(0xFFFF, color0 + 1)
            color1 = max(0, color1 - 1)

    palette = [_rgb565(color0), _rgb565(color1)]
    if color0 > color1:
        palette.extend(
            (
                tuple((2 * palette[0][index] + palette[1][index]) // 3 for index in range(3)),
                tuple((palette[0][index] + 2 * palette[1][index]) // 3 for index in range(3)),
            )
        )
    else:
        palette.extend(
            (
                tuple((palette[0][index] + palette[1][index]) // 2 for index in range(3)),
                (0, 0, 0),
            )
        )

    indices = 0
    for pixel_index, (red, green, blue, alpha) in enumerate(pixels):
        if transparent and alpha < 128:
            palette_index = 3
        else:
            palette_index = min(
                range(3 if color0 <= color1 else 4),
                key=lambda index: sum((value - target) ** 2 for value, target in zip((red, green, blue), palette[index])),
            )
        indices |= palette_index << (pixel_index * 2)
    return struct.pack("<HHI", color0, color1, indices)


def _encode_dxt1(image) -> bytes:
    width, height = image.size
    pixels = list(image.getdata())
    blocks = bytearray()
    for block_y in range(0, height, 4):
        for block_x in range(0, width, 4):
            block = []
            for local_y in range(4):
                for local_x in range(4):
                    x = min(width - 1, block_x + local_x)
                    y = min(height - 1, block_y + local_y)
                    block.append(pixels[y * width + x])
            blocks.extend(_dxt1_block(block))
    return bytes(blocks)


def _dxt5_alpha_block(pixels: list[tuple[int, int, int, int]]) -> bytes:
    """Encode the alpha portion of one DXT5 block."""

    alphas = [pixel[3] for pixel in pixels]
    alpha0 = max(alphas)
    alpha1 = min(alphas)
    if alpha0 == alpha1:
        if alpha0 < 255:
            alpha0 += 1
        else:
            alpha1 -= 1

    palette = [alpha0, alpha1]
    if alpha0 > alpha1:
        palette.extend((
            ((7 - index) * alpha0 + index * alpha1) // 7
            for index in range(1, 7)
        ))
    else:
        palette.extend((
            ((5 - index) * alpha0 + index * alpha1) // 5
            for index in range(1, 5)
        ))
        palette.extend((0, 255))

    indices = 0
    for pixel_index, alpha in enumerate(alphas):
        alpha_index = min(
            range(8),
            key=lambda index: abs(alpha - palette[index]),
        )
        indices |= alpha_index << (pixel_index * 3)
    return bytes((alpha0, alpha1)) + indices.to_bytes(6, "little")


def _dxt5_color_block(pixels: list[tuple[int, int, int, int]]) -> bytes:
    """Encode the always-opaque RGB portion of one DXT5 block."""

    colors = [(red, green, blue) for red, green, blue, _ in pixels]
    low = tuple(min(pixel[channel] for pixel in colors) for channel in range(3))
    high = tuple(max(pixel[channel] for pixel in colors) for channel in range(3))
    color0 = _pack_rgb565(high)
    color1 = _pack_rgb565(low)
    if color0 <= color1:
        color0, color1 = max(color0, color1), min(color0, color1)
        if color0 == color1:
            color0 = min(0xFFFF, color0 + 1)
            color1 = max(0, color1 - 1)

    palette = [_rgb565(color0), _rgb565(color1)]
    palette.extend(
        tuple((2 * palette[0][index] + palette[1][index]) // 3 for index in range(3))
        for _ in (0,)
    )
    palette.append(
        tuple((palette[0][index] + 2 * palette[1][index]) // 3 for index in range(3))
    )
    indices = 0
    for pixel_index, color in enumerate(colors):
        color_index = min(
            range(4),
            key=lambda index: sum(
                (value - target) ** 2
                for value, target in zip(color, palette[index])
            ),
        )
        indices |= color_index << (pixel_index * 2)
    return struct.pack("<HHI", color0, color1, indices)


def _dxt5_block(pixels: list[tuple[int, int, int, int]]) -> bytes:
    return _dxt5_alpha_block(pixels) + _dxt5_color_block(pixels)


def _encode_dxt5(image) -> bytes:
    width, height = image.size
    pixels = list(image.getdata())
    blocks = bytearray()
    for block_y in range(0, height, 4):
        for block_x in range(0, width, 4):
            block = []
            for local_y in range(4):
                for local_x in range(4):
                    x = min(width - 1, block_x + local_x)
                    y = min(height - 1, block_y + local_y)
                    block.append(pixels[y * width + x])
            blocks.extend(_dxt5_block(block))
    return bytes(blocks)


def _encode_imported_vtf(path: Path, frame_index: int | None = None) -> bytes:
    from PIL import Image

    frames = _prepare_imported_spray_frames(path)
    if frame_index is not None:
        if frame_index < 0 or frame_index >= len(frames):
            raise SprayError(f"图片帧编号超出范围：{path.name}")
        frames = [frames[frame_index]]
    frame_mipmaps = []
    for frame in frames:
        mipmaps = [frame]
        while mipmaps[-1].width > MIN_SPRAY_MIP_DIMENSION:
            current = mipmaps[-1]
            next_size = (current.width // 2, current.height // 2)
            mipmaps.append(current.resize(next_size, Image.Resampling.LANCZOS))
        frame_mipmaps.append(mipmaps)
    width, height = frames[0].size
    lowres = frames[0].resize((16, 16), Image.Resampling.LANCZOS)
    image_data = _encode_dxt1(lowres) + b"".join(
        _encode_dxt5(frame_mipmaps[frame_index][mip_index])
        for mip_index in range(len(frame_mipmaps[0]) - 1, -1, -1)
        for frame_index in range(len(frame_mipmaps))
    )

    # Match the VTF 7.2 layout emitted by the working spray conversion tool.
    header = bytearray(80)
    struct.pack_into("<4sII", header, 0, b"VTF\x00", 7, 2)
    struct.pack_into("<I", header, 12, 80)
    struct.pack_into("<HH", header, 16, width, height)
    struct.pack_into("<I", header, 20, 0x220C)
    struct.pack_into("<HH", header, 24, len(frames), 0)
    struct.pack_into("<3f", header, 32, 0.0, 0.0, 0.0)
    struct.pack_into("<fI", header, 48, 0.0, 15)
    header[56] = len(mipmaps)
    struct.pack_into("<I", header, 57, 13)
    header[61] = 16
    header[62] = 16
    header[63] = 1
    return bytes(header) + image_data


def import_spray_images(root: str | Path, images: list[dict]) -> dict:
    root_path = Path(root).resolve()
    ensure_manager_data_layout(root_path)
    imported_root = root_path / IMPORTED_SPRAY_DIR
    imported_root.mkdir(parents=True, exist_ok=True)
    if not isinstance(images, list) or not images:
        raise SprayError("请至少选择一张图片")
    if len(images) > 100:
        raise SprayError("一次最多导入 100 张图片")
    try:
        from PIL import Image
    except ImportError as error:
        raise SprayError("导入图片需要 Pillow 图像组件") from error
    imported = []
    skipped = []
    for item in images:
        if not isinstance(item, dict):
            raise SprayError("导入图片数据无效")
        name = Path(str(item.get("name", ""))).name
        if Path(name).suffix.casefold() not in IMPORTED_IMAGE_EXTENSIONS:
            raise SprayError(f"不支持的喷漆图片格式：{name}")
        encoded = str(item.get("data", ""))
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as error:
            raise SprayError(f"图片数据无效：{name}") from error
        if not raw or len(raw) > MAX_IMPORTED_IMAGE_BYTES:
            raise SprayError(f"图片大小无效：{name}")
        try:
            with Image.open(io.BytesIO(raw)) as image:
                image.verify()
        except (OSError, ValueError) as error:
            raise SprayError(f"无法读取图片：{name}") from error
        digest = hashlib.sha1(raw).hexdigest()
        stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff _.-]+", "_", Path(name).stem).strip(" .") or "imported-spray"
        source_extension = Path(name).suffix.casefold()
        destination = imported_root / f"{stem}-{digest[:10]}{'.gif' if source_extension == '.gif' else '.png'}"
        if destination.exists():
            skipped.append(destination.name)
            continue
        try:
            if source_extension == ".gif":
                with Image.open(io.BytesIO(raw)) as image:
                    frame_count = max(1, int(getattr(image, "n_frames", 1)))
                    if frame_count > MAX_SPRAY_VTF_FRAMES:
                        raise SprayError(f"GIF 帧数过多，最多支持 {MAX_SPRAY_VTF_FRAMES} 帧")
                    for frame_index in range(frame_count):
                        image.seek(frame_index)
                        image.convert("RGBA")
                destination.write_bytes(raw)
            else:
                with Image.open(io.BytesIO(raw)) as image:
                    image.seek(0)
                    image = image.convert("RGBA")
                    image.thumbnail((MAX_IMPORTED_IMAGE_DIMENSION, MAX_IMPORTED_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
                    image.save(destination, format="PNG")
        except SprayError:
            raise
        except (OSError, EOFError) as error:
            raise SprayError(f"保存图片失败：{name}") from error
        imported.append(destination.name)
    return {"imported": imported, "skipped": skipped}


def delete_imported_spray(
    root: str | Path,
    asset_id: str,
    recycle_callback=None,
) -> dict:
    root_path = Path(root).resolve()
    ensure_manager_data_layout(root_path)
    asset = next((item for item in _imported_spray_assets(root_path) if item["id"] == asset_id), None)
    if asset is None:
        raise SprayError("找不到这个导入的喷漆图片")
    imported_root = (root_path / IMPORTED_SPRAY_DIR).resolve()
    target = (root_path / asset["importedPath"]).resolve()
    try:
        relative_target = target.relative_to(imported_root)
    except ValueError as error:
        raise SprayError("导入喷漆路径无效") from error
    if len(relative_target.parts) != 1 or not target.is_file():
        raise SprayError("这个导入的喷漆图片不存在")
    if recycle_callback is not None:
        recycle_callback([target])
    else:
        target.unlink()

    configurations = load_spray_configurations(root_path)
    removed_configurations = []
    for configured_id, configuration in configurations.items():
        references = {configured_id}
        if configuration.get("mode") == "dynamic":
            if configuration.get("source") == "gif":
                references.add(str(configuration.get("assetId", "")))
            references.update(str(item.get("assetId", "")) for item in configuration.get("frames", []) if isinstance(item, dict))
        elif configuration.get("mode") == "gradient":
            references.update(str(item.get("assetId", "")) for item in configuration.get("mipmaps", []) if isinstance(item, dict))
            references.update(str(item.get("assetId", "")) for item in configuration.get("keyframes", []) if isinstance(item, dict))
        if asset_id in references:
            removed_configurations.append(configured_id)
    if removed_configurations:
        for configured_id in removed_configurations:
            configurations.pop(configured_id, None)
        _save_spray_configurations(root_path, configurations)

    state_path = root_path / SPRAY_COLLECTION_STATE
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    assignments = payload.get("assignments", {}) if isinstance(payload, dict) else {}
    if not isinstance(assignments, dict):
        assignments = {}
    cleared_slots = [str(slot) for slot, assigned_id in assignments.items() if str(assigned_id) == asset_id]
    payload = {"assignments": {str(slot): assigned_id for slot, assigned_id in assignments.items() if str(assigned_id) != asset_id}}
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"deleted": asset["filename"], "clearedSlots": cleared_slots, "recycled": recycle_callback is not None}


def apply_spray_collection(
    root: str | Path,
    catalog: list[dict],
    assignments: dict[str, str],
    toggle_callback=None,
) -> dict:
    root_path = Path(root).resolve()
    ensure_manager_data_layout(root_path)
    assignments = {str(slot): str(asset_id) for slot, asset_id in assignments.items() if str(slot).strip() and str(asset_id).strip()}
    if not assignments:
        raise SprayError("请至少选择一张喷漆")
    entries: dict[str, bytes] = {}
    resolved = {}
    configurations = load_spray_configurations(root_path)
    for slot, asset_id in assignments.items():
        slot_name = _normalize_path(slot).rsplit("/", 1)[-1]
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", slot_name):
            raise SprayError(f"喷漆槽位名称无效：{slot}")
        if slot_name not in SPRAY_STANDARD_SLOTS:
            raise SprayError(f"目标喷漆槽位只能是 1-16：{slot}")
        asset = _find_asset(root_path, catalog, asset_id)
        if asset.get("sourceType") == "imported":
            imported_path = (root_path / asset["importedPath"]).resolve()
            configuration = configurations.get(asset_id)
            if isinstance(configuration, dict):
                configuration = _validate_spray_configuration(root_path, asset_id, configuration)
            if configuration and configuration["mode"] == "static":
                vtf = _encode_imported_vtf(imported_path, configuration["frame"])
                vmt = None
            elif configuration and configuration["mode"] == "dynamic":
                from gif_to_vtf import encode_frames_to_vtf_bytes
                frames, tick = _configured_spray_frame_data(root_path, configuration)
                vtf = encode_frames_to_vtf_bytes(frames)
                vmt = _dynamic_imported_spray_vmt(slot_name, 1000 / tick)
            elif configuration and configuration["mode"] == "gradient":
                try:
                    vtf = _encode_gradient_vtf(root_path, configuration)
                except (ImportError, OSError, ValueError) as error:
                    raise SprayError(f"生成渐变喷漆失败：{error}") from error
                # A gradient is selected by VTF mipmaps as distance changes;
                # AnimatedTexture would incorrectly treat it as a time animation.
                vmt = None
            else:
                if Path(asset["importedPath"]).suffix.casefold() == ".gif":
                    vtf, frame_rate = _encode_imported_gif_vtf(imported_path)
                    vmt = _dynamic_imported_spray_vmt(slot_name, frame_rate)
                else:
                    vtf = _encode_imported_vtf(imported_path)
                    vmt = None
        else:
            vpk = (root_path / asset["vpkPath"]).resolve()
            vtf = read_vpk_file(vpk, asset["vtfPath"])
            if not vtf:
                raise SprayError(f"找不到喷漆文件：{asset['filename']}")
            vmt = read_vpk_file(vpk, asset["vmtPath"])
        entries[f"{SPRAY_ROOT}{slot_name}.vtf"] = vtf
        entries[f"{SPRAY_ROOT}{slot_name}.vmt"] = _rewrite_vmt(vmt, slot_name)
        resolved[slot_name] = asset_id
    manifest = "sprays_manifest\n{\n" + "".join(
        f'\t"{slot}"\t"{slot}.vtf"\n' for slot in sorted(resolved, key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value.casefold()))
    ) + "}\n"
    entries[SPRAY_MANIFEST_PATH] = manifest.encode("utf-8")
    entries["addoninfo.txt"] = b'"AddonInfo"\n{\n\taddontitle "L4D2 Mod Manager Spray Collection"\n\taddonContent_Spray "1"\n}\n'

    output = root_path / SPRAY_COLLECTION_VPK
    with tempfile.NamedTemporaryFile(prefix="spray-collection-", suffix=".vpk", dir=root_path, delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        write_vpk_entries(temporary_path, entries)
        temporary_path.replace(output)
    finally:
        temporary_path.unlink(missing_ok=True)

    loose_files_moved = _move_loose_spray_files_to_backup(root_path)

    disabled_vpk_files: list[str] = []
    if toggle_callback is not None:
        # A second sprays_manifest.txt can replace the collection manifest at
        # load time. Disable every active source package, including Workshop
        # files hidden from the catalog and packages with stale metadata.
        active_paths = _active_spray_vpk_paths(root_path, catalog)
        vpk_backups: list[str] = []
        for relative in active_paths:
            disabled, backup_relative = _disable_spray_vpk(root_path, relative, toggle_callback)
            disabled_vpk_files.extend(disabled)
            if backup_relative:
                vpk_backups.append(backup_relative)
    else:
        vpk_backups = []
    import json
    (root_path / SPRAY_COLLECTION_STATE).write_text(
        json.dumps({"assignments": resolved}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "vpk": SPRAY_COLLECTION_VPK,
        "assignments": resolved,
        "looseFilesMoved": loose_files_moved,
        "disabledVpkFiles": disabled_vpk_files,
        "vpkBackups": vpk_backups,
    }


def reset_spray_state(root: str | Path) -> None:
    import json

    ensure_manager_data_layout(root)
    state_path = Path(root).resolve() / SPRAY_COLLECTION_STATE
    state_path.write_text(
        json.dumps({"assignments": {}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
