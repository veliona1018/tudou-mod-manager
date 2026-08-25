"""Launch the local Mod manager as a standalone Windows app window."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

from mod_server import load_last_folder


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


def app_profile_dir() -> Path:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.cwd()))
    sessions = local_app_data / "L4D2ModManager" / "Sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="session-", dir=sessions))


def start_server(root: Path, port: int) -> subprocess.Popen:
    server_script = Path(__file__).with_name("mod_server.py")
    return subprocess.Popen(
        [sys.executable, str(server_script), str(root), "--port", str(port)],
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
        return process, profile_dir
    webbrowser.open(url, new=1)
    return None, None


def main() -> None:
    parser = argparse.ArgumentParser(description="Open the L4D2 Mod manager window")
    parser.add_argument("folder", nargs="?", type=Path, default=None)
    parser.add_argument("--check", action="store_true", help="Check the desktop launcher without opening a window")
    parser.add_argument("--no-watch", action="store_true", help="Disable automatic source hot reload")
    args = parser.parse_args()

    root = args.folder.resolve() if args.folder else load_last_folder(Path.cwd().resolve())
    if not root.is_dir():
        raise SystemExit(f"Mod folder does not exist: {root}")

    browser = find_browser()
    if args.check:
        print(f"folder={root}")
        print(f"browser={browser or 'system default browser'}")
        return

    port = find_port()
    project_root = Path(__file__).parent.resolve()
    server_process = start_server(root, port)
    url = f"http://127.0.0.1:{port}/"
    print(f"Opening Mod manager: {url}")
    browser_process, profile_dir = open_app_window(url)
    stop_event = threading.Event()
    state_lock = threading.Lock()
    state = {"process": server_process}
    watcher = None
    if not args.no_watch:
        watcher = threading.Thread(
            target=watch_server,
            args=(project_root, root, port, state, state_lock, stop_event),
            daemon=True,
        )
        watcher.start()
    try:
        if browser_process:
            browser_process.wait()
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
        if profile_dir:
            shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
