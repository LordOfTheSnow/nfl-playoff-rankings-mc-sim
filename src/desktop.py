"""Desktop launcher: runs the server in-process and shows it in a native window.

This is the entry point of the Windows build (see packaging/windows/), but it
also runs from source for development:

    python -m src.desktop               # native window (needs pywebview)
    python -m src.desktop --no-window   # server only, e.g. for the CI smoke test

Unlike `python -m src`, the server binds to 127.0.0.1 on a free port (unless
--port is given), and the cache DB, solver-performance export and log file
live in a per-user data directory rather than the working directory.

The window is a pywebview (Edge WebView2) window. Its js_api exposes
`save_file(filename, base64)` so the frontend's downloads (Export, Teaser
images) can go through a native Save-As dialog -- see `_downloadBlob` in
frontend/js/export.js. If the webview cannot start (e.g. no WebView2 runtime),
the app falls back to the default browser and keeps the server alive until a
message box is dismissed.
"""

from __future__ import annotations

import argparse
import base64
import logging
import multiprocessing
import os
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

from src.server import NFLSimulatorServer

logger = logging.getLogger(__name__)

APP_DIR_NAME = "nfl-playoff-sim"
WINDOW_TITLE = "NFL Playoff Rankings Sim"


def default_data_dir() -> Path:
    """Per-user data directory: %LOCALAPPDATA% on Windows, XDG data home elsewhere."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    if not base:
        base = str(Path.home() / ".local" / "share")
    return Path(base) / APP_DIR_NAME


def default_static_dir() -> Path:
    """The frontend/ directory: bundled next to the code when frozen, repo root otherwise."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "frontend"
    return Path(__file__).resolve().parent.parent / "frontend"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the desktop launcher."""
    parser = argparse.ArgumentParser(
        prog="nfl-playoff-sim",
        description="NFL Playoff Rankings Monte Carlo Simulator — desktop app",
    )
    parser.add_argument("--port", type=int, default=0, help="Port to listen on (default: a free port)")
    parser.add_argument(
        "--season",
        type=int,
        default=datetime.now().year,
        help=f"NFL season year (default: {datetime.now().year})",
    )
    parser.add_argument("--data-dir", type=str, default=None, help="Directory for the cache DB and log file")
    parser.add_argument("--no-window", action="store_true", help="Run the server only, without a window")
    return parser.parse_args(argv)


def _configure_logging(data_dir: Path) -> None:
    handlers: list[logging.Handler] = [logging.FileHandler(data_dir / "app.log", encoding="utf-8")]
    # A windowed (no-console) build has no stderr to log to.
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


class DesktopApi:
    """Methods callable from the page as `window.pywebview.api.<name>()`."""

    def __init__(self) -> None:
        self.window = None

    def save_file(self, filename: str, data_base64: str) -> bool:
        """Ask for a target path with a native Save dialog and write the file.

        Returns True if the file was written, False if the dialog was cancelled.
        """
        import webview

        save_mode = getattr(getattr(webview, "FileDialog", None), "SAVE", None) or webview.SAVE_DIALOG
        result = self.window.create_file_dialog(save_mode, save_filename=filename)
        if not result:
            return False
        # Backends differ: some return a path string, some a 1-tuple.
        path = result if isinstance(result, str) else result[0]
        Path(path).write_bytes(base64.b64decode(data_base64))
        logger.info("Saved %s", path)
        return True


def _unblock_bundled_dlls() -> None:
    """Remove the "downloaded from the internet" mark from the frozen build's own DLLs.

    Extracting a downloaded ZIP with Explorer copies its Mark of the Web (a
    `Zone.Identifier` alternate data stream) onto every file, and the .NET
    Framework refuses to load marked assemblies -- pythonnet then fails with
    "Failed to resolve Python.Runtime.Loader.Initialize" and no window opens.
    Deleting the stream is what Explorer's "Unblock" does; the user already
    chose to run this exe, so this only covers its own bundled files.
    """
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    bundle_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    unblocked = 0
    for dll in bundle_dir.rglob("*.dll"):
        try:
            os.remove(f"{dll}:Zone.Identifier")
            unblocked += 1
        except FileNotFoundError:
            continue
        except OSError as exc:
            logger.warning("Could not unblock %s: %s", dll, exc)
    if unblocked:
        logger.info("Removed the download mark from %d bundled DLLs", unblocked)


def _webview2_installed() -> bool | None:
    """Whether the Edge WebView2 Runtime is installed (None if it can't be checked).

    Uses the registry keys Microsoft documents for detecting the Evergreen runtime.
    """
    if sys.platform != "win32":
        return None
    import winreg

    client = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    for root, key in (
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\{client}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\{client}"),
        (winreg.HKEY_CURRENT_USER, rf"Software\{client}"),
    ):
        try:
            with winreg.OpenKey(root, key) as handle:
                version, _ = winreg.QueryValueEx(handle, "pv")
        except OSError:
            continue
        if version and version != "0.0.0.0":
            return True
    return False


def _show_window(url: str) -> bool:
    """Show the app in a native window; return False if the webview could not start."""
    _unblock_bundled_dlls()
    try:
        import webview

        api = DesktopApi()
        api.window = webview.create_window(
            WINDOW_TITLE, url, js_api=api, width=1400, height=900, min_size=(900, 600)
        )
        # Force Edge WebView2: never silently fall back to an IE-based renderer.
        webview.start(gui="edgechromium" if sys.platform == "win32" else None)
        return True
    except Exception:
        logger.exception("Could not start the native window; falling back to the default browser")
        return False


def _browser_fallback(url: str, server_thread: threading.Thread, log_path: Path) -> None:
    """Open the default browser and keep serving until the user quits."""
    webbrowser.open(url)
    if sys.platform == "win32":
        import ctypes

        if _webview2_installed() is False:
            reason = "The app window needs the Microsoft Edge WebView2 Runtime, which is not installed."
        else:
            reason = f"The app window could not be opened. Details are in:\n{log_path}"
        message = f"{reason}\n\nThe app is running in your browser instead:\n{url}\n\nClick OK to quit."
        ctypes.windll.user32.MessageBoxW(0, message, WINDOW_TITLE, 0x40)  # MB_ICONINFORMATION
    else:
        print(f"Running at {url} — press Ctrl+C to quit.")
        try:
            server_thread.join()
        except KeyboardInterrupt:
            pass


def _shutdown(server: NFLSimulatorServer) -> None:
    server.shutdown()
    server.server_close()
    server.cache.close()
    server.data_client.close()
    # Simulation workers may still be mid-run; don't leave them orphaned.
    for child in multiprocessing.active_children():
        child.terminate()


def main(argv: list[str] | None = None) -> None:
    """Start the server on localhost and show it in a window (or browser)."""
    multiprocessing.freeze_support()
    args = parse_args(argv)

    data_dir = Path(args.data_dir) if args.data_dir else default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    _configure_logging(data_dir)

    server = NFLSimulatorServer(
        port=args.port,
        season_year=args.season,
        static_dir=str(default_static_dir()),
        db_path=str(data_dir / "nfl_cache.db"),
        perf_export_path=str(data_dir / "solver-performance.md"),
        host="127.0.0.1",
    )
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    logger.info("Server v%s listening on %s (season %d, data in %s)", server.version, url, args.season, data_dir)

    server_thread = threading.Thread(target=server.serve_forever, name="http-server", daemon=True)
    server_thread.start()

    try:
        if args.no_window:
            print(url, flush=True)
            server_thread.join()
        elif not _show_window(url):
            _browser_fallback(url, server_thread, data_dir / "app.log")
    except KeyboardInterrupt:
        pass
    finally:
        _shutdown(server)


if __name__ == "__main__":
    main()
