"""Smoke-test a desktop build: start it headless, fetch data, run a small simulation.

Usage:
    python packaging/windows/smoke_test.py -- dist/nfl-playoff-sim/nfl-playoff-sim.exe
    python packaging/windows/smoke_test.py -- python -m src.desktop     # from source

Everything after `--` is the command to launch; `--no-window --port <port>
--data-dir <tmp> --season <season>` is appended. A simulation with
num_workers=2 exercises the spawned worker processes, which is what most
often breaks in a frozen build (missing freeze_support, missing OR-Tools DLLs).
Stdlib only, so it runs before/without installing the app's dependencies.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _request(base: str, method: str, path: str, body: dict | None = None, timeout: float = 120) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _wait_until_up(base: str, proc: subprocess.Popen, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"app exited early with code {proc.returncode}")
        try:
            return _request(base, "GET", "/api/status", timeout=5)
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(1)
    raise RuntimeError(f"server did not come up within {timeout:.0f}s")


def _kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        # Also kills the spawned simulation workers, which would otherwise keep
        # the build's DLLs locked.
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], check=False, capture_output=True)
    else:
        proc.terminate()
    proc.wait(timeout=30)


def main() -> int:
    if "--" not in sys.argv:
        print(__doc__)
        return 2
    split = sys.argv.index("--")
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--startup-timeout", type=float, default=90)
    args = parser.parse_args(sys.argv[1:split])
    command = sys.argv[split + 1 :]

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory() as data_dir:
        cmd = command + ["--no-window", "--port", str(port), "--data-dir", data_dir, "--season", str(args.season)]
        print("Launching:", " ".join(cmd), flush=True)
        proc = subprocess.Popen(cmd)
        try:
            status = _wait_until_up(base, proc, args.startup_timeout)
            print(f"Up: version {status.get('version')}, season {status.get('season_year')}", flush=True)

            # The frontend must be bundled, not just the API.
            with urllib.request.urlopen(base + "/", timeout=10) as resp:
                if b"<html" not in resp.read().lower():
                    raise RuntimeError("GET / did not return the frontend")

            fetched = _request(base, "POST", "/api/fetch-data", {}, timeout=300)
            print(f"Fetched {fetched.get('games_fetched')} games", flush=True)

            job = _request(base, "POST", "/api/simulate", {"iterations": 200, "cutoff_week": 14, "num_workers": 2})
            deadline = time.monotonic() + 600
            while True:
                state = _request(base, "GET", f"/api/simulate/status/{job['job_id']}")
                if state["status"] != "running":
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("simulation did not finish within 600s")
                time.sleep(2)
            if state["status"] != "completed":
                raise RuntimeError(f"simulation {state['status']}: {state.get('error')}")
            teams = state["result"]["team_results"]
            print(f"Simulation completed: {len(teams)} teams", flush=True)
            if len(teams) != 32:
                raise RuntimeError("expected 32 team results")

            # The CP solver answers 503 if OR-Tools failed to import (e.g. its
            # native DLLs in ortools/.libs weren't bundled); the server itself
            # still runs fine without it, so check explicitly.
            try:
                clinch = _request(base, "GET", "/api/cp-clinch-all?cutoff_week=17&time_limit=30", timeout=300)
            except urllib.error.HTTPError as exc:
                raise RuntimeError(f"CP solver unavailable (HTTP {exc.code}): {exc.read()[:200]!r}") from exc
            solved = sum(len(teams) for teams in clinch["conferences"].values())
            print(f"CP solver OK: {solved} teams solved", flush=True)
            if solved != 32:
                raise RuntimeError("expected CP results for 32 teams")
        finally:
            _kill_tree(proc)
    print("Smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
