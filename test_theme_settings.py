import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_server import save_ui_theme, theme_config, ui_theme


class ThemeSettingsTests(unittest.TestCase):
    def test_theme_defaults_to_dark_and_persists(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = Path(temporary) / "settings.json"
            with patch("mod_server.settings_path", return_value=settings):
                self.assertEqual(ui_theme(), "dark")
                save_ui_theme("light")
                self.assertEqual(theme_config(), {"theme": "light"})
                self.assertEqual(
                    json.loads(settings.read_text(encoding="utf-8"))["theme"],
                    "light",
                )

    def test_invalid_theme_is_rejected(self):
        with self.assertRaises(ValueError):
            save_ui_theme("blue")

    def test_invalid_saved_theme_falls_back_to_dark(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = Path(temporary) / "settings.json"
            settings.write_text(json.dumps({"theme": "blue"}), encoding="utf-8")
            with patch("mod_server.settings_path", return_value=settings):
                self.assertEqual(ui_theme(), "dark")


if __name__ == "__main__":
    unittest.main()
