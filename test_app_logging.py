import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app_logging


class AppLoggingTests(unittest.TestCase):
    def tearDown(self):
        app_logging.close_logging()

    def test_log_is_written_under_local_app_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"LOCALAPPDATA": temporary}, clear=False):
                app_logging.write_log("scan started", component="test")
                path = app_logging.log_path()

            self.assertEqual(path, Path(temporary) / "L4D2ModManager" / "logs" / "manager.log")
            self.assertIn("[test] scan started", path.read_text(encoding="utf-8"))
            app_logging.close_logging()

    def test_logging_failure_does_not_escape(self):
        with patch.object(Path, "mkdir", side_effect=OSError("read-only")):
            app_logging.write_log("still starts", component="test")


if __name__ == "__main__":
    unittest.main()
