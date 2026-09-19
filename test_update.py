import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from mod_server import (
    UpdateError,
    _find_update_executable,
    _find_source_root,
    _latest_release,
    _select_update_asset,
    save_update_source,
    update_config,
    update_source,
    _validate_direct_executable,
    _version_key,
    _get_update_progress,
    _initial_update_progress,
    _download_update,
    schedule_update,
    _write_update_script,
    _set_update_progress,
    update_info,
)


class UpdateTests(unittest.TestCase):
    def test_update_progress_returns_an_isolated_snapshot(self):
        class Server:
            pass

        server = Server()
        server.update_progress_lock = threading.Lock()
        server.update_progress = _initial_update_progress()
        _set_update_progress(
            server,
            active=True,
            phase="downloading",
            downloadedBytes=5,
            totalBytes=10,
            percent=50,
        )
        snapshot = _get_update_progress(server)
        self.assertEqual(snapshot["phase"], "downloading")
        self.assertEqual(snapshot["percent"], 50)
        snapshot["percent"] = 0
        self.assertEqual(_get_update_progress(server)["percent"], 50)

    def test_download_update_reports_download_and_validation_progress(self):
        class ChunkedResponse:
            headers = {"Content-Length": "8"}

            def __init__(self):
                self.chunks = iter([b"MZ12", b"3456", b""])

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, _size):
                return next(self.chunks)

        with tempfile.TemporaryDirectory() as temporary:
            events = []
            release = {
                "assetName": "update.exe",
                "assetUrl": "https://example.com/update.exe",
                "assetSize": 8,
            }
            with patch.dict("os.environ", {"LOCALAPPDATA": temporary}, clear=False):
                with patch("mod_server.urllib.request.urlopen", return_value=ChunkedResponse()):
                    package = _download_update(release, Path(temporary) / "manager.exe", lambda changes: events.append(changes))
            self.assertEqual(package.read_bytes(), b"MZ123456")
            package.unlink()
            self.assertEqual(events[0]["phase"], "downloading")
            self.assertIn("validating", [event.get("phase") for event in events])

    def test_update_script_clears_pyinstaller_child_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary) / "update.ps1"
            _write_update_script(script)
            content = script.read_text(encoding="utf-8-sig")
            self.assertIn("_PYI_ARCHIVE_FILE", content)
            self.assertIn("_PYI_PARENT_PROCESS_LEVEL", content)
            self.assertIn("_PYI_APPLICATION_HOME_DIR", content)
            self.assertIn("PYINSTALLER_RESET_ENVIRONMENT", content)

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

    def test_source_update_archive_requires_project_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "source.zip"
            with zipfile.ZipFile(archive, "w") as package:
                for name in ("desktop_app.py", "mod_server.py", "index.html"):
                    package.writestr(f"tudou-mod-manager-v0.4/{name}", "placeholder")
            self.assertEqual(_find_source_root(archive), "tudou-mod-manager-v0.4")

    def test_source_update_archive_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "unsafe-source.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("../desktop_app.py", "placeholder")
            with self.assertRaises(UpdateError):
                _find_source_root(archive)

    def test_update_asset_can_prefer_source_archive(self):
        assets = [
            {"name": "TudouManager-v0.4.exe", "browser_download_url": "https://github.com/example/release.exe"},
            {"name": "TudouManager-v0.4-source.zip", "browser_download_url": "https://github.com/example/source.zip"},
        ]
        self.assertEqual(_select_update_asset(assets, preferred_extension=".zip")["name"], "TudouManager-v0.4-source.zip")

    def test_source_update_script_contains_restart_arguments(self):
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary) / "source-update.ps1"
            from mod_server import _write_source_update_script

            _write_source_update_script(script)
            content = script.read_text(encoding="utf-8-sig")
            self.assertIn("ProjectRoot", content)
            self.assertIn("PythonPath", content)
            self.assertIn("Start-Process", content)

    def test_development_mode_schedules_source_update_and_restart(self):
        import mod_server

        with tempfile.TemporaryDirectory() as temporary:
            project_root = Path(temporary) / "project"
            project_root.mkdir()
            package = Path(temporary) / "source.zip"
            package.write_bytes(b"source package")
            # Keep this fixture comfortably newer than any normal local release.
            # Otherwise a version bump can make the update-path test silently
            # exercise the already-current branch instead.
            release = {
                "version": "99.0",
                "versionKey": _version_key("99.0"),
                "assetName": "TudouManager-v99.0-source.zip",
            }
            with patch.dict("os.environ", {"LOCALAPPDATA": temporary}, clear=False):
                with patch.object(mod_server.sys, "frozen", False, create=True):
                    with patch("mod_server.resource_root", return_value=project_root):
                        with patch("mod_server._latest_release", return_value=release) as latest:
                            with patch("mod_server._download_update", return_value=package) as download:
                                with patch("mod_server.shutil.which", return_value="powershell.exe"):
                                    with patch("mod_server.subprocess.Popen") as popen:
                                        result = schedule_update()

            self.assertTrue(result["restartScheduled"])
            latest.assert_called_once_with("github", preferred_extension=".zip")
            self.assertEqual(download.call_args.kwargs["package_kind"], "source")
            command = popen.call_args.args[0]
            self.assertIn("-ProjectRoot", command)
            self.assertIn(str(project_root), command)
            self.assertIn("-LauncherScript", command)
            self.assertIn(str(project_root / "desktop_app.py"), command)

    def test_update_archive_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("../土豆管理器.exe", b"placeholder")
            with self.assertRaises(UpdateError):
                _find_update_executable(archive, "土豆管理器.exe")


if __name__ == "__main__":
    unittest.main()
