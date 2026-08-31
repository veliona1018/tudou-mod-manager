"""Launch the local Mod manager as a standalone Windows app window."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from mod_server import load_last_folder, resource_root, run_server


APP_TITLE = "土豆 Mod 管理器"


def find_browser() -> str | None:
    candidates = [
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which("msedge") or shutil.which("chrome")


def find_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def log(message: str) -> None:
    """Write diagnostics when a console is available."""
    if sys.stdout is not None:
        print(message)


def app_profile_dir() -> Path:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.cwd()))
    profile = local_app_data / "L4D2ModManager" / "BrowserProfile"
    profile.mkdir(parents=True, exist_ok=True)
    return profile


def start_server(root: Path, port: int) -> subprocess.Popen:
    if getattr(sys, "frozen", False):
        command = [sys.executable, "--server", str(root), "--port", str(port)]
    else:
        server_script = Path(__file__).with_name("mod_server.py")
        command = [sys.executable, str(server_script), str(root), "--port", str(port)]
    return subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def stop_server(server_process: subprocess.Popen | None) -> None:
    if not server_process or server_process.poll() is not None:
        return
    server_process.terminate()
    try:
        server_process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        server_process.kill()
        server_process.wait(timeout=3)


def apply_window_icon(process: subprocess.Popen, icon_path: Path) -> None:
    """Apply the manager icon to the Edge app window shown on the taskbar."""
    if os.name != "nt" or not icon_path.is_file():
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.LoadImageW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.SendMessageW.restype = ctypes.c_ssize_t
        user32.DestroyIcon.argtypes = [wintypes.HANDLE]
        user32.DestroyIcon.restype = wintypes.BOOL

        image_icon = 1
        load_from_file = 0x00000010
        default_size = 0x00000040
        wm_seticon = 0x0080
        icon_small = 0
        icon_big = 1
        icon = user32.LoadImageW(None, str(icon_path), image_icon, 0, 0, load_from_file | default_size)
        if not icon:
            return

        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            found_window = False

            @callback_type
            def collect_window(hwnd, _lparam):
                nonlocal found_window
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                if buffer.value != APP_TITLE:
                    return True
                user32.SendMessageW(hwnd, wm_seticon, icon_big, icon)
                user32.SendMessageW(hwnd, wm_seticon, icon_small, icon)
                found_window = True
                return False

            user32.EnumWindows(collect_window, 0)
            if found_window:
                break
            time.sleep(0.25)
        user32.DestroyIcon(icon)
    except (AttributeError, OSError, TypeError, ValueError):
        # The browser can still run with its default icon if native APIs fail.
        return


def wait_for_browser_window() -> None:
    """Keep the local server alive until the browser app window is closed."""
    if os.name != "nt":
        input("Press Enter to stop the Mod manager... ")
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.IsWindow.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def find_window():
            found = []

            @callback_type
            def collect_window(hwnd, _lparam):
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                if buffer.value == APP_TITLE:
                    found.append(hwnd)
                    return False
                return True

            user32.EnumWindows(collect_window, 0)
            return found[0] if found else None

        deadline = time.monotonic() + 20
        window = None
        while time.monotonic() < deadline:
            window = find_window()
            if window:
                break
            time.sleep(0.25)
        if not window:
            return
        while user32.IsWindow(window):
            time.sleep(0.25)
    except (AttributeError, OSError, TypeError, ValueError):
        input("Press Enter to stop the Mod manager... ")


def source_signature(project_root: Path) -> tuple[tuple[str, int, int], ...]:
    paths = [project_root / "index.html", project_root / "app.js", project_root / "styles.css"]
    paths.extend(sorted(project_root.glob("*.py")))
    signature = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        signature.append((path.name, stat.st_mtime_ns, stat.st_size))
    return tuple(signature)


def watch_server(
    project_root: Path,
    fallback_root: Path,
    port: int,
    state: dict[str, subprocess.Popen],
    state_lock: threading.Lock,
    stop_event: threading.Event,
) -> None:
    last_signature = source_signature(project_root)
    while not stop_event.wait(0.5):
        current_signature = source_signature(project_root)
        if current_signature == last_signature:
            continue
        last_signature = current_signature
        with state_lock:
            if stop_event.is_set():
                return
            stop_server(state["process"])
            root = load_last_folder(project_root)
            if not root.is_dir():
                root = fallback_root
            state["process"] = start_server(root, port)


def open_app_window(url: str) -> tuple[subprocess.Popen | None, Path | None]:
    browser = find_browser()
    if browser:
        profile_dir = app_profile_dir()
        process = subprocess.Popen(
            [
                browser,
                f"--app={url}",
                "--new-window",
                "--window-size=1440,900",
                f"--user-data-dir={profile_dir}",
                "--disable-extensions",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-sync",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        icon_path = resource_root() / "assets" / "tudou-logo.ico"
        threading.Thread(target=apply_window_icon, args=(process, icon_path), daemon=True).start()
        return process, profile_dir
    webbrowser.open(url, new=1)
    return None, None


def main() -> None:
    parser = argparse.ArgumentParser(description="Open the L4D2 Mod manager window")
    parser.add_argument("folder", nargs="?", type=Path, default=None)
    parser.add_argument("--check", action="store_true", help="Check the desktop launcher without opening a window")
    parser.add_argument("--no-watch", action="store_true", help="Disable automatic source hot reload")
    parser.add_argument("--port", type=int, default=8765, help=argparse.SUPPRESS)
    parser.add_argument("--server", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.server:
        root = args.folder.resolve() if args.folder else load_last_folder(Path.cwd().resolve())
        run_server(root, args.port, resource_root())
        return

    root = args.folder.resolve() if args.folder else load_last_folder(Path.cwd().resolve())
    if not root.is_dir():
        raise SystemExit(f"Mod folder does not exist: {root}")

    browser = find_browser()
    if args.check:
        print(f"folder={root}")
        print(f"browser={browser or 'system default browser'}")
        return

    port = find_port()
    project_root = resource_root()
    server_process = start_server(root, port)
    url = f"http://127.0.0.1:{port}/"
    log(f"Opening Mod manager: {url}")
    browser_process, _profile_dir = open_app_window(url)
    stop_event = threading.Event()
    state_lock = threading.Lock()
    state = {"process": server_process}
    watcher = None
    if not args.no_watch and not getattr(sys, "frozen", False):
        watcher = threading.Thread(
            target=watch_server,
            args=(project_root, root, port, state, state_lock, stop_event),
            daemon=True,
        )
        watcher.start()
    try:
        if browser_process:
            wait_for_browser_window()
        else:
            input("Press Enter to stop the Mod manager... ")
    except KeyboardInterrupt:
        pass
    finally:
        if browser_process and browser_process.poll() is None:
            browser_process.terminate()
        stop_event.set()
        if watcher:
            watcher.join(timeout=2)
        with state_lock:
            stop_server(state["process"])


if __name__ == "__main__":
    main()
