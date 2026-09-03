import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop_app import app_profile_dir, acquire_single_instance, release_single_instance


class DesktopAppTests(unittest.TestCase):
    def test_browser_profile_path_is_stable_between_launches(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"LOCALAPPDATA": temporary}, clear=False):
                first = app_profile_dir()
                second = app_profile_dir()

            self.assertEqual(first, second)
            self.assertEqual(first, Path(temporary) / "L4D2ModManager" / "BrowserProfile")
            self.assertTrue(first.is_dir())

    @patch("desktop_app.os.name", "posix")
    def test_non_windows_single_instance_fallback_is_releasable(self):
        handle = acquire_single_instance()

        self.assertTrue(handle)
        release_single_instance(handle)

    @unittest.skipUnless(os.name == "nt", "Windows mutex behavior is Windows-specific")
    def test_windows_mutex_rejects_second_instance(self):
        first = acquire_single_instance()
        try:
            second = acquire_single_instance()
            self.assertIsNotNone(first)
            self.assertIsNone(second)
            release_single_instance(second)
        finally:
            release_single_instance(first)


if __name__ == "__main__":
    unittest.main()
