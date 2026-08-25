import json
import io
import os
from http.client import HTTPConnection
import shutil
import struct
import subprocess
import tarfile
import tempfile
import threading
import unittest
import zipfile
import zlib
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from mod_catalog import build_catalog, save_custom_names, save_custom_tags
from mod_server import ModRequestHandler, extract_archive, rename_mod_files
from nekovpk import convert_nekovpk_target, inspect_nekovpk, write_vpk_entries
from voice_replacement import (
    VoiceReplacementError,
    inspect_voice_package,
    install_voice_package,
    restore_voice_package,
)
from vpk_detector import (
    VPKClassificationError,
    analyze_vpk,
    classify_paths,
    read_vpk_paths,
    read_vpk_addon_title,
)


def make_vpk_files(file_contents: dict[str, bytes]) -> bytes:
    grouped: dict[str, dict[str, list[str]]] = {}
    for relative_path in file_contents:
        folder, filename = relative_path.rsplit("/", 1) if "/" in relative_path else (" ", relative_path)
        stem, extension = filename.rsplit(".", 1)
        grouped.setdefault(extension, {}).setdefault(folder, []).append(stem)

    tree = bytearray()
    payload = bytearray()
    for extension, folders in sorted(grouped.items()):
        tree.extend(extension.encode() + b"\x00")
        for folder, stems in sorted(folders.items()):
            tree.extend(folder.encode() + b"\x00")
            for stem in sorted(stems):
                tree.extend(stem.encode() + b"\x00")
                relative_path = "/".join(part for part in ("" if folder == " " else folder, stem) if part)
                relative_path = f"{relative_path}.{extension}"
                content = file_contents[relative_path]
                tree.extend(struct.pack("<IHHIIH", 0, 0, 0x7FFF, len(payload), len(content), 0xFFFF))
                payload.extend(content)
            tree.extend(b"\x00")
        tree.extend(b"\x00")
    tree.extend(b"\x00")
    return struct.pack("<III", 0x55AA1234, 1, len(tree)) + tree + payload


def make_vpk(relative_paths: list[str]) -> bytes:
    return make_vpk_files({relative_path: b"" for relative_path in relative_paths})


