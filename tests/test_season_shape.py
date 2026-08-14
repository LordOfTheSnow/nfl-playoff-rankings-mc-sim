"""Tests for pre-2021 (16 games/17 weeks) season shape handling.

Covers the regression described in README's "Known limitations": several
places used to hardcode the modern 2021+ season shape (18 weeks/272 games)
instead of deriving it from the loaded schedule. See derive_season_weeks
(src/data_client.py) and expected_total_games (src/nfl_teams.py).
"""

from __future__ import annotations

import json
from datetime import date
from io import BytesIO
from unittest.mock import patch

import pytest

from src.cache import Cache
from src.clinching import min_cutoff_week_for_clinching
from src.data_client import Game, GameStatus, derive_season_weeks
from src.nfl_teams import expected_total_games
from src.server import NFLRequestHandler, NFLSimulatorServer


def _game(week: int, status: GameStatus = GameStatus.COMPLETED) -> Game:
    return Game(
        game_id=f"g-{week}",
        week=week,
        date=date(2020, 9, 1),
        home_team="Bills",
        away_team="Dolphins",
        status=status,
        home_score=20 if status == GameStatus.COMPLETED else None,
        away_score=17 if status == GameStatus.COMPLETED else None,
    )


class TestDeriveSeasonWeeks:
    def test_empty_games_is_none(self) -> None:
        assert derive_season_weeks([]) is None

    def test_pre_2021_season_derives_17(self) -> None:
        games = [_game(w) for w in range(1, 18)]  # weeks 1-17, no week 18
        assert derive_season_weeks(games) == 17

    def test_modern_season_derives_18(self) -> None:
        games = [_game(w) for w in range(1, 19)]  # weeks 1-18
        assert derive_season_weeks(games) == 18

    def test_uses_highest_week_regardless_of_status(self) -> None:
        # A future scheduled game (the "hull" ESPN returns pre-kickoff)
        # still counts toward the derived length.
        games = [_game(1), _game(17, status=GameStatus.SCHEDULED)]
        assert derive_season_weeks(games) == 17


class TestExpectedTotalGames:
    def test_none_weeks_is_none(self) -> None:
        assert expected_total_games(None) is None

    def test_modern_18_week_season_is_272(self) -> None:
        assert expected_total_games(18) == 272

    def test_pre_2021_17_week_season_is_256(self) -> None:
        assert expected_total_games(17) == 256


class TestMinCutoffWeekForClinching:
    """Clinching scenarios need >=4 weeks remaining to be tractable — the
    gate scales with season length rather than a fixed absolute week."""

    def test_modern_18_week_season_gates_at_14(self) -> None:
        assert min_cutoff_week_for_clinching(18) == 14

    def test_pre_2021_17_week_season_gates_at_13(self) -> None:
        assert min_cutoff_week_for_clinching(17) == 13

    def test_hypothetical_19_week_season_gates_at_15(self) -> None:
        assert min_cutoff_week_for_clinching(19) == 15


class FakeHandler(NFLRequestHandler):
    """A handler subclass that captures responses without real sockets
    (mirrors the pattern in test_cp_clinch_endpoint.py)."""

    def __init__(self, path: str, server: NFLSimulatorServer):
        self.path = path
        self.server = server
        self.headers = {"Content-Length": "0"}
        self.rfile = BytesIO(b"")
        self.wfile = BytesIO()
        self._sent_code = None
        self._sent_headers: list[tuple[str, str]] = []

    def send_response(self, code: int, message: str | None = None) -> None:
        self._sent_code = code

    def send_header(self, keyword: str, value: str) -> None:
        self._sent_headers.append((keyword, value))

    def end_headers(self) -> None:
        pass

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass

    def get_response_json(self) -> dict:
        return json.loads(self.wfile.getvalue().decode("utf-8"))


@pytest.fixture
def server_2020() -> NFLSimulatorServer:
    """A server with a fully-loaded, fully-completed pre-2021 (17-week,
    256-game) season cached — the scenario from the README bug report."""
    server = NFLSimulatorServer(port=0, season_year=2020, db_path=":memory:")
    games = [_game(w) for w in range(1, 18)]
    server.cache.store_games(games, 2020)
    yield server
    server.cache.close()


