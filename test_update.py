import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from mod_server import (
    UpdateError,
    _find_update_executable,
    _latest_release,
    _select_update_asset,
    save_update_source,
    update_config,
    update_source,
    _validate_direct_executable,
    _version_key,
    update_info,
)


class UpdateTests(unittest.TestCase):
    def test_version_key_compares_common_release_formats(self):
        self.assertEqual(_version_key("v0.2"), (0, 2, 0))
        self.assertLess(_version_key("0.2"), _version_key("v0.2.1"))
        self.assertLess(_version_key("v0.9"), _version_key("v1.0"))
        self.assertLess(_version_key("v0.32"), _version_key("v0.4"))

    def test_update_info_marks_newer_release(self):
        release = {
            "version": "0.32",
            "versionKey": (0, 32, 0),
            "name": "土豆管理器 v0.32",
            "releaseUrl": "https://github.com/veliona1018/tudou-mod-manager/releases/tag/v0.32",
            "publishedAt": "2026-08-28T00:00:00Z",
            "notes": "测试版本",
            "assetName": "TudouManager-v0.32.exe",
            "assetSize": 123,
        }
        with patch("mod_server._latest_release", return_value=release):
            result = update_info()
        self.assertTrue(result["updateAvailable"])
        self.assertEqual(result["latestVersion"], "0.32")

    def test_update_asset_prefers_manager_executable(self):
        assets = [
            {"name": "TudouManager-v0.31.exe", "browser_download_url": "https://github.com/example/release.exe"},
            {"name": "source.zip", "browser_download_url": "https://github.com/example/source.zip"},
        ]
        self.assertEqual(_select_update_asset(assets)["name"], "TudouManager-v0.31.exe")

    def test_update_asset_accepts_gitee_download_url(self):
        assets = [{"name": "TudouManager-v0.4.exe", "browser_download_url": "https://gitee.com/example/release/download/v0.4/TudouManager-v0.4.exe"}]
        self.assertEqual(_select_update_asset(assets, {"gitee.com"})["name"], "TudouManager-v0.4.exe")

    def test_latest_release_normalizes_gitee_download_url(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({
                    "tag_name": "v0.4",
                    "name": "土豆管理器 v0.4",
                    "assets": [{
                        "name": "TudouManager-v0.4.exe",
                        "download_url": "https://gitee.com/veliona1018/tudou-mod-manager/releases/download/v0.4/TudouManager-v0.4.exe",
                        "size": 123,
                    }],
                }).encode("utf-8")

        with patch("mod_server.urllib.request.urlopen", return_value=FakeResponse()):
            release = _latest_release("gitee")
        self.assertEqual(release["updateSource"], "gitee")
        self.assertEqual(release["assetUrl"].split("://", 1)[0], "https")

    def test_update_source_is_saved_and_exposed(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict("os.environ", {"LOCALAPPDATA": temporary}, clear=False):
                save_update_source("gitee")
                self.assertEqual(update_source(), "gitee")
                self.assertEqual(update_config()["updateSource"], "gitee")

    def test_update_asset_falls_back_to_zip(self):
        assets = [{"name": "TudouManager-v0.31.zip", "browser_download_url": "https://github.com/example/update.zip"}]
        self.assertEqual(_select_update_asset(assets)["name"], "TudouManager-v0.31.zip")

    def test_direct_executable_requires_pe_header(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "update.exe"
            package.write_bytes(b"MZplaceholder")
            _validate_direct_executable(package)

            package.write_bytes(b"not an exe")
            with self.assertRaises(UpdateError):
                _validate_direct_executable(package)

    def test_update_archive_requires_a_manager_executable(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "update.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("土豆管理器.exe", b"placeholder")
            self.assertEqual(_find_update_executable(archive, "土豆管理器.exe"), "土豆管理器.exe")

    def test_update_archive_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("../土豆管理器.exe", b"placeholder")
            with self.assertRaises(UpdateError):
                _find_update_executable(archive, "土豆管理器.exe")


if __name__ == "__main__":
    unittest.main()
