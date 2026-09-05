import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_server import (
    _parse_steam_library_paths,
    _rank_game_mod_folders,
    _validate_mod_folder,
    find_l4d2_mod_folders,
)


class GameFolderTests(unittest.TestCase):
    def test_parses_steam_library_paths_with_escaped_backslashes(self):
        contents = r'''
        "libraryfolders"
        {
            "0" { "path" "C:\\Program Files (x86)\\Steam" }
            "1" { "path" "D:\\SteamLibrary" }
        }
        '''

        self.assertEqual(
            _parse_steam_library_paths(contents),
            [Path(r"C:\Program Files (x86)\Steam"), Path(r"D:\SteamLibrary")],
        )

    def test_finds_addons_in_all_steam_libraries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "Steam"
            second = root / "SteamLibrary"
            for library in (first, second):
                (library / "steamapps" / "common" / "Left 4 Dead 2" / "left4dead2" / "addons").mkdir(parents=True)

            with patch("mod_server._steam_library_roots", return_value=[first, second]):
                found = find_l4d2_mod_folders()

            self.assertEqual(len(found), 2)
            self.assertTrue(all(path.name == "addons" for path in found))

    def test_ranking_prefers_current_folder_then_mod_count(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            empty = root / "empty"
            full = root / "full"
            empty.mkdir()
            full.mkdir()
            (full / "one.vpk").write_bytes(b"")
            (full / "two.vpk").write_bytes(b"")

            self.assertEqual(_rank_game_mod_folders([empty, full])[0], full)
            self.assertEqual(_rank_game_mod_folders([empty, full], empty)[0], empty)

    def test_rejects_a_filesystem_root_as_mod_folder(self):
        root = Path(Path.cwd().anchor)
        with self.assertRaisesRegex(ValueError, "不要选择"):
            _validate_mod_folder(root)

    def test_accepts_a_specific_mod_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            selected = _validate_mod_folder(Path(temporary))
            self.assertEqual(selected, Path(temporary).resolve())


if __name__ == "__main__":
    unittest.main()