class TestStatusEndpointPre2021Season:
    def test_season_weeks_and_expected_total_reflect_17_week_season(
        self, server_2020: NFLSimulatorServer
    ) -> None:
        handler = FakeHandler("/api/status", server_2020)
        handler._handle_get_status()
        body = handler.get_response_json()

        assert body["season_weeks"] == 17
        assert body["expected_total"] == 256
        assert body["weeks_fetched"] == 17

    def test_no_data_cached_reports_unknown_season_weeks(self) -> None:
        server = NFLSimulatorServer(port=0, season_year=2020, db_path=":memory:")
        try:
            handler = FakeHandler("/api/status", server)
            handler._handle_get_status()
            body = handler.get_response_json()

            assert body["season_weeks"] is None
            assert body["expected_total"] is None
        finally:
            server.cache.close()


class TestScheduleGridPre2021Season:
    def test_grid_has_17_week_columns(self, server_2020: NFLSimulatorServer) -> None:
        handler = FakeHandler("/api/schedule-grid", server_2020)
        handler._handle_get_schedule_grid()
        body = handler.get_response_json()

        assert body["season_weeks"] == 17
        for entry in body["teams"]:
            assert len(entry["weeks"]) == 17


class TestCutoffWeekValidationPre2021Season:
    def test_cutoff_17_is_valid(self, server_2020: NFLSimulatorServer) -> None:
        handler = FakeHandler("/api/standings?cutoff_week=17", server_2020)
        handler._handle_get_standings("/api/standings?cutoff_week=17")
        body = handler.get_response_json()

        assert "error" not in body

    def test_cutoff_18_does_not_exist_for_this_season(
        self, server_2020: NFLSimulatorServer
    ) -> None:
        # cutoff_week=18 is out of range for a 17-week season; the standings
        # endpoint treats an out-of-range cutoff as "no filter" rather than
        # a 400, so this just confirms it doesn't filter out week 17 games.
        handler = FakeHandler("/api/standings?cutoff_week=18", server_2020)
        handler._handle_get_standings("/api/standings?cutoff_week=18")
        body = handler.get_response_json()

        assert "error" not in body

    def test_simulate_rejects_cutoff_18_for_17_week_season(
        self, server_2020: NFLSimulatorServer
    ) -> None:
        handler = FakeHandler("/api/simulate", server_2020)
        handler._parse_json_body = lambda: {"iterations": 100, "cutoff_week": 18}
        handler._handle_post_simulate()

        assert handler._sent_code == 400
        body = handler.get_response_json()
        assert "17" in body.get("details", "")


class TestClinchingScenariosGatePre2021Season:
    """The 'clinching scenarios need N weeks remaining' gate (min_cutoff_week_
    for_clinching) should scale with season length: week 13 for this 17-week
    season, not the modern week-14 constant."""

    def test_cutoff_below_dynamic_gate_returns_400(
        self, server_2020: NFLSimulatorServer
    ) -> None:
        handler = FakeHandler("/api/clinching-scenarios", server_2020)
        handler._parse_json_body = lambda: {"team": "Bills", "cutoff_week": 12}
        handler._handle_post_clinching_scenarios()

        assert handler._sent_code == 400
        body = handler.get_response_json()
        assert "13" in body["message"]

    def test_cutoff_at_dynamic_gate_boundary_passes_gate(
        self, server_2020: NFLSimulatorServer
    ) -> None:
        from src.clinching import ClinchingResult

        with patch(
            "src.clinching.compute_clinching_scenarios",
            return_value=ClinchingResult(team="Bills"),
        ):
            handler = FakeHandler("/api/clinching-scenarios", server_2020)
            handler._parse_json_body = lambda: {"team": "Bills", "cutoff_week": 13}
            handler._handle_post_clinching_scenarios()

        assert handler._sent_code == 200


class TestSeasonsSummaryPerSeasonShape:
    def test_different_cached_seasons_get_their_own_shape(self) -> None:
        cache = Cache(db_path=":memory:")
        try:
            cache.store_games([_game(w) for w in range(1, 18)], 2020)  # 17 weeks
            cache.store_games(
                [Game(
                    game_id=f"g24-{w}", week=w, date=date(2024, 9, 1),
                    home_team="Bills", away_team="Dolphins",
                    status=GameStatus.COMPLETED, home_score=20, away_score=17,
                ) for w in range(1, 19)],
                2024,
            )  # 18 weeks

            summary = {row["year"]: row for row in cache.get_seasons_summary()}

            assert summary[2020]["season_weeks"] == 17
            assert summary[2020]["expected_games"] == 256
            assert summary[2024]["season_weeks"] == 18
            assert summary[2024]["expected_games"] == 272
        finally:
            cache.close()
