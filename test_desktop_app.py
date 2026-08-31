import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop_app import app_profile_dir


class DesktopAppTests(unittest.TestCase):
    def test_browser_profile_path_is_stable_between_launches(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"LOCALAPPDATA": temporary}, clear=False):
                first = app_profile_dir()
                second = app_profile_dir()

            self.assertEqual(first, second)
            self.assertEqual(first, Path(temporary) / "L4D2ModManager" / "BrowserProfile")
            self.assertTrue(first.is_dir())


if __name__ == "__main__":
    unittest.main()
