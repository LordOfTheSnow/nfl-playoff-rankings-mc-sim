"""Desktop launcher: runs the server in-process, opens the browser, shows a control window.

This is the entry point of the Windows build (see packaging/windows/), but it
also runs from source for development:

    python -m src.desktop               # browser + control window (needs tkinter)
    python -m src.desktop --no-window   # server only, e.g. for the CI smoke test

Unlike `python -m src`, the server binds to 127.0.0.1 only, and the cache DB,
solver-performance export, log file and settings live in a per-user data
directory rather than the working directory.

The app runs in the user's default browser. A small tkinter control window
keeps it alive: it shows the URL and version, lets the user change the port
(remembered in settings.json; first launch uses DEFAULT_PORT), reopen the
browser, open the data folder, and quit -- closing the window quits too. If the
saved port already answers as this app, a second launch just opens the browser
on it and exits.
"""

from __future__ import annotations

import argparse
import json
import logging
import multiprocessing
import os
import socket
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

from src.server import NFLSimulatorServer

logger = logging.getLogger(__name__)

APP_DIR_NAME = "nfl-playoff-rankings-mc-sim"
WINDOW_TITLE = "NFL Playoff Rankings Sim"
DEFAULT_PORT = 8765
SETTINGS_FILE = "settings.json"


def default_data_dir() -> Path:
    """Per-user data directory: %LOCALAPPDATA% on Windows, XDG data home elsewhere."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    if not base:
        base = str(Path.home() / ".local" / "share")
    return Path(base) / APP_DIR_NAME


def _bundle_dir() -> Path:
    """Where bundled resources live: _internal/ when frozen, the repo root otherwise."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def default_static_dir() -> Path:
    """The frontend/ directory: bundled next to the code when frozen, repo root otherwise."""
    return _bundle_dir() / "frontend"


