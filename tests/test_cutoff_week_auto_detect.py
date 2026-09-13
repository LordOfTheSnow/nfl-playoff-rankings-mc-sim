"""Tests for auto-detection of the simulation cutoff week.

_auto_detect_cutoff_week resolves the cutoff week to use when a request
doesn't specify one explicitly. It must land on the highest week containing
at least one completed game, even when that week isn't fully played out yet
-- otherwise a week's already-decided games are silently ignored until every
game in it finishes (see CHANGELOG / doc/algorithms.md for the "auto cutoff
week" design note).
"""

from __future__ import annotations

from datetime import date

from src.data_client import Game, GameStatus
from src.simulator import _auto_detect_cutoff_week


def _game(game_id: str, week: int, status: GameStatus) -> Game:
    is_completed = status == GameStatus.COMPLETED
    return Game(
        game_id=game_id,
        week=week,
        date=date(2026, 9, 7),
        home_team="Bills",
        away_team="Jets",
        status=status,
        home_score=24 if is_completed else None,
        away_score=17 if is_completed else None,
        home_points=24 if is_completed else None,
        away_points=17 if is_completed else None,
        quarter=None,
        clock=None,
    )


class TestAutoDetectCutoffWeek:
    def test_no_games_returns_zero(self) -> None:
        assert _auto_detect_cutoff_week([]) == 0

    def test_no_completed_games_returns_zero(self) -> None:
        games = [
            _game("g1", 1, GameStatus.SCHEDULED),
            _game("g2", 1, GameStatus.SCHEDULED),
        ]
        assert _auto_detect_cutoff_week(games) == 0

    def test_partial_week_with_one_completed_game_resolves_to_that_week(self) -> None:
        # Week 1, only 2 of 16 games decided -- the reported bug scenario.
        games = [
            _game("g1", 1, GameStatus.COMPLETED),
            _game("g2", 1, GameStatus.COMPLETED),
        ] + [_game(f"s{i}", 1, GameStatus.SCHEDULED) for i in range(14)]
        assert _auto_detect_cutoff_week(games) == 1

    def test_fully_completed_week_resolves_to_that_week(self) -> None:
        games = [_game(f"g{i}", 2, GameStatus.COMPLETED) for i in range(16)]
        assert _auto_detect_cutoff_week(games) == 2

    def test_advances_to_latest_week_with_any_completed_game(self) -> None:
        # Weeks 1-9 fully complete, week 10 partially complete, week 11+ untouched.
        games = [_game(f"g{w}", w, GameStatus.COMPLETED) for w in range(1, 10)]
        games += [
            _game("w10a", 10, GameStatus.COMPLETED),
            _game("w10b", 10, GameStatus.IN_PROGRESS),
            _game("w10c", 10, GameStatus.SCHEDULED),
        ]
        games += [_game("w11a", 11, GameStatus.SCHEDULED)]
        assert _auto_detect_cutoff_week(games) == 10

    def test_in_progress_games_alone_do_not_advance_cutoff(self) -> None:
        games = [
            _game("g1", 1, GameStatus.COMPLETED),
            _game("g2", 2, GameStatus.IN_PROGRESS),
        ]
        assert _auto_detect_cutoff_week(games) == 1

    def test_postponed_game_does_not_block_a_later_completed_game(self) -> None:
        games = [
            _game("g1", 3, GameStatus.POSTPONED),
            _game("g2", 4, GameStatus.COMPLETED),
        ]
        assert _auto_detect_cutoff_week(games) == 4
