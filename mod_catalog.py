"""Build a view model that associates Mod preview images with VPK files."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path

from vpk_detector import (
    VPKClassificationError,
    VPKFormatError,
    analyze_vpk_paths,
    read_vpk_addon_title,
    read_vpk_paths,
)
from nekovpk import NekoVPKError, inspect_nekovpk
from voice_replacement import detect_voice_replacement_mode, detect_voice_roles


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VPK_EXTENSIONS = {".vpk", ".vpk1"}
GENERATED_SPRAY_VPK = "l4d2modmanager_spraycollection.vpk"
ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar"}
IGNORED_DATA_DIRECTORIES = {
    "workshop",
    "tudou mod manger",
    ".l4d2_mod_manager_spray_previews",
    ".l4d2_voice_backups",
}
METADATA_FILE = ".l4d2_mod_manager.json"
VPK_ANALYSIS_VERSION = 2
PART_SUFFIX = re.compile(r"(?:[ _.-]?(?:part|vol|chunk)[ _.-]?\d+)$", re.IGNORECASE)
NUMBER_SUFFIX = re.compile(r"^(.*?)[ _.-]?\d{1,2}$")
SERIES_SUFFIX = re.compile(
    r"^(.*?)(?:\s*[-_:]\s*|\s+)(?:content\s+)?(?:part|vol(?:ume)?|chapter)\s*[-_. ]*(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*$",
    re.IGNORECASE,
)


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.casefold())


def _possible_group_key(stem: str) -> str:
    part_match = PART_SUFFIX.search(stem)
    if part_match:
        return stem[: part_match.start()]
    number_match = NUMBER_SUFFIX.match(stem)
    if number_match and number_match.group(1):
        return number_match.group(1)
    return stem


def _metadata_series_name(title: str | None) -> str | None:
    if not title:
        return None
    match = SERIES_SUFFIX.match(title.strip())
    base = match.group(1).strip(" -_:._") if match else ""
    return base or None


def _map_families(paths: list[str]) -> set[str]:
    families: set[str] = set()
    for path in paths:
        if not path.startswith("maps/") or not path.endswith(".bsp"):
            continue
        stem = path.rsplit("/", 1)[-1][:-4]
        if "." in stem:
            continue
        match = re.match(r"^(.+?)[_-]\d+(?:[_-].*)?$", stem)
        if match:
            families.add(_key(match.group(1)))
    return families


def _mission_names(paths: list[str]) -> set[str]:
    return {
        path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        for path in paths
        if path.startswith("missions/") and path.endswith((".txt", ".res"))
    }


def _embedded_archive_paths(paths: list[str]) -> list[str]:
    """Find archive files stored inside a VPK without opening or extracting them."""

    return sorted(
        {
            path.replace("\\", "/")
            for path in paths
            if Path(path).suffix.casefold() in ARCHIVE_EXTENSIONS
        }
    )


def _is_pure_archive_package(paths: list[str], archive_paths: list[str]) -> bool:
    """Return whether the VPK is an archive container rather than a normal Mod."""

    if not archive_paths:
        return False
    metadata_names = {"addoninfo.txt", "addonimage.jpg", "addonimage.png"}
    content_paths = [
        path
        for path in paths
        if Path(path).name.casefold() not in metadata_names
    ]
    return bool(content_paths) and all(path in archive_paths for path in content_paths)


def _group_stems(stems: list[str], exact_image_keys: set[str] | None = None) -> dict[str, str]:
    """Strip split-file suffixes only when doing so creates a real sibling group."""

    exact_image_keys = exact_image_keys or set()
    candidates = [_possible_group_key(stem) for stem in stems]
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[_key(candidate)] = counts.get(_key(candidate), 0) + 1

    grouped: dict[str, str] = {}
    for stem, candidate in zip(stems, candidates):
        if _key(stem) in exact_image_keys:
            grouped[stem] = stem
            continue
        if counts[_key(candidate)] > 1:
            grouped[stem] = candidate
        else:
            grouped[stem] = stem
    return grouped


def load_custom_names(root: str | Path) -> dict[str, str]:
    metadata_path = Path(root) / METADATA_FILE
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    names = payload.get("names", {})
    return names if isinstance(names, dict) else {}


def load_custom_tags(root: str | Path) -> dict[str, dict[str, str]]:
    metadata_path = Path(root) / METADATA_FILE
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    tags = payload.get("tags", {})
    if not isinstance(tags, dict):
        return {}
    return {
        str(mod_id): {
            str(tag_key): str(label).strip()
            for tag_key, label in values.items()
            if str(label).strip()
        }
        for mod_id, values in tags.items()
        if isinstance(values, dict)
    }


def load_marked_tags(root: str | Path) -> dict[str, dict[str, bool]]:
    metadata_path = Path(root) / METADATA_FILE
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    marked = payload.get("markedTags", {})
    if not isinstance(marked, dict):
        return {}
    return {
        str(mod_id): {
            str(tag_key): True
            for tag_key, value in values.items()
            if value is True
        }
        for mod_id, values in marked.items()
        if isinstance(values, dict)
    }


def save_custom_names(root: str | Path, names: dict[str, str]) -> None:
    metadata_path = Path(root) / METADATA_FILE
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload["names"] = names
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_custom_tags(root: str | Path, tags: dict[str, dict[str, str]]) -> None:
    metadata_path = Path(root) / METADATA_FILE
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload["tags"] = tags
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_marked_tags(root: str | Path, marked: dict[str, dict[str, bool]]) -> None:
    metadata_path = Path(root) / METADATA_FILE
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload["markedTags"] = marked
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_hidden_tags(root: str | Path) -> dict[str, dict[str, str]]:
    metadata_path = Path(root) / METADATA_FILE
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    hidden = payload.get("hiddenTags", {})
    if not isinstance(hidden, dict):
        return {}
    return {
        str(mod_id): {
            str(tag_key): str(label).strip()
            for tag_key, label in values.items()
            if str(label).strip()
        }
        for mod_id, values in hidden.items()
        if isinstance(values, dict)
    }


def save_hidden_tags(root: str | Path, hidden: dict[str, dict[str, str]]) -> None:
    metadata_path = Path(root) / METADATA_FILE
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload["hiddenTags"] = hidden
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _vpk_cache_signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def _cached_vpk_analysis(
    path: Path,
    root_path: Path,
    cache: dict[str, dict[str, object]],
) -> dict[str, object]:
    """Read and classify one VPK only when its on-disk signature changed."""

    cache_key = path.relative_to(root_path).as_posix()
    signature = _vpk_cache_signature(path)
    cached = cache.get(cache_key)
    if (
        cached
        and cached.get("signature") == signature
        and cached.get("analysisVersion") == VPK_ANALYSIS_VERSION
    ):
        return cached

    record: dict[str, object] = {
        "signature": signature,
        "analysisVersion": VPK_ANALYSIS_VERSION,
        "internalPaths": [],
        "title": None,
        "detection": None,
        "errorType": None,
        "error": None,
    }
    try:
        internal_paths = read_vpk_paths(path)
        record["internalPaths"] = internal_paths
        record["title"] = read_vpk_addon_title(path)
        record["detection"] = analyze_vpk_paths(path, internal_paths, record["title"])
    except VPKClassificationError as error:
        record["errorType"] = "classification"
        record["error"] = str(error)
    except (OSError, VPKFormatError) as error:
        record["errorType"] = "format"
        record["error"] = str(error)
    cache[cache_key] = record
    return record


def build_catalog(
    root: str | Path,
    vpk_cache: dict[str, dict[str, object]] | None = None,
) -> list[dict]:
    root_path = Path(root)
    cache = vpk_cache if vpk_cache is not None else {}
    all_files = [
        path
        for path in root_path.rglob("*")
        if path.is_file()
        and not (
            path.relative_to(root_path).parts
            and path.relative_to(root_path).parts[0].casefold() in IGNORED_DATA_DIRECTORIES
        )
    ]
    vpk_files = sorted(
        path for path in all_files
        if path.suffix.casefold() in VPK_EXTENSIONS
        and path.name.casefold() != GENERATED_SPRAY_VPK
    )
    image_files = sorted(path for path in all_files if path.suffix.casefold() in IMAGE_EXTENSIONS)
    custom_names = load_custom_names(root_path)
    custom_tags = load_custom_tags(root_path)
    marked_tags = load_marked_tags(root_path)
    hidden_tags = load_hidden_tags(root_path)

    current_cache_keys = {
        path.relative_to(root_path).as_posix()
        for path in vpk_files
    }
    for cache_key in set(cache) - current_cache_keys:
        cache.pop(cache_key, None)

    images_by_key: dict[str, list[Path]] = {}
    for image in image_files:
        images_by_key.setdefault(_key(image.stem), []).append(image)

    stem_groups = _group_stems(
        [path.stem for path in vpk_files],
        set(images_by_key),
    )
    package_signals: dict[Path, dict[str, object]] = {}
    addon_titles: dict[Path, str] = {}
    for path in vpk_files:
        analysis = _cached_vpk_analysis(path, root_path, cache)
        internal_paths = analysis["internalPaths"]
        title = analysis["title"]
        package_signals[path] = {
            "title": title,
            "titleKey": _key(title) if title else "",
            "missions": _mission_names(internal_paths),
            "mapFamilies": _map_families(internal_paths),
        }
        if title:
            addon_titles[path] = title

    # Build connected components from strong campaign evidence. This covers
    # same-title parts (Prague) and title-less continuation packages (hehe30).
    parent = {path: path for path in vpk_files}

    def find(path: Path) -> Path:
        while parent[path] != path:
            parent[path] = parent[parent[path]]
            path = parent[path]
        return path

    def union(left: Path, right: Path) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    def union_buckets(buckets: dict[str, list[Path]]) -> None:
        for members in buckets.values():
            if len(members) < 2:
                continue
            first = members[0]
            for member in members[1:]:
                union(first, member)

    series_buckets: dict[str, list[Path]] = {}
    title_buckets: dict[str, list[Path]] = {}
    mission_buckets: dict[str, list[Path]] = {}
    map_family_buckets: dict[str, list[Path]] = {}
    for path in vpk_files:
        signals = package_signals[path]
        title = signals["title"]
        if title:
            series = _metadata_series_name(str(title))
            if series:
                series_buckets.setdefault(_key(series), []).append(path)
            if signals["titleKey"]:
                title_buckets.setdefault(str(signals["titleKey"]), []).append(path)
        for mission in signals["missions"]:
            mission_buckets.setdefault(str(mission), []).append(path)
        for map_family in signals["mapFamilies"]:
            map_family_buckets.setdefault(str(map_family), []).append(path)

    union_buckets(series_buckets)
    union_buckets(title_buckets)
    union_buckets(mission_buckets)
    for members in map_family_buckets.values():
        if len(members) < 2:
            continue
        has_metadata_anchor = any(
            package_signals[path]["title"] or package_signals[path]["missions"]
            for path in members
        )
        if has_metadata_anchor:
            first = members[0]
            for member in members[1:]:
                union(first, member)

    component_paths: dict[Path, list[Path]] = {}
    for path in vpk_files:
        component_paths.setdefault(find(path), []).append(path)

    metadata_groups: dict[str, list[Path]] = {}
    metadata_group_names: dict[str, str] = {}
    for paths in component_paths.values():
        if len(paths) < 2:
            continue
        labels = [
            _metadata_series_name(str(package_signals[path]["title"]))
            for path in paths
            if package_signals[path]["title"]
        ]
        labels = [label for label in labels if label]
        if labels:
            series_name = sorted(labels, key=lambda value: (len(value), value.casefold()))[0]
        else:
            titled = [str(package_signals[path]["title"]) for path in paths if package_signals[path]["title"]]
            missions = sorted({mission for path in paths for mission in package_signals[path]["missions"]})
            series_name = titled[0] if titled else (missions[0] if missions else paths[0].stem)
        group_id = _key(f"series-{series_name}")
        metadata_groups[group_id] = paths
        metadata_group_names[group_id] = series_name

    path_group_keys = {path: stem_groups[path.stem] for path in vpk_files}
    for group_id, paths in metadata_groups.items():
        if len(paths) < 2:
            continue
        for path in paths:
            path_group_keys[path] = group_id

    grouped_vpks: dict[str, list[Path]] = {}
    for path in vpk_files:
        group_key = path_group_keys[path]
        grouped_vpks.setdefault(_key(group_key), []).append(path)

    catalog: list[dict] = []
    used_images: set[Path] = set()
    for group_key, files in sorted(grouped_vpks.items()):
        series_name = metadata_group_names.get(group_key)
        display_stem = series_name or (
            _possible_group_key(files[0].stem) if len(files) > 1 else files[0].stem
        )
        preview_files: list[Path] = []
        for file in files:
            preview_files.extend(images_by_key.get(_key(file.stem), []))
        if series_name:
            preview_files.extend(
                image
                for image in image_files
                if _key(_possible_group_key(image.stem)) == _key(series_name)
            )
        if not preview_files:
            preview_files.extend(images_by_key.get(_key(display_stem), []))
        if not preview_files:
            preview_files.extend(images_by_key.get(_key(files[0].stem), []))
        preview_files = list(dict.fromkeys(preview_files))
        preview = preview_files[0] if preview_files else None
        errors: list[dict] = []
        detections: list[dict] = []
        for vpk in files:
            analysis = _cached_vpk_analysis(vpk, root_path, cache)
            internal_paths = analysis["internalPaths"]
            embedded_archives = _embedded_archive_paths(internal_paths)
            pure_archive = _is_pure_archive_package(internal_paths, embedded_archives)
            if analysis["errorType"] == "classification":
                if pure_archive:
                    detections.append(
                        {
                            "primary": "archive",
                            "categories": ["archive"],
                            "confidence": "high",
                            "file_count": len(internal_paths),
                            "characterTargets": [],
                            "weaponTargets": [],
                            "signals": {"archive": embedded_archives[:12]},
                            "scores": {"archive": 100},
                            "embeddedArchives": embedded_archives,
                        }
                    )
                else:
                    errors.append({"file": vpk.name, "error": analysis["error"]})
                continue
            if analysis["errorType"]:
                errors.append({"file": vpk.name, "error": analysis["error"]})
                continue

            detection = copy.deepcopy(analysis["detection"])
            if pure_archive:
                detection["categories"] = sorted(set(detection.get("categories", [])) | {"archive"})
                detection["signals"] = {
                    **detection.get("signals", {}),
                    "archive": embedded_archives[:12],
                }
                detection["embeddedArchives"] = embedded_archives
            if any(
                path.startswith("nekovpk/") and path.endswith(".neko7z")
                for path in internal_paths
            ):
                try:
                    detection["nekovpk"] = {
                        **inspect_nekovpk(vpk),
                        "vpkPath": vpk.relative_to(root_path).as_posix(),
                    }
                except (NekoVPKError, OSError, VPKFormatError) as error:
                    detection["nekovpk"] = {
                        "format": "nekovpk",
                        "vpkPath": vpk.relative_to(root_path).as_posix(),
                        "error": str(error),
                        "targets": [],
                    }
            if "voice_replacement" in detection.get("categories", []):
                detection["voiceRoles"] = detect_voice_roles(internal_paths)
                voice_mode = detect_voice_replacement_mode(vpk, internal_paths)
                if voice_mode:
                    detection["voiceMode"] = voice_mode
                    detection["categories"].append(f"voice_{voice_mode}")
            detections.append(detection)

        categories = sorted(
            {
                category
                for detection in detections
                for category in detection.get("categories", [])
            }
        )
        primary_categories = sorted(
            {
                detection["primary"]
                for detection in detections
                if detection.get("primary")
            }
        )
        if any("archive" in detection.get("categories", []) for detection in detections):
            primary_categories.append("archive")
            primary_categories = sorted(set(primary_categories))
        character_targets: dict[tuple[str, str], dict] = {}
        for detection in detections:
            for target in detection.get("characterTargets", []):
                key = (target["side"], target["id"])
                character_targets.setdefault(
                    key,
                    {"side": target["side"], "id": target["id"], "name": target["name"], "evidence": []},
                )["evidence"].extend(target.get("evidence", []))
        for target in character_targets.values():
            target["evidence"] = sorted(set(target["evidence"]))[:12]
        weapon_targets: dict[str, dict] = {}
        for detection in detections:
            for target in detection.get("weaponTargets", []):
                weapon_targets.setdefault(
                    target["id"],
                    {"id": target["id"], "name": target["name"], "evidence": []},
                )["evidence"].extend(target.get("evidence", []))
        for target in weapon_targets.values():
            target["evidence"] = sorted(set(target["evidence"]))[:12]
        nekovpk_infos = [
            detection["nekovpk"]
            for detection in detections
            if isinstance(detection.get("nekovpk"), dict)
        ]
        nekovpk = nekovpk_infos[0] if len(nekovpk_infos) == 1 else None
        voice_roles_by_id: dict[str, dict] = {}
        voice_modes: set[str] = set()
        for detection in detections:
            for role in detection.get("voiceRoles", []):
                voice_roles_by_id.setdefault(role["id"], role)
            if detection.get("voiceMode") in {"automatic", "manual"}:
                voice_modes.add(detection["voiceMode"])
        catalog.append(
            {
                "id": group_key,
                "name": custom_names.get(group_key, display_stem),
                "tagOverrides": {
                    key: label
                    for key, label in custom_tags.get(group_key, {}).items()
                    if not key.startswith("custom:")
                },
                "customTags": [
                    {
                        "id": key.removeprefix("custom:"),
                        "label": label,
                        "marked": key in marked_tags.get(group_key, {}),
                    }
                    for key, label in custom_tags.get(group_key, {}).items()
                    if key.startswith("custom:")
                ],
                "hiddenTags": hidden_tags.get(group_key, {}),
                "originalName": display_stem,
                "preview": preview.relative_to(root_path).as_posix() if preview else None,
                "previewFiles": [path.relative_to(root_path).as_posix() for path in preview_files],
                "vpkFiles": [path.relative_to(root_path).as_posix() for path in files],
                "enabled": all(path.suffix.casefold() == ".vpk" for path in files),
                "partiallyEnabled": len({path.suffix.casefold() == ".vpk" for path in files}) > 1,
                "addonTitles": sorted({addon_titles[path] for path in files if path in addon_titles}),
                "categories": categories,
                "primaryCategories": primary_categories,
                "characterTargets": sorted(character_targets.values(), key=lambda item: item["name"]),
                "weaponTargets": sorted(weapon_targets.values(), key=lambda item: item["name"]),
                "nekovpk": nekovpk,
                "voiceRoles": list(voice_roles_by_id.values()),
                "voiceModes": sorted(voice_modes),
                "detections": detections,
                "errors": errors,
                "status": "matched" if preview else "missing_preview",
            }
        )
        used_images.update(preview_files)

    for image in image_files:
        if image not in used_images:
            catalog.append(
                {
                    "id": _key(image.stem),
                    "name": custom_names.get(_key(image.stem), image.stem),
                    "tagOverrides": {
                        key: label
                        for key, label in custom_tags.get(_key(image.stem), {}).items()
                        if not key.startswith("custom:")
                    },
                    "customTags": [
                        {
                            "id": key.removeprefix("custom:"),
                            "label": label,
                            "marked": key in marked_tags.get(_key(image.stem), {}),
                        }
                        for key, label in custom_tags.get(_key(image.stem), {}).items()
                        if key.startswith("custom:")
                    ],
                    "hiddenTags": hidden_tags.get(_key(image.stem), {}),
                    "originalName": image.stem,
                    "preview": image.relative_to(root_path).as_posix(),
                    "previewFiles": [image.relative_to(root_path).as_posix()],
                    "vpkFiles": [],
                    "enabled": True,
                    "partiallyEnabled": False,
                    "addonTitles": [],
                    "categories": [],
                    "primaryCategories": [],
                    "characterTargets": [],
                    "weaponTargets": [],
                    "nekovpk": None,
                    "voiceRoles": [],
                    "voiceModes": [],
                    "detections": [],
                    "errors": [],
                    "status": "image_without_vpk",
                }
            )

    return sorted(catalog, key=lambda item: item["name"].casefold())


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a JPG/VPK Mod catalog")
    parser.add_argument("folder", nargs="?", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(build_catalog(args.folder), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
