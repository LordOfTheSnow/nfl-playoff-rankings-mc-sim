"""Tests that all auto-cutoff-detection call sites agree with each other.

Before this change, four places in server.py each reimplemented "auto-detect
the cutoff week" inline, using the old "latest FULLY completed week" rule
(with inconsistent fallbacks of 0 or 1). They've been unified to call the one
shared, fixed _auto_detect_cutoff_week (src/simulator.py), which now resolves
to the latest week with *any* completed game.

Each test below uses a fixture where week 1 is fully complete and week 2 is
only partially complete (1 of 2 games decided) — a scenario where the old
"fully complete week" rule and the new "any completed game" rule disagree
(old: cutoff=1, new: cutoff=2). A passing test here proves the call site is
actually wired to the new shared function, not just coincidentally correct.
"""

from __future__ import annotations

import json
from datetime import date
from io import BytesIO
from unittest.mock import patch

import pytest

from src.cp_solver import CPSolverResult
from src.data_client import Game, GameStatus
from src.nfl_teams import ALL_TEAMS
from src.server import NFLRequestHandler, NFLSimulatorServer


def _completed(game_id: str, week: int, home: str, away: str) -> Game:
    return Game(
        game_id=game_id, week=week, date=date(2026, 9, 7),
        home_team=home, away_team=away, status=GameStatus.COMPLETED,
        home_score=24, away_score=17, home_points=24, away_points=17,
    )


def _scheduled(game_id: str, week: int, home: str, away: str) -> Game:
    return Game(
        game_id=game_id, week=week, date=date(2026, 12, 1),
        home_team=home, away_team=away, status=GameStatus.SCHEDULED,
    )


class FakeHandler(NFLRequestHandler):
    """A handler subclass that captures responses without real sockets
    (mirrors the pattern in test_cp_clinch_endpoint.py / test_season_shape.py)."""

    def __init__(self, path: str, server: NFLSimulatorServer):
        self.path = path
        self.server = server
        self.headers = {"Content-Length": "0"}
        self.rfile = BytesIO(b"")
        self.wfile = BytesIO()
        self._sent_code = None
        self._sent_headers: list[tuple[str, str]] = []

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
def server_partial_week2() -> NFLSimulatorServer:
    """Week 1 fully complete, week 2 only half-decided, week 3 not started.

    A week-18 scheduled placeholder is included so derive_season_weeks
    resolves to 18, matching a real fetched season shape.
    """
    server = NFLSimulatorServer(port=0, season_year=2026, db_path=":memory:")
    games = [
        _completed("g1", 1, "Bills", "Jets"),
        _completed("g2", 1, "Dolphins", "Patriots"),
        _completed("g3", 2, "Bills", "Dolphins"),
        _scheduled("g4", 2, "Jets", "Patriots"),
        _scheduled("g5", 3, "Bills", "Patriots"),
        _scheduled("g6", 3, "Dolphins", "Jets"),
        _scheduled("g7", 18, "Bills", "Jets"),
    ]
    server.cache.store_games(games, 2026)
    yield server
    server.cache.close()


class TestStatusEndpointAutoCutoff:
    def test_auto_cutoff_week_is_the_partial_week_not_the_last_fully_complete_one(
        self, server_partial_week2: NFLSimulatorServer
    ) -> None:
        handler = FakeHandler("/api/status", server_partial_week2)
        handler._handle_get_status()
        body = handler.get_response_json()

        assert body["auto_cutoff_week"] == 2
        # weeks_completed (fully-complete week count) stays a separate stat.
        assert body["weeks_completed"] == 1

    def test_completed_per_week_reports_per_week_completed_counts(
        self, server_partial_week2: NFLSimulatorServer
    ) -> None:
        handler = FakeHandler("/api/status", server_partial_week2)
        handler._handle_get_status()
        body = handler.get_response_json()

        assert body["completed_per_week"] == {"1": 2, "2": 1}


class TestCpClinchAutoDetectPartialWeek:
    def test_single_team_endpoint_uses_new_rule(
        self, server_partial_week2: NFLSimulatorServer
    ) -> None:
        with patch("src.server.solve_clinch") as mock_solve:
            mock_solve.return_value = CPSolverResult(team="Bills")
            handler = FakeHandler("/api/cp-clinch/Bills", server_partial_week2)
            handler._handle_get_cp_clinch("/api/cp-clinch/Bills")

        assert handler._sent_code == 200
        assert mock_solve.call_args[0][2] == 2

    def test_all_teams_endpoint_uses_new_rule(
        self, server_partial_week2: NFLSimulatorServer
    ) -> None:
        mock_results = {team: CPSolverResult(team=team) for team in ALL_TEAMS}
        with patch(
            "src.server.solve_clinch",
            side_effect=lambda t, g, c, cfg=None: mock_results[t],
        ):
            handler = FakeHandler("/api/cp-clinch-all", server_partial_week2)
            handler._handle_get_cp_clinch_all("/api/cp-clinch-all")
            body = handler.get_response_json()

        assert handler._sent_code == 200
        assert body["cutoff_week"] == 2


class TestClinchEstimateAutoDetectPartialWeek:
    def test_uses_new_rule(self, server_partial_week2: NFLSimulatorServer) -> None:
        with patch("src.clinching.estimate_clinching", return_value={}) as mock_estimate:
            handler = FakeHandler("/api/clinch-estimate?team=Bills", server_partial_week2)
            handler._handle_get_clinch_estimate()
            body = handler.get_response_json()

        assert handler._sent_code == 200
        assert body["cutoff_week"] == 2
        assert mock_estimate.call_args[0][2] == 2


class TestClinchingScenariosAutoDetectPartialWeek:
    def test_uses_new_rule(self, server_partial_week2: NFLSimulatorServer) -> None:
        handler = FakeHandler("/api/clinching-scenarios", server_partial_week2)
        handler._parse_json_body = lambda: {"team": "Bills"}
        handler._handle_post_clinching_scenarios()
        body = handler.get_response_json()

        # season_weeks=18 -> min_cutoff=14; auto-detected cutoff (2) fails
        # the gate, and the error message echoes the resolved value, proving
        # the new rule (not the old "1") produced it.
        assert handler._sent_code == 400
        assert "got: 2" in body["details"]
