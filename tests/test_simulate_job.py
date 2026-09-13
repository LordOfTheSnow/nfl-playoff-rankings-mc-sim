"""Tests for POST /api/simulate's background-job architecture.

POST /api/simulate used to block for the full duration of a simulation
(which can take minutes — see CHANGELOG) with no way to report progress or
stop early. It now starts the run in a background thread and returns a
job_id immediately; GET /api/simulate/status/{job_id} polls progress and the
eventual result, and POST /api/simulate/cancel/{job_id} requests a
best-effort stop. These tests exercise that orchestration using a
controllable fake Simulator (real progress/cancellation semantics inside
Simulator.run() itself are covered in test_impact_games.py and by direct
unit tests of _auto_detect_cutoff_week-adjacent code) so they run fast and
deterministically, without real multiprocessing.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import date
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from src.data_client import Game, GameStatus
from src.server import NFLRequestHandler, NFLSimulatorServer
from src.simulator import SimulationCancelled


class _FakeSimulationResult:
    """Stand-in for a real SimulationResult: only carries the two
    attributes _handle_post_simulate reads directly (for the lifetime
    games-simulated counter) -- the rest of the object is opaque to it,
    since _serialize_simulation_result is patched separately in tests
    that need a realistic response body."""

    iterations_run = 100
    simulated_games_count = 5


class FakeHandler(NFLRequestHandler):
    """A handler subclass that captures responses without real sockets
    (mirrors the pattern in test_cp_clinch_endpoint.py / test_season_shape.py)."""

    def __init__(self, path: str, server: NFLSimulatorServer, body: dict | None = None):
        self.path = path
        self.server = server
        self._body = body if body is not None else {}
        self.headers = {"Content-Length": "0"}
        self.rfile = BytesIO(b"")
        self.wfile = BytesIO()
        self._sent_code = None
        self._sent_headers: list[tuple[str, str]] = []

    def _parse_json_body(self) -> dict:
        return self._body

    def send_response(self, code, message=None):
        self._sent_code = code

    def send_header(self, keyword, value):
        self._sent_headers.append((keyword, value))

    def end_headers(self):
        pass

    def log_message(self, format, *args):
        pass

    def get_response_json(self) -> dict:
        return json.loads(self.wfile.getvalue().decode("utf-8"))


@pytest.fixture
def server_with_games() -> NFLSimulatorServer:
    server = NFLSimulatorServer(port=0, season_year=2026, db_path=":memory:")
    games = [
        Game(game_id="g1", week=1, date=date(2026, 9, 7), home_team="Bills", away_team="Jets",
             status=GameStatus.COMPLETED, home_score=24, away_score=10, home_points=24, away_points=10),
        Game(game_id="g2", week=2, date=date(2026, 9, 14), home_team="Bills", away_team="Dolphins",
             status=GameStatus.SCHEDULED),
    ]
    server.cache.store_games(games, 2026)
    yield server
    server.cache.close()


def _poll_until_terminal(handler_factory, job_id: str, timeout: float = 5.0) -> dict:
    """Poll GET /api/simulate/status/{job_id} until status != 'running'."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        handler = handler_factory(f"/api/simulate/status/{job_id}")
        handler._handle_get_simulate_status(f"/api/simulate/status/{job_id}")
        body = handler.get_response_json()
        if body["status"] != "running":
            return body
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} never left 'running' within {timeout}s")


