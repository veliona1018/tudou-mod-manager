import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import app_logging
from mod_server import _diagnostic_archive, deepseek_analyze_log


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

    def test_read_and_clear_rotated_logs(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"LOCALAPPDATA": temporary}, clear=False):
                app_logging.write_log("before clear", component="test")
                path = app_logging.log_path()
                path.with_name("manager.log.1").write_text("old entry", encoding="utf-8")

                info = app_logging.read_log()
                self.assertIn("before clear", info["content"])
                self.assertEqual(len(app_logging.log_files()), 2)

                self.assertEqual(app_logging.clear_logs(), 2)
                self.assertFalse(path.exists())
                app_logging.write_log("after clear", component="test")
                self.assertIn("after clear", path.read_text(encoding="utf-8"))
                app_logging.close_logging()

    def test_diagnostic_archive_contains_logs_without_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"LOCALAPPDATA": temporary}, clear=False):
                app_logging.write_log("diagnostic entry", component="test")
                payload = _diagnostic_archive(Path(temporary), Path(temporary))
                app_logging.close_logging()

            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                self.assertIn("logs/manager.log", archive.namelist())
                self.assertIn("environment.txt", archive.namelist())
                self.assertNotIn(".l4d2_mod_manager.json", archive.namelist())
                self.assertIn("diagnostic entry", archive.read("logs/manager.log").decode("utf-8"))

    @patch("mod_server._deepseek_chat", return_value="发现一次扫描异常")
    def test_log_analysis_uses_log_specific_prompt(self, deepseek_chat):
        result = deepseek_analyze_log("ERROR 无法读取 Mod 目录", "test-key", "deepseek-chat")

        self.assertEqual(result, "发现一次扫描异常")
        prompt = deepseek_chat.call_args.args[0]
        self.assertIn("运行日志：", prompt)
        self.assertIn("ERROR 无法读取 Mod 目录", prompt)
        self.assertEqual(deepseek_chat.call_args.args[1:], (
            "test-key",
            "deepseek-chat",
            "你是一个谨慎的桌面应用运行日志分析助手，只根据日志证据作答。",
        ))


if __name__ == "__main__":
    unittest.main()
