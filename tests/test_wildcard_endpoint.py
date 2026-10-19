"""Tests for POST /api/wildcard (src/server.py's _handle_post_wildcard).

Uses the same FakeHandler-over-a-real-server pattern as test_export.py,
since this endpoint reuses the real standings/cp-clinch-all computation via
_capture_json_response rather than duplicating it.
"""

from __future__ import annotations

import json
from datetime import date
from io import BytesIO

import pytest

from src.data_client import Game, GameStatus
from src.server import NFLRequestHandler, NFLSimulatorServer


class FakeHandler(NFLRequestHandler):
    def __init__(self, path: str, server: NFLSimulatorServer, body: dict | None = None):
        self.path = path
        self.server = server
        self._body = body
        self.headers = {"Content-Length": "0"}
        self.rfile = BytesIO(b"")
        self.wfile = BytesIO()
        self._sent_code: int | None = None
        self._sent_headers: list[tuple[str, str]] = []

    def _parse_json_body(self) -> dict | None:
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
             status=GameStatus.COMPLETED, home_score=20, away_score=20, home_points=20, away_points=20),
        Game(game_id="g3", week=3, date=date(2026, 9, 21), home_team="Chiefs", away_team="Broncos",
             status=GameStatus.COMPLETED, home_score=31, away_score=17, home_points=31, away_points=17),
        Game(game_id="g4", week=4, date=date(2026, 9, 28), home_team="Bills", away_team="Patriots",
             status=GameStatus.SCHEDULED),
    ]
    server.cache.store_games(games, 2026)
    yield server
    server.cache.close()


SAMPLE_SIM_RESULT = {
    "team_results": [
        {
            "team": "Bills", "conference": "AFC", "division": "East", "record": "1-0-1",
            "playoff_probability": 55.5, "strength_rating": 1.05,
            "seed_probabilities": {"1": 60, "2": 10, "3": 10, "4": 5, "5": 5, "6": 5, "7": 0.5},
        },
        {
            "team": "Jets", "conference": "AFC", "division": "East", "record": "0-1-0",
            "playoff_probability": 10.0, "strength_rating": 0.9,
            "seed_probabilities": {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 10, "7": 20},
        },
    ],
    "top_scenarios": [{"afc_seeds": ["Bills"], "nfc_seeds": [], "probability": 12.3}],
    "iterations_run": 5000,
    "cutoff_week_used": 3,
    "low_confidence": False,
    "convergence_achieved": True,
    "team_strengths": {"Bills": 1.05, "Jets": 0.9},
    "fixed_games": 3,
    "simulated_games": 269,
}


class TestWildcardEndpointActual:
    def test_returns_16_teams_per_conference_seeded_1_to_16(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        handler = FakeHandler("/api/wildcard", server_with_games, body={"source": "actual", "cutoff_week": 3})
        handler._handle_post_wildcard()

        assert handler._sent_code == 200
        data = handler.get_response_json()
        assert data["source"] == "actual"
        assert data["cutoff_week"] == 3
        for conf in ("AFC", "NFC"):
            teams = data["conferences"][conf]
            assert len(teams) == 16
            assert [t["seed"] for t in teams] == list(range(1, 17))

    def test_auto_detects_cutoff_when_omitted(self, server_with_games: NFLSimulatorServer) -> None:
        handler = FakeHandler("/api/wildcard", server_with_games, body={"source": "actual"})
        handler._handle_post_wildcard()
        assert handler._sent_code == 200
        data = handler.get_response_json()
        assert isinstance(data["cutoff_week"], int)

    def test_no_cached_data_returns_409(self) -> None:
        empty_server = NFLSimulatorServer(port=0, season_year=2099, db_path=":memory:")
        try:
            handler = FakeHandler("/api/wildcard", empty_server, body={"source": "actual"})
            handler._handle_post_wildcard()
            assert handler._sent_code == 409
        finally:
            empty_server.cache.close()


class TestWildcardEndpointSimulated:
    def test_valid_simulation_result_returns_200(self, server_with_games: NFLSimulatorServer) -> None:
        handler = FakeHandler(
            "/api/wildcard", server_with_games,
            body={"source": "simulated", "simulation_result": SAMPLE_SIM_RESULT},
        )
        handler._handle_post_wildcard()

        assert handler._sent_code == 200
        data = handler.get_response_json()
        assert data["source"] == "simulated"
        assert data["cutoff_week"] == 3
        assert data["iterations"] == 5000
        afc_teams = {t["team"] for t in data["conferences"]["AFC"]}
        assert {"Bills", "Jets"} <= afc_teams

    def test_missing_simulation_result_returns_400(self, server_with_games: NFLSimulatorServer) -> None:
        handler = FakeHandler("/api/wildcard", server_with_games, body={"source": "simulated"})
        handler._handle_post_wildcard()
        assert handler._sent_code == 400

    def test_malformed_simulation_result_returns_400(self, server_with_games: NFLSimulatorServer) -> None:
        handler = FakeHandler(
            "/api/wildcard", server_with_games,
            body={"source": "simulated", "simulation_result": {"team_results": "nope"}},
        )
        handler._handle_post_wildcard()
        assert handler._sent_code == 400


class TestWildcardEndpointValidation:
    def test_invalid_source_returns_400(self, server_with_games: NFLSimulatorServer) -> None:
        handler = FakeHandler("/api/wildcard", server_with_games, body={"source": "bogus"})
        handler._handle_post_wildcard()
        assert handler._sent_code == 400

    def test_malformed_json_body_returns_400(self, server_with_games: NFLSimulatorServer) -> None:
        handler = FakeHandler("/api/wildcard", server_with_games, body=None)
        handler._handle_post_wildcard()
        assert handler._sent_code == 400
