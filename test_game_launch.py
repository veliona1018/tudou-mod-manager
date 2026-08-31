import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_server import find_game_executable, launch_game


class GameLaunchTests(unittest.TestCase):
    def test_finds_game_executable_above_addons_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            install = Path(temporary)
            addons = install / "left4dead2" / "addons"
            addons.mkdir(parents=True)
            executable = install / "left4dead2.exe"
            executable.write_bytes(b"MZ")

            self.assertEqual(find_game_executable(addons), executable)

    def test_launches_game_from_its_install_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            install = Path(temporary)
            addons = install / "left4dead2" / "addons"
            addons.mkdir(parents=True)
            executable = install / "left4dead2.exe"
            executable.write_bytes(b"MZ")
            with patch("mod_server.subprocess.Popen") as popen:
                result = launch_game(addons)

            self.assertEqual(result["mode"], "direct")
            popen.assert_called_once_with(
                [str(executable)],
                cwd=str(install),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )

    @unittest.skipUnless(os.name == "nt", "Steam URI fallback is Windows-specific")
    def test_falls_back_to_steam_when_executable_is_missing(self):
        with tempfile.TemporaryDirectory() as temporary, patch("mod_server.os.startfile") as startfile:
            result = launch_game(Path(temporary))

        self.assertEqual(result, {"ok": True, "mode": "steam"})
        startfile.assert_called_once_with("steam://rungameid/550")


if __name__ == "__main__":
    unittest.main()