def app_version() -> str:
    """Installed package version, as NFLSimulatorServer reports it."""
    try:
        from importlib.metadata import version

        return version("nfl-playoff-rankings-mc-sim")
    except Exception:
        return "unknown"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the desktop launcher."""
    parser = argparse.ArgumentParser(
        prog="nfl-playoff-rankings-mc-sim",
        description="NFL Playoff Rankings Monte Carlo Simulator — desktop app",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Port to listen on (default: the saved port, initially {DEFAULT_PORT}; "
        "with --no-window, a free port)",
    )
    parser.add_argument(
        "--season",
        type=int,
        default=datetime.now().year,
        help=f"NFL season year (default: {datetime.now().year})",
    )
    parser.add_argument("--data-dir", type=str, default=None, help="Directory for the cache DB, log and settings")
    parser.add_argument("--no-window", action="store_true", help="Run the server only: no browser, no window")
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


def valid_port(port: object) -> bool:
    """Ports the user may pick: unprivileged TCP ports."""
    return isinstance(port, int) and not isinstance(port, bool) and 1024 <= port <= 65535


def load_port(data_dir: Path) -> int:
    """The saved port from settings.json, or DEFAULT_PORT if none/invalid."""
    try:
        port = json.loads((data_dir / SETTINGS_FILE).read_text(encoding="utf-8")).get("port")
    except (OSError, ValueError, AttributeError):
        return DEFAULT_PORT
    return port if valid_port(port) else DEFAULT_PORT


def save_port(data_dir: Path, port: int) -> None:
    """Remember the port in settings.json, keeping any other settings."""
    path = data_dir / SETTINGS_FILE
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(settings, dict):
            settings = {}
    except (OSError, ValueError):
        settings = {}
    settings["port"] = port
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def url_for(port: int) -> str:
    return f"http://127.0.0.1:{port}/"


def is_running_instance(port: int, timeout: float = 1.0) -> bool:
    """Whether this app is already serving on 127.0.0.1:<port>."""
    try:
        with urllib.request.urlopen(url_for(port) + "api/status", timeout=timeout) as resp:
            status = json.loads(resp.read())
    except Exception:
        return False
    # Any other local web server would have to fake the exact /api/status shape.
    return isinstance(status, dict) and "season_year" in status and "version" in status


class LocalServer(NFLSimulatorServer):
    """NFLSimulatorServer that refuses a port another program already uses.

    HTTPServer sets SO_REUSEADDR, which on Windows lets a second socket bind a
    port that is already taken -- a busy port would then silently "work" while
    the other program keeps receiving the connections. Ask for exclusive use
    there instead (Linux/macOS REUSEADDR doesn't allow that, so keep it).
    """

    allow_reuse_address = sys.platform != "win32"

    def server_bind(self) -> None:
        if sys.platform == "win32":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class ServerHandle:
    """One running LocalServer and its serving thread."""

    def __init__(self, server: LocalServer) -> None:
        self.server = server
        self.port: int = server.server_address[1]
        self.url = url_for(self.port)
        self.thread = threading.Thread(target=server.serve_forever, name="http-server", daemon=True)
        self.thread.start()

    @classmethod
    def start(cls, port: int, season_year: int, data_dir: Path) -> ServerHandle:
        """Bind 127.0.0.1:<port> (0 = any free port) and serve. Raises OSError if the port is taken."""
        server = LocalServer(
            port=port,
            season_year=season_year,
            static_dir=str(default_static_dir()),
            db_path=str(data_dir / "nfl_cache.db"),
            perf_export_path=str(data_dir / "solver-performance.md"),
            host="127.0.0.1",
        )
        handle = cls(server)
        logger.info(
            "Server v%s listening on %s (season %d, data in %s)", server.version, handle.url, season_year, data_dir
        )
        return handle

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server.cache.close()
        self.server.data_client.close()


def _terminate_workers() -> None:
    # Simulation workers may still be mid-run; don't leave them orphaned.
    for child in multiprocessing.active_children():
        child.terminate()


def _open_folder(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]  # Windows-only
    else:
        subprocess.Popen(["xdg-open", str(path)])


class ControlWindow:
    """The small tkinter window that keeps the app running."""

    def __init__(self, data_dir: Path, season_year: int, port: int) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.data_dir = data_dir
        self.season_year = season_year
        self.handle: ServerHandle | None = None

        self.root = tk.Tk()
        self.root.title(f"{WINDOW_TITLE} v{app_version()}")
        self.root.resizable(False, False)
        icon = _bundle_dir() / "icon.ico"
        if sys.platform == "win32" and icon.is_file():
            self.root.iconbitmap(str(icon))
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        frame = ttk.Frame(self.root, padding=12)
        # Keep the content left-aligned when _fit_title makes the window wider.
        frame.grid(sticky="nw")
        self.status = ttk.Label(frame, wraplength=360, justify="left")
        self.status.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))

        ttk.Label(frame, text="Port:").grid(row=1, column=0, sticky="w")
        self.port_var = tk.StringVar(value=str(port))
        port_entry = ttk.Entry(frame, textvariable=self.port_var, width=7)
        port_entry.grid(row=1, column=1, sticky="w", padx=(4, 4))
        port_entry.bind("<Return>", lambda _event: self.apply_port())
        ttk.Button(frame, text="Apply", command=self.apply_port).grid(row=1, column=2, sticky="w")

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, columnspan=4, sticky="w", pady=(12, 0))
        self.open_button = ttk.Button(buttons, text="Open in browser", command=self.open_browser)
        self.open_button.grid(row=0, column=0, padx=(0, 6))
        ttk.Button(buttons, text="Open data folder", command=lambda: _open_folder(self.data_dir)).grid(
            row=0, column=1, padx=(0, 6)
        )
        ttk.Button(buttons, text="Quit", command=self.quit).grid(row=0, column=2)

        self._start_on(port, open_browser=True)
        self._fit_title()

    def _fit_title(self) -> None:
        """Widen the window so the title bar shows the whole title (incl. version).

        Tk sizes the window to its widgets only, which leaves the title clipped.
        TkCaptionFont is the system's title-bar font; the extra allowance covers
        the window icon, the minimize/maximize/close buttons and padding, scaled
        from 96 dpi to the display's DPI.
        """
        from tkinter import font

        self.root.update_idletasks()
        scale = self.root.winfo_fpixels("1i") / 96
        title_width = font.nametofont("TkCaptionFont").measure(self.root.title())
        width = max(self.root.winfo_reqwidth(), title_width + int(190 * scale))
        self.root.minsize(width, self.root.winfo_reqheight())

    def _start_on(self, port: int, open_browser: bool) -> bool:
        """Switch the server to <port>; on failure keep the current one running."""
        try:
            new_handle = ServerHandle.start(port, self.season_year, self.data_dir)
        except OSError as exc:
            logger.warning("Could not listen on port %d: %s", port, exc)
            current = f"\n\nStill running at {self.handle.url}" if self.handle else ""
            self.status.configure(
                text=f"Port {port} is in use by another program. Choose another port and click Apply.{current}"
            )
            self.open_button.state(["!disabled"] if self.handle else ["disabled"])
            return False

        if self.handle is not None:
            # Keep the season the user switched to in the UI.
            self.season_year = self.handle.server.season_year
            new_handle.server.season_year = self.season_year
            self.handle.stop()
            _terminate_workers()
        self.handle = new_handle
        save_port(self.data_dir, port)
        self.status.configure(text=f"Running at {new_handle.url}\n\nClose this window to quit the app.")
        self.open_button.state(["!disabled"])
        if open_browser:
            self.open_browser()
        return True

    def apply_port(self) -> None:
        text = self.port_var.get().strip()
        port = int(text) if text.isdigit() else None
        if port is None or not valid_port(port):
            self.status.configure(text="Enter a port number between 1024 and 65535.")
            return
        if self.handle is not None and port == self.handle.port:
            return
        self._start_on(port, open_browser=True)

    def open_browser(self) -> None:
        if self.handle is not None:
            webbrowser.open(self.handle.url)

    def quit(self) -> None:
        logger.info("Shutting down")
        if self.handle is not None:
            self.handle.stop()
        _terminate_workers()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main(argv: list[str] | None = None) -> None:
    """Start the server on localhost; open the browser and the control window."""
    multiprocessing.freeze_support()
    args = parse_args(argv)

    data_dir = Path(args.data_dir) if args.data_dir else default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    _configure_logging(data_dir)

    if args.no_window:
        handle = ServerHandle.start(args.port or 0, args.season, data_dir)
        print(handle.url, flush=True)
        try:
            handle.thread.join()
        except KeyboardInterrupt:
            pass
        finally:
            handle.stop()
            _terminate_workers()
        return

    port = args.port if valid_port(args.port) else load_port(data_dir)
    if is_running_instance(port):
        logger.info("Already running on port %d; opening the browser", port)
        webbrowser.open(url_for(port))
        return

    ControlWindow(data_dir, args.season, port).run()


if __name__ == "__main__":
    main()
