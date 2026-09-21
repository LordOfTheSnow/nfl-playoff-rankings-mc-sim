"""Early-season division ordering: teams with different numbers of games played.

A 1-0 team and a 2-0 team share win percentage 1.000, and a 0-0 team and a
0-1 team share 0.0, but they aren't genuinely tied — the 2-0 team is strictly
ahead of the 1-0 team (games_behind 0.5). Regression tests for a bug where
`determine_playoff_bracket` and `GET /api/standings` still grouped teams by win
percentage alone, ran the tiebreaker cascade across them, and so could rank
(and crown as division champion) the 1-0 team ahead of the 2-0 team — while
`games_behind` already named the 2-0 team the leader.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.data_client import Game, GameStatus
from src.server import NFLSimulatorServer
from src.standings import (
    _sort_teams_by_record,
    _standing_tie_key,
    compute_standings,
    determine_playoff_bracket,
)
from tests.test_season_shape import FakeHandler


def _completed(
    game_id: str, week: int, home: str, away: str, home_score: int, away_score: int
) -> Game:
    return Game(
        game_id=game_id,
        week=week,
        date=date(2024, 9, week),
        home_team=home,
        away_team=away,
        status=GameStatus.COMPLETED,
        home_score=home_score,
        away_score=away_score,
        home_points=home_score,
        away_points=away_score,
        quarter=None,
        clock=None,
    )


def _games_where_one_win_team_looks_better_on_tiebreakers() -> list[Game]:
    """AFC East: Bills 2-0 (beat two non-division AFC teams), Jets 1-0 (beat
    a division rival). Under the old win%-only grouping the Jets won the
    division on the "Div" step (1-0 vs 0-0 in division play), even though the
    Bills have the strictly better record."""
    return [
        _completed("g1", 1, "Bills", "Ravens", 24, 10),
        _completed("g2", 2, "Bills", "Chiefs", 27, 13),
        _completed("g3", 2, "Jets", "Dolphins", 20, 13),
    ]


class TestStandingTieKey:
    def test_more_wins_at_same_perfect_record_is_higher(self) -> None:
        assert _standing_tie_key(1.0, 2, 0) > _standing_tie_key(1.0, 1, 0)

    def test_fewer_losses_at_same_winless_record_is_higher(self) -> None:
        assert _standing_tie_key(0.0, 0, 0) > _standing_tie_key(0.0, 0, 1)
        assert _standing_tie_key(0.0, 0, 1) > _standing_tie_key(0.0, 0, 2)

    def test_same_percentage_and_margin_is_a_genuine_tie(self) -> None:
        assert _standing_tie_key(0.5, 1, 1) == _standing_tie_key(0.5, 2, 2)


class TestDivisionChampion:
    def test_two_and_oh_team_beats_one_and_oh_team_despite_tiebreakers(self) -> None:
        games = _games_where_one_win_team_looks_better_on_tiebreakers()
        standings = compute_standings(games)
        determine_playoff_bracket(standings, all_games=games)

        bills = next(s for s in standings if s.team == "Bills")
        jets = next(s for s in standings if s.team == "Jets")

        assert bills.is_division_champion is True
        assert jets.is_division_champion is False
        assert bills.games_behind == 0.0
        assert jets.games_behind == 0.5

    def test_fallback_sort_without_games_also_ranks_by_margin(self) -> None:
        games = _games_where_one_win_team_looks_better_on_tiebreakers()
        standings = compute_standings(games)
        east = [
            s for s in standings if s.team in {"Bills", "Dolphins", "Jets", "Patriots"}
        ]

        ordered = [s.team for s in _sort_teams_by_record(east)]

        # Bills 2-0, Jets 1-0, Patriots 0-0, Dolphins 0-1
        assert ordered == ["Bills", "Jets", "Patriots", "Dolphins"]


@pytest.fixture
def server_with_partial_week() -> NFLSimulatorServer:
    server = NFLSimulatorServer(port=0, season_year=2024, db_path=":memory:")
    server.cache.store_games(_games_where_one_win_team_looks_better_on_tiebreakers(), 2024)
    yield server
    server.cache.close()


class TestStandingsEndpointOrder:
    def test_division_rows_follow_record_not_tiebreak_cascade(
        self, server_with_partial_week: NFLSimulatorServer
    ) -> None:
        handler = FakeHandler("/api/standings", server_with_partial_week)
        handler._handle_get_standings("/api/standings")
        east = handler.get_response_json()["conferences"]["AFC"]["East"]

        assert [t["team"] for t in east] == ["Bills", "Jets", "Patriots", "Dolphins"]
        by_team = {t["team"]: t for t in east}
        # Only genuinely tied teams get a tiebreaker badge.
        assert "tiebreaker" not in by_team["Bills"]
        assert "tiebreaker" not in by_team["Jets"]
        assert by_team["Bills"]["is_division_champion"] is True
        assert by_team["Jets"]["is_division_champion"] is False

    def test_genuinely_tied_zero_zero_teams_still_get_alpha_badge(self) -> None:
        server = NFLSimulatorServer(port=0, season_year=2024, db_path=":memory:")
        try:
            # Only a game outside AFC East, so all four AFC East teams are 0-0-0.
            server.cache.store_games([_completed("g1", 1, "Chiefs", "Ravens", 20, 10)], 2024)
            handler = FakeHandler("/api/standings", server)
            handler._handle_get_standings("/api/standings")
            east = handler.get_response_json()["conferences"]["AFC"]["East"]

            assert [t["team"] for t in east] == ["Bills", "Dolphins", "Jets", "Patriots"]
            assert all(t["tiebreaker"] == "Alpha" for t in east)
        finally:
            server.cache.close()