def make_neko7z(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return output.getvalue()


def read_vpk_entry_crcs(file_path: Path) -> dict[str, int]:
    data = file_path.read_bytes()
    signature, version, tree_size = struct.unpack_from("<III", data)
    header_size = 12 if version == 1 else 28
    tree_end = header_size + tree_size
    position = header_size
    result: dict[str, int] = {}

    def read_string() -> str:
        nonlocal position
        end = data.index(b"\x00", position)
        value = data[position:end].decode("utf-8")
        position = end + 1
        return value

    assert signature == 0x55AA1234
    while position < tree_end:
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
                entry_offset = position
                crc, preload_bytes, archive_index, offset, length, terminator = struct.unpack_from(
                    "<IHHIIH", data, position
                )
                position += 18 + preload_bytes
                relative = "/".join(
                    part for part in ("" if folder == " " else folder, filename) if part
                )
                path = f"{relative}.{extension}".casefold()
                result[path] = crc
                assert archive_index == 0x7FFF
                assert offset + length <= len(data) - tree_end
                assert terminator == 0xFFFF
                assert crc == zlib.crc32(data[tree_end + offset : tree_end + offset + length]) & 0xFFFFFFFF
                assert position > entry_offset
    return result


def read_vpk_extension_groups(file_path: Path) -> list[str]:
    """Read extension nodes from the VPK tree using the Valve format grammar."""

    data = file_path.read_bytes()
    _, version, tree_size = struct.unpack_from("<III", data)
    position = 12 if version == 1 else 28
    tree_end = position + tree_size
    extensions: list[str] = []

    def read_string() -> str:
        nonlocal position
        end = data.index(b"\x00", position)
        value = data[position:end].decode("utf-8")
        position = end + 1
        return value

    while position < tree_end:
        extension = read_string()
        if not extension:
            break
        extensions.append(extension)
        while True:
            folder = read_string()
            if not folder:
                break
            while read_string():
                position += 18
    return extensions


def verify_with_official_valvepak(file_path: Path) -> None:
    """Ask the official ValvePak assembly to parse and CRC-check one VPK."""

    dll_path = os.environ.get("NEKOVPK_VALVEPAK_DLL", "")
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not dll_path or not Path(dll_path).is_file() or not shell:
        raise unittest.SkipTest(
            "设置 NEKOVPK_VALVEPAK_DLL 并安装 PowerShell 后才运行官方 ValvePak 集成测试"
        )
    script = r'''
$ErrorActionPreference = "Stop"
$assembly = [System.Reflection.Assembly]::LoadFrom($env:NEKOVPK_VALVEPAK_DLL)
$type = $assembly.GetType("SteamDatabase.ValvePak.Package")
$package = [Activator]::CreateInstance($type)
try {
    $package.Read($env:NEKOVPK_TEST_VPK)
    $package.VerifyFileChecksums($null)
} finally {
    $package.Dispose()
}
'''
    environment = os.environ.copy()
    environment["NEKOVPK_TEST_VPK"] = str(file_path)
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    if result.returncode:
        details = (result.stderr or result.stdout).strip()
        raise AssertionError(f"官方 ValvePak 校验失败：{details}")


class VPKDetectorTests(unittest.TestCase):
    def test_nekovpk_writer_uses_standard_extension_groups_and_crcs(self):
        entries = {
            "models/survivors/survivor_gambler.mdl": b"model",
            "models/weapons/arms/v_arms_gambler_new.mdl": b"arms",
            "materials/vgui/s_panel_gambler.vtf": b"panel",
            "materials/other/panel.vtf": b"other-panel",
            "nekovpk/example/0.neko7z": b"archive",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "written.vpk"
            write_vpk_entries(path, entries)

            extension_groups = read_vpk_extension_groups(path)
            self.assertEqual(len(extension_groups), len(set(extension_groups)))
            self.assertEqual(
                read_vpk_entry_crcs(path),
                {name: zlib.crc32(content) & 0xFFFFFFFF for name, content in entries.items()},
            )

    def test_nekovpk_writer_is_readable_by_official_valvepak(self):
        entries = {
            "models/survivors/survivor_gambler.mdl": b"model",
            "models/weapons/arms/v_arms_gambler_new.mdl": b"arms",
            "materials/vgui/s_panel_gambler.vtf": b"panel",
            "materials/other/panel.vtf": b"other-panel",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "written.vpk"
            write_vpk_entries(path, entries)
            verify_with_official_valvepak(path)

    def test_voice_replacement_preview_install_and_restore_are_backed_up(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            game = workspace / "left4dead2"
            addons = game / "addons"
            addons.mkdir(parents=True)
            base_voice = game / "sound/player/survivor/voice/manager"
            dlc_voice = workspace / "left4dead2_dlc1/sound/player/survivor/voice/manager"
            base_voice.mkdir(parents=True)
            dlc_voice.mkdir(parents=True)
            (base_voice / "alertgiveitem01.wav").write_bytes(b"original-base")
            (dlc_voice / "alertgiveitem01.wav").write_bytes(b"original-dlc")
            vpk_path = addons / "voice.vpk"
            vpk_path.write_bytes(
                make_vpk_files(
                    {
                        "sound/player/survivor/voice/manager/alertgiveitem01.wav": b"replacement",
                        "sound/player/survivor/voice/manager/alertgiveitem02.wav": b"new-line",
                    }
                )
            )
            mod = build_catalog(addons)[0]

            preview = inspect_voice_package(addons, mod)
            self.assertEqual(preview["sourceFileCount"], 2)
            manager = next(role for role in preview["roles"] if role["id"] == "manager")
            self.assertEqual(manager["overwriteCount"], 2)
            self.assertEqual(manager["newCount"], 2)
            self.assertEqual((base_voice / "alertgiveitem01.wav").read_bytes(), b"original-base")

            catalog_server = type("CatalogServer", (), {
                "mod_root": addons,
                "catalog_cache": None,
            })()
            catalog_handler = object.__new__(ModRequestHandler)
            catalog_handler.server = catalog_server
            catalog_handler.root = addons
            self.assertFalse(catalog_handler._catalog(refresh=True)[0]["voiceInstalled"])

            result = install_voice_package(addons, mod)
            self.assertEqual(result["fileCount"], 4)
            self.assertEqual((base_voice / "alertgiveitem01.wav").read_bytes(), b"replacement")
            self.assertEqual((base_voice / "alertgiveitem02.wav").read_bytes(), b"new-line")
            self.assertEqual((dlc_voice / "alertgiveitem01.wav").read_bytes(), b"replacement")
            self.assertTrue((addons / result["backupDir"] / "left4dead2/sound/player/survivor/voice/manager/alertgiveitem01.wav").is_file())
            catalog_server.catalog_cache = None
            self.assertTrue(catalog_handler._catalog(refresh=True)[0]["voiceInstalled"])
            with self.assertRaises(VoiceReplacementError):
                install_voice_package(addons, mod)

            restore_voice_package(addons, mod["id"])
            self.assertEqual((base_voice / "alertgiveitem01.wav").read_bytes(), b"original-base")
            self.assertEqual((dlc_voice / "alertgiveitem01.wav").read_bytes(), b"original-dlc")
            self.assertFalse((base_voice / "alertgiveitem02.wav").exists())
            self.assertFalse((dlc_voice / "alertgiveitem02.wav").exists())

    def test_nekovpk_inspection_and_target_conversion_are_isolated(self):
        nested = make_neko7z(
            {
                "models/survivors/survivor_gambler.mdl": b"nick-model",
                "models/weapons/arms/v_arms_gambler_new.mdl": b"nick-arms",
                "materials/vgui/s_panel_gambler.vtf": b"nick-panel",
                "materials/vgui/s_panel_gambler_incap.vtf": b"nick-incap",
                "materials/vgui/s_panel_lobby_gambler.vtf": b"nick-lobby",
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "nekovpk.vpk"
            path.write_bytes(
                make_vpk_files(
                    {
                        "models/survivors/survivor_namvet.mdl": b"bill-model",
                        "models/weapons/arms/v_arms_bill.mdl": b"bill-arms",
                        "materials/vgui/s_panel_namvet.vtf": b"bill-panel",
                        "materials/vgui/s_panel_namvet_incap.vtf": b"bill-incap",
                        "nekovpk/example/0.neko7z": nested,
                    }
                )
            )

            info = inspect_nekovpk(path)
            self.assertEqual(info["currentTarget"], "bill")
            self.assertEqual(
                {target["id"] for target in info["targets"]},
                {"bill", "nick"},
            )

            result = convert_nekovpk_target(path, "nick")
            self.assertTrue(result["changed"])
            self.assertTrue(Path(result["backup"]).is_file())
            converted_paths = read_vpk_paths(path)
            self.assertIn("models/survivors/survivor_gambler.mdl", converted_paths)
            self.assertNotIn("models/survivors/survivor_namvet.mdl", converted_paths)
            self.assertIn("materials/vgui/s_panel_gambler_incap.vtf", converted_paths)
            self.assertIn("materials/vgui/s_panel_lobby_gambler.vtf", converted_paths)
            self.assertNotIn("materials/vgui/s_panel_namvet_incap.vtf", converted_paths)
            converted_crcs = read_vpk_entry_crcs(path)
            self.assertEqual(len(converted_crcs), len(converted_paths))
            self.assertTrue(all(converted_crcs.values()))

            convert_nekovpk_target(path, "bill")
            restored_paths = read_vpk_paths(path)
            self.assertIn("models/survivors/survivor_namvet.mdl", restored_paths)
            self.assertNotIn("models/survivors/survivor_gambler.mdl", restored_paths)
            self.assertIn("materials/vgui/s_panel_namvet_incap.vtf", restored_paths)
            self.assertNotIn("materials/vgui/s_panel_gambler_incap.vtf", restored_paths)
            restored_crcs = read_vpk_entry_crcs(path)
            self.assertEqual(len(restored_crcs), len(restored_paths))
            self.assertTrue(all(restored_crcs.values()))

    def test_server_exposes_only_nekovpk_target_conversion(self):
        nested = make_neko7z(
            {
                "models/survivors/survivor_gambler.mdl": b"nick-model",
                "models/weapons/arms/v_arms_gambler_new.mdl": b"nick-arms",
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "sample.vpk").write_bytes(
                make_vpk_files(
                    {
                        "models/survivors/survivor_namvet.mdl": b"bill-model",
                        "models/weapons/arms/v_arms_bill.mdl": b"bill-arms",
                        "nekovpk/example/0.neko7z": nested,
                    }
                )
            )
            mod_id = build_catalog(root)[0]["id"]
            handler = type("TestNekoRequestHandler", (ModRequestHandler,), {"root": root})
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                port = server.server_address[1]

                def request(method, route, payload=None):
                    connection = HTTPConnection("127.0.0.1", port)
                    body = json.dumps(payload).encode() if payload is not None else None
                    headers = {"Content-Type": "application/json"} if body is not None else {}
                    connection.request(method, route, body=body, headers=headers)
                    response = connection.getresponse()
                    result = json.loads(response.read())
                    connection.close()
                    return response.status, result

                status, info = request("GET", f"/api/mod/nekovpk?id={mod_id}")
                self.assertEqual(status, 200)
                self.assertEqual(info["currentTarget"], "bill")

                status, body = request(
                    "POST",
                    "/api/mod/nekovpk/convert",
                    {"id": mod_id, "target": "nick"},
                )
                self.assertEqual(status, 200)
                self.assertEqual(body["nekovpk"]["currentTarget"], "nick")
                self.assertTrue((root / "sample.vpk.nekobak").is_file())
            finally:
                server.shutdown()
                server.server_close()

    def test_reads_directory_tree(self):
        expected = ["maps/c1m1_hotel.bsp", "materials/vgui/logos/my_logo.vtf"]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.vpk"
            path.write_bytes(make_vpk(expected))
            self.assertEqual(read_vpk_paths(path), sorted(expected))

    def test_classifies_content(self):
        self.assertEqual(
            classify_paths(["models/survivors/coach.mdl", "models/survivors/coach.vvd"])["primary"],
            "survivor_model",
        )
        survivor_targets = classify_paths(["models/survivors/survivor_mechanic.mdl"])["characterTargets"]
        self.assertEqual([(target["side"], target["name"]) for target in survivor_targets], [("survivor", "Ellis")])
        self.assertEqual(
            classify_paths(["models/infected/boomer.mdl"])["primary"], "infected_model"
        )
        infected_targets = classify_paths(["models/infected/common_male_calentito.mdl"])["characterTargets"]
        self.assertEqual(
            [(target["side"], target["name"]) for target in infected_targets],
            [("infected", "普通感染者（男性）")],
        )
        self.assertEqual(
            classify_paths(["maps/c1m1_hotel.bsp", "missions/c1m1.txt"])["primary"], "map"
        )
        self.assertEqual(
            classify_paths(["missions/campaign.txt", "models/infected/boomer.mdl"])["primary"],
            "map",
        )
        self.assertEqual(
            classify_paths(["materials/vgui/logos/logo.vtf"])["primary"], "spray"
        )
        voice = classify_paths(
            [
                "sound/player/survivor/voice/manager/alertgiveitem01.wav",
                "sound/player/survivor/voice/manager/alertgiveitem02.wav",
            ]
        )
        self.assertEqual(voice["primary"], "voice_replacement")
        self.assertIn("sound", voice["categories"])

    def test_classifies_ui_scripts_and_environment_models(self):
        self.assertEqual(
            classify_paths(["resource/ui/mainmenu.res", "scripts/clientmenu.txt"])["primary"],
            "ui",
        )
        self.assertEqual(
            classify_paths(["scripts/vscripts/director_base_addon.nut"])["primary"],
            "script",
        )
        self.assertEqual(
            classify_paths(["models/props_vehicles/tanker001a.mdl"])["primary"],
            "prop_model",
        )

    def test_classifies_first_person_and_world_weapon_models(self):
        self.assertEqual(
            classify_paths(["models/v_models/v_autoshotgun.mdl"])["primary"],
            "weapon_model",
        )
        self.assertEqual(
            classify_paths(["models/w_models/weapons/w_m60.mdl"])["primary"],
            "weapon_model",
        )
        targets = classify_paths(
            ["models/v_models/v_desert_eagle.mdl", "models/w_models/weapons/w_rifle_m16a2.mdl"]
        )["weaponTargets"]
        self.assertEqual(
            [(target["id"], target["name"]) for target in targets],
            [("m16", "M16"), ("desert_eagle", "沙漠之鹰")],
        )
        melee_and_special = classify_paths(
            [
                "models/weapons/melee/w_pitchfork.mdl",
                "models/weapons/melee/v_frying_pan.mdl",
                "models/v_models/v_snip_awp.mdl",
                "models/v_models/v_desert_rifle.mdl",
            ]
        )["weaponTargets"]
        self.assertEqual(
            [(target["id"], target["name"]) for target in melee_and_special],
            [("awp", "AWP 狙击枪"), ("scar", "SCAR-L"), ("pitchfork", "干草叉"), ("frying_pan", "平底锅")],
        )

    def test_environment_names_do_not_create_character_targets(self):
        targets = classify_paths(
            ["models/props_vehicles/coolingtank02.mdl", "models/props_static/witch_sign.mdl"]
        )["characterTargets"]
        self.assertEqual(targets, [])

    def test_reads_addon_title_and_groups_content_parts_as_one_mod(self):
        title_part = b'"AddonInfo"\n{ addontitle "Chernobyl - Content Part 1" }'
        title_main = b'"AddonInfo"\n{ addontitle "Chernobyl - Chapter One" }'
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "part.vpk").write_bytes(
                make_vpk_files(
                    {
                        "materials/chernobyl/wall.vtf": b"",
                        "addoninfo.txt": title_part,
                    }
                )
            )
            (root / "main.vpk").write_bytes(
                make_vpk_files(
                    {
                        "missions/chernobyl.txt": b"",
                        "addoninfo.txt": title_main,
                    }
                )
            )
            (root / "part.jpg").write_bytes(b"jpg")
            (root / "main.jpg").write_bytes(b"jpg")

            self.assertEqual(read_vpk_addon_title(root / "part.vpk"), "Chernobyl - Content Part 1")
            catalog = build_catalog(root)
            self.assertEqual(len(catalog), 1)
            self.assertEqual(catalog[0]["name"], "Chernobyl")
            self.assertEqual(catalog[0]["vpkFiles"], ["main.vpk", "part.vpk"])
            self.assertEqual(len(catalog[0]["previewFiles"]), 2)
            self.assertIn("map", catalog[0]["categories"])

    def test_unknown_content_is_an_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "unknown.vpk"
            path.write_bytes(make_vpk(["cfg/addon.cfg"]))
            with self.assertRaises(VPKClassificationError):
                analyze_vpk(path)

    def test_groups_same_title_map_parts(self):
        title = b'"AddonInfo"\n{ addontitle "Prague" }'
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for index in (1, 2, 3):
                (root / f"part{index}.vpk").write_bytes(
                    make_vpk_files(
                        {
                            f"maps/prague_{index}.bsp": b"",
                            "addoninfo.txt": title,
                        }
                    )
                )
                (root / f"part{index}.jpg").write_bytes(b"jpg")

            catalog = build_catalog(root)
            self.assertEqual(len(catalog), 1)
            self.assertEqual(catalog[0]["name"], "Prague")
            self.assertEqual(len(catalog[0]["vpkFiles"]), 3)
            self.assertEqual(len(catalog[0]["previewFiles"]), 3)

    def test_groups_titleless_continuation_by_map_family(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "main.vpk").write_bytes(
                make_vpk_files(
                    {
                        "maps/hehe30_1.bsp": b"",
                        "missions/hehe30.txt": b"",
                        "addoninfo.txt": b'"AddonInfo"\n{ addontitle "hehe30" }',
                    }
                )
            )
            (root / "continuation.vpk").write_bytes(
                make_vpk_files({"maps/hehe30_2.bsp": b""})
            )

            catalog = build_catalog(root)
            self.assertEqual(len(catalog), 1)
            self.assertEqual(catalog[0]["name"], "hehe30")
            self.assertEqual(catalog[0]["vpkFiles"], ["continuation.vpk", "main.vpk"])

    def test_catalog_links_preview_and_vpk(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "3484097222.jpg").write_bytes(b"jpg")
            (root / "3484097222.vpk").write_bytes(
                make_vpk(["models/survivors/survivor_coach.mdl"])
            )
            (root / "3765243667.jpg").write_bytes(b"jpg")

            catalog = build_catalog(root)
            linked = next(item for item in catalog if item["name"] == "3484097222")
            orphan = next(item for item in catalog if item["name"] == "3765243667")
            self.assertEqual(linked["status"], "matched")
            self.assertEqual(linked["preview"], "3484097222.jpg")
            self.assertEqual(linked["vpkFiles"], ["3484097222.vpk"])
            self.assertEqual(orphan["status"], "image_without_vpk")

    def test_custom_name_is_persisted_in_catalog(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "sample.vpk").write_bytes(make_vpk(["maps/c1m1_hotel.bsp"]))
            save_custom_names(root, {"sample": "我的战役"})
            catalog = build_catalog(root)
            self.assertEqual(catalog[0]["name"], "我的战役")
            self.assertEqual(catalog[0]["originalName"], "sample")

    def test_disabled_vpk_remains_in_catalog(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "sample.vpk1").write_bytes(make_vpk(["maps/c1m1_hotel.bsp"]))
            (root / "sample.jpg").write_bytes(b"jpg")
            catalog = build_catalog(root)
            self.assertEqual(len(catalog), 1)
            self.assertEqual(catalog[0]["id"], "sample")
            self.assertEqual(catalog[0]["vpkFiles"], ["sample.vpk1"])
            self.assertFalse(catalog[0]["enabled"])

    def test_zip_import_is_safe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "import.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("new_mod.vpk", make_vpk(["maps/c1m1_hotel.bsp"]))
                package.writestr("../outside.txt", "must be rejected")
            with self.assertRaises(ValueError):
                extract_archive(archive, root)
            self.assertFalse((root.parent / "outside.txt").exists())

            clean_archive = root / "clean.zip"
            with zipfile.ZipFile(clean_archive, "w") as package:
                package.writestr("folder/new_mod.vpk", make_vpk(["maps/c1m1_hotel.bsp"]))
            result = extract_archive(clean_archive, root)
            self.assertEqual(result["imported"], ["folder/new_mod.vpk"])

    def test_server_rename_and_delete_actions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "sample.vpk").write_bytes(make_vpk(["maps/c1m1_hotel.bsp"]))
            (root / "sample.jpg").write_bytes(b"jpg")
            save_custom_tags(root, {"sample": {"custom:favorite": "我喜欢的标签"}})
            handler = type("TestModRequestHandler", (ModRequestHandler,), {"root": root})
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                port = server.server_address[1]

                def post(route, payload):
                    connection = HTTPConnection("127.0.0.1", port)
                    connection.request(
                        "POST",
                        route,
                        body=json.dumps(payload),
                        headers={"Content-Type": "application/json"},
                    )
                    response = connection.getresponse()
                    body = json.loads(response.read())
                    connection.close()
                    return response.status, body

                status, body = post("/api/mod/toggle", {"id": "sample", "enabled": False})
                self.assertEqual(status, 200)
                self.assertEqual(body["renamed"], ["sample.vpk1"])
                self.assertFalse((root / "sample.vpk").exists())
                self.assertTrue((root / "sample.vpk1").exists())
                self.assertFalse(build_catalog(root)[0]["enabled"])

                status, body = post("/api/mod/toggle", {"id": "sample", "enabled": True})
                self.assertEqual(status, 200)
                self.assertEqual(body["renamed"], ["sample.vpk"])
                self.assertTrue((root / "sample.vpk").exists())
                self.assertTrue(build_catalog(root)[0]["enabled"])

                status, body = post(
                    "/api/mod/tag/mark",
                    {"id": "sample", "key": "custom:favorite", "marked": True},
                )
                self.assertEqual(status, 200)
                self.assertTrue(body["marked"])
                custom_tag = build_catalog(root)[0]["customTags"][0]
                self.assertTrue(custom_tag["marked"])

                status, body = post(
                    "/api/mod/tag/mark",
                    {"id": "sample", "key": "custom:favorite", "marked": False},
                )
                self.assertEqual(status, 200)
                self.assertFalse(body["marked"])
                custom_tag = build_catalog(root)[0]["customTags"][0]
                self.assertFalse(custom_tag["marked"])

                status, _ = post("/api/mod/rename", {"id": "sample", "name": "测试地图"})
                self.assertEqual(status, 200)
                self.assertEqual(build_catalog(root)[0]["name"], "测试地图")
                self.assertTrue((root / "测试地图.vpk").exists())
                self.assertTrue((root / "测试地图.jpg").exists())

                with patch(
                    "mod_server.move_to_recycle_bin",
                    side_effect=lambda paths: [path.unlink() for path in paths],
                ) as recycle_bin:
                    status, body = post("/api/mod/delete", {"id": "测试地图"})
                self.assertEqual(status, 200)
                self.assertTrue(body["recycled"])
                self.assertEqual(body["removed"], ["测试地图.vpk", "测试地图.jpg"])
                recycle_bin.assert_called_once()
                self.assertFalse((root / "测试地图.vpk").exists())
                self.assertFalse((root / "测试地图.jpg").exists())
            finally:
                server.shutdown()
                server.server_close()

    def test_server_file_details_and_single_vpk_delete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            content = make_vpk_files(
                {
                    "maps/duplicate.bsp": b"map",
                    "addoninfo.txt": b'"AddonInfo"\n{ addontitle "Duplicate Mod" }',
                }
            )
            (root / "copy1.vpk").write_bytes(content)
            (root / "copy2.vpk").write_bytes(content)
            mod = build_catalog(root)[0]
            handler = type("TestModRequestHandler", (ModRequestHandler,), {"root": root})
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                port = server.server_address[1]

                def request(method, route, payload=None):
                    connection = HTTPConnection("127.0.0.1", port)
                    body = json.dumps(payload).encode() if payload is not None else None
                    headers = {"Content-Type": "application/json"} if body is not None else {}
                    connection.request(method, route, body=body, headers=headers)
                    response = connection.getresponse()
                    result = json.loads(response.read())
                    connection.close()
                    return response.status, result

                status, body = request("GET", f"/api/mod/file-details?id={mod['id']}")
                self.assertEqual(status, 200)
                self.assertEqual(len(body["files"]), 2)
                self.assertTrue(all(item["duplicate"] for item in body["files"]))
                self.assertEqual({item["size"] for item in body["files"]}, {len(content)})

                with patch(
                    "mod_server.move_to_recycle_bin",
                    side_effect=lambda paths: [path.unlink() for path in paths],
                ) as recycle_bin:
                    status, body = request(
                        "POST",
                        "/api/mod/file-delete",
                        {"id": mod["id"], "path": "copy1.vpk"},
                    )
                self.assertEqual(status, 200)
                self.assertTrue(body["recycled"])
                recycle_bin.assert_called_once()
                self.assertFalse((root / "copy1.vpk").exists())
                self.assertTrue((root / "copy2.vpk").exists())
            finally:
                server.shutdown()
                server.server_close()

    def test_split_map_rename_preserves_part_suffixes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "宜昌市1.vpk").write_bytes(make_vpk(["maps/yichang02_1.bsp"]))
            (root / "宜昌市2.vpk").write_bytes(make_vpk(["maps/yichang02_2.bsp"]))
            (root / "宜昌市.jpg").write_bytes(b"jpg")
            mod = build_catalog(root)[0]
            renamed = rename_mod_files(root, mod, "新地图")
            self.assertEqual(
                renamed,
                ["新地图1.vpk", "新地图2.vpk", "新地图.jpg"],
            )

    def test_server_bulk_toggle_and_delete_actions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "one.vpk").write_bytes(make_vpk(["maps/c1m1_hotel.bsp"]))
            (root / "two.vpk").write_bytes(make_vpk(["maps/c2m1_highway.bsp"]))
            handler = type("TestModRequestHandler", (ModRequestHandler,), {"root": root})
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                port = server.server_address[1]

                def post(route, payload):
                    connection = HTTPConnection("127.0.0.1", port)
                    connection.request(
                        "POST",
                        route,
                        body=json.dumps(payload),
                        headers={"Content-Type": "application/json"},
                    )
                    response = connection.getresponse()
                    body = json.loads(response.read())
                    connection.close()
                    return response.status, body

                status, body = post(
                    "/api/mod/bulk",
                    {"action": "disable", "ids": ["one", "two"]},
                )
                self.assertEqual(status, 200)
                self.assertEqual(body["processed"], ["one", "two"])
                self.assertTrue((root / "one.vpk1").exists())
                self.assertTrue((root / "two.vpk1").exists())

                status, body = post(
                    "/api/mod/bulk",
                    {"action": "enable", "ids": ["one", "two"]},
                )
                self.assertEqual(status, 200)
                self.assertEqual(body["processed"], ["one", "two"])
                self.assertTrue((root / "one.vpk").exists())
                self.assertTrue((root / "two.vpk").exists())

                with patch(
                    "mod_server.move_to_recycle_bin",
                    side_effect=lambda paths: [path.unlink() for path in paths],
                ) as recycle_bin:
                    status, body = post(
                        "/api/mod/bulk",
                        {"action": "delete", "ids": ["one", "two"]},
                    )
                self.assertEqual(status, 200)
                self.assertEqual(body["processed"], ["one", "two"])
                recycle_bin.assert_called_once()
                self.assertFalse((root / "one.vpk").exists())
                self.assertFalse((root / "two.vpk").exists())
            finally:
                server.shutdown()
                server.server_close()

    def test_multi_part_map_is_renumbered_sequentially(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for filename in ("old_part10.vpk", "old_part2.vpk", "old_part1.vpk"):
                (root / filename).write_bytes(make_vpk([f"maps/{filename}.bsp"]))
            mod = build_catalog(root)[0]
            renamed = rename_mod_files(root, mod, "战役")
            self.assertEqual(
                renamed,
                ["战役1.vpk", "战役2.vpk", "战役3.vpk"],
            )

    def test_exact_preview_prevents_numeric_name_merge(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "test.vpk").write_bytes(make_vpk(["maps/test.bsp"]))
            (root / "test2.vpk").write_bytes(make_vpk(["models/survivors/survivor_coach.mdl"]))
            (root / "test2.jpg").write_bytes(b"jpg")
            catalog = build_catalog(root)
            test2 = next(item for item in catalog if item["name"] == "test2")
            self.assertEqual(test2["vpkFiles"], ["test2.vpk"])
            self.assertEqual(test2["preview"], "test2.jpg")


if __name__ == "__main__":
    unittest.main()