class TestStartSimulationJob:
    def test_returns_202_with_job_id_and_running_status(self, server_with_games: NFLSimulatorServer) -> None:
        # The background thread runs concurrently with this test (starting a
        # job always spawns it) -- what matters here is that the
        # *synchronous* response doesn't wait for it. Still drain it before
        # returning (inside the patch context, and before the fixture closes
        # the shared SQLite connection out from under the still-running
        # thread) rather than leaving it dangling.
        fake_sim = MagicMock()
        fake_sim.run.side_effect = lambda *a, **kw: _FakeSimulationResult()
        with patch("src.server.Simulator", return_value=fake_sim), \
             patch("src.server._serialize_simulation_result", return_value={}):
            handler = FakeHandler("/api/simulate", server_with_games, body={"iterations": 100})
            handler._handle_post_simulate()

            assert handler._sent_code == 202
            body = handler.get_response_json()
            assert body["status"] == "running"
            job_id = body["job_id"]
            assert isinstance(job_id, str) and job_id

            _poll_until_terminal(lambda path: FakeHandler(path, server_with_games), job_id)

    def test_invalid_iterations_returns_400_synchronously_no_job_created(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        handler = FakeHandler("/api/simulate", server_with_games, body={"iterations": 1})
        handler._handle_post_simulate()

        assert handler._sent_code == 400
        assert server_with_games.simulation_jobs == {}


class TestSimulationJobProgressAndCompletion:
    def test_status_reports_progress_then_result(self, server_with_games: NFLSimulatorServer) -> None:
        reached_progress = threading.Event()
        release = threading.Event()

        def run_side_effect(games, progress_callback=None, cancel_check=None):
            progress_callback("Ranking impact games", 3, 10)
            reached_progress.set()
            assert release.wait(timeout=5), "test never released the fake run()"
            return _FakeSimulationResult()

        fake_sim = MagicMock()
        fake_sim.run.side_effect = run_side_effect

        with patch("src.server.Simulator", return_value=fake_sim), \
             patch("src.server._serialize_simulation_result", return_value={"team_results": []}):
            handler = FakeHandler("/api/simulate", server_with_games, body={"iterations": 100})
            handler._handle_post_simulate()
            job_id = handler.get_response_json()["job_id"]

            assert reached_progress.wait(timeout=5), "background job never reached run()"

            status_handler = FakeHandler(f"/api/simulate/status/{job_id}", server_with_games)
            status_handler._handle_get_simulate_status(f"/api/simulate/status/{job_id}")
            body = status_handler.get_response_json()
            assert body["status"] == "running"
            assert body["phase"] == "Ranking impact games"
            assert body["progress_done"] == 3
            assert body["progress_total"] == 10

            release.set()

            final = _poll_until_terminal(
                lambda path: FakeHandler(path, server_with_games), job_id
            )

        assert final["status"] == "completed"
        assert final["result"] == {"team_results": []}

    def test_unknown_job_id_returns_404(self, server_with_games: NFLSimulatorServer) -> None:
        handler = FakeHandler("/api/simulate/status/does-not-exist", server_with_games)
        handler._handle_get_simulate_status("/api/simulate/status/does-not-exist")
        assert handler._sent_code == 404


class TestSimulationJobCancellation:
    def test_cancel_stops_the_job_and_status_becomes_cancelled(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        def run_side_effect(games, progress_callback=None, cancel_check=None):
            for _ in range(200):
                if cancel_check is not None and cancel_check():
                    raise SimulationCancelled()
                time.sleep(0.01)
            raise AssertionError("cancel_check() never reported cancellation")

        fake_sim = MagicMock()
        fake_sim.run.side_effect = run_side_effect

        with patch("src.server.Simulator", return_value=fake_sim):
            handler = FakeHandler("/api/simulate", server_with_games, body={"iterations": 100})
            handler._handle_post_simulate()
            job_id = handler.get_response_json()["job_id"]

            cancel_handler = FakeHandler(f"/api/simulate/cancel/{job_id}", server_with_games)
            cancel_handler._handle_post_simulate_cancel(f"/api/simulate/cancel/{job_id}")
            assert cancel_handler._sent_code == 200

            final = _poll_until_terminal(
                lambda path: FakeHandler(path, server_with_games), job_id
            )

        assert final["status"] == "cancelled"

    def test_cancel_unknown_job_id_returns_404(self, server_with_games: NFLSimulatorServer) -> None:
        handler = FakeHandler("/api/simulate/cancel/does-not-exist", server_with_games)
        handler._handle_post_simulate_cancel("/api/simulate/cancel/does-not-exist")
        assert handler._sent_code == 404

    def test_cancel_on_already_finished_job_is_a_noop(self, server_with_games: NFLSimulatorServer) -> None:
        fake_sim = MagicMock()
        fake_sim.run.side_effect = lambda *a, **kw: _FakeSimulationResult()

        with patch("src.server.Simulator", return_value=fake_sim), \
             patch("src.server._serialize_simulation_result", return_value={}):
            handler = FakeHandler("/api/simulate", server_with_games, body={"iterations": 100})
            handler._handle_post_simulate()
            job_id = handler.get_response_json()["job_id"]

            _poll_until_terminal(lambda path: FakeHandler(path, server_with_games), job_id)

            cancel_handler = FakeHandler(f"/api/simulate/cancel/{job_id}", server_with_games)
            cancel_handler._handle_post_simulate_cancel(f"/api/simulate/cancel/{job_id}")

        assert cancel_handler._sent_code == 200
        assert cancel_handler.get_response_json()["status"] == "completed"


class TestJobPruning:
    def test_stale_finished_jobs_are_pruned_on_next_job_creation(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        from src.server import SimulationJob, SIMULATION_JOB_RETENTION_SECONDS

        stale_job = SimulationJob("stale")
        stale_job.status = "completed"
        stale_job.created_at = time.time() - SIMULATION_JOB_RETENTION_SECONDS - 1
        server_with_games.simulation_jobs["stale"] = stale_job

        fake_sim = MagicMock()
        fake_sim.run.side_effect = lambda *a, **kw: _FakeSimulationResult()

        with patch("src.server.Simulator", return_value=fake_sim), \
             patch("src.server._serialize_simulation_result", return_value={}):
            handler = FakeHandler("/api/simulate", server_with_games, body={"iterations": 100})
            handler._handle_post_simulate()
            new_job_id = handler.get_response_json()["job_id"]
            _poll_until_terminal(lambda path: FakeHandler(path, server_with_games), new_job_id)

        assert "stale" not in server_with_games.simulation_jobs

    def test_still_running_job_is_never_pruned_regardless_of_age(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        from src.server import SimulationJob, SIMULATION_JOB_RETENTION_SECONDS, _prune_finished_jobs

        old_running_job = SimulationJob("still-running")
        old_running_job.status = "running"
        old_running_job.created_at = time.time() - SIMULATION_JOB_RETENTION_SECONDS - 1000
        jobs = {"still-running": old_running_job}

        _prune_finished_jobs(jobs)

        assert "still-running" in jobs
