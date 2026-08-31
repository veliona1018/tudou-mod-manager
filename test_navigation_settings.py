import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_server import navigation_order, save_navigation_order


class NavigationSettingsTests(unittest.TestCase):
    def test_navigation_order_is_saved_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = Path(temporary) / "settings.json"
            with patch("mod_server.settings_path", return_value=settings):
                save_navigation_order(["library", "spray", "spray", "settings"])

                self.assertEqual(navigation_order(), ["library", "spray", "settings"])
                self.assertEqual(
                    json.loads(settings.read_text(encoding="utf-8"))["navOrder"],
                    ["library", "spray", "settings"],
                )


if __name__ == "__main__":
    unittest.main()
