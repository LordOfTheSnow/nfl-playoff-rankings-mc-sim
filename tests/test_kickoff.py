"""Tests for the UTC kickoff timestamp: the games table's kickoff columns in
src/cache.py (round-trip, migration of databases created before the columns
existed, kickoff-based freshness check) and its serialization in the API."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.cache import Cache
from src.data_client import Game, GameStatus
from src.server import _serialize_simulation_result
from src.simulator import MatchupOutcome, SimulationResult

_kickoffs = st.datetimes(
    min_value=datetime(2020, 9, 1),
    max_value=datetime(2030, 2, 1),
    timezones=st.just(UTC),
).map(lambda dt: dt.replace(microsecond=0))


def _game(
    kickoff: datetime | None,
    status: GameStatus = GameStatus.SCHEDULED,
    time_valid: bool = True,
    game_id: str = "g1",
    week: int = 7,
) -> Game:
    completed = status == GameStatus.COMPLETED
    return Game(
        game_id=game_id,
        week=week,
        date=(kickoff or datetime(2026, 10, 23, tzinfo=UTC)).date(),
        home_team="Bears",
        away_team="Patriots",
        status=status,
        home_score=30 if completed else None,
        away_score=24 if completed else None,
        home_points=30 if completed else None,
        away_points=24 if completed else None,
        kickoff=kickoff,
        kickoff_time_valid=time_valid,
    )


@given(kickoff=_kickoffs, time_valid=st.booleans())
@settings(max_examples=50)
def test_kickoff_round_trips_through_cache(kickoff: datetime, time_valid: bool) -> None:
    cache = Cache(":memory:")
    cache.store_games([_game(kickoff, time_valid=time_valid)], 2026)

    (stored,) = cache.get_games(2026, 7)
    assert stored.kickoff == kickoff
    assert stored.kickoff.tzinfo is not None
    assert stored.kickoff_time_valid is time_valid
    (team_game,) = cache.get_team_games(2026, "Bears")
    assert team_game.kickoff == kickoff


def test_completed_game_with_kickoff_is_fresh() -> None:
    cache = Cache(":memory:")
    past = datetime.now(UTC) - timedelta(days=2)
    cache.store_games([_game(past, GameStatus.COMPLETED)], 2026)
    assert cache.is_fresh(2026, 7) is True


def test_game_without_kickoff_is_stale() -> None:
    """Rows cached before the kickoff column existed force a backfill."""
    cache = Cache(":memory:")
    cache.store_games([_game(None, GameStatus.COMPLETED)], 2026)
    assert cache.is_fresh(2026, 7) is False


@pytest.mark.parametrize(
    ("offset", "fresh"),
    [(timedelta(hours=2), True), (timedelta(minutes=-1), False)],
)
def test_scheduled_game_stale_once_kickoff_passed(offset: timedelta, fresh: bool) -> None:
    cache = Cache(":memory:")
    cache.store_games([_game(datetime.now(UTC) + offset)], 2026)
    assert cache.is_fresh(2026, 7) is fresh


def test_scheduled_night_game_fresh_after_utc_midnight(monkeypatch) -> None:
    """A Sunday-night game is not stale just because its UTC date arrived.

    The old date-only check compared the UTC date with today, so at 8:05pm
    ET (00:05Z Monday) an 8:20pm ET kickoff (00:20Z) already counted as
    "today"; the kickoff check only goes stale once the game has started.
    """
    frozen_now = datetime(2026, 10, 26, 0, 5, tzinfo=UTC)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D102
            return frozen_now

    monkeypatch.setattr("src.cache.datetime", _FrozenDatetime)
    cache = Cache(":memory:")
    cache.store_games([_game(datetime(2026, 10, 26, 0, 20, tzinfo=UTC))], 2026)
    assert cache.is_fresh(2026, 7) is True


def test_migration_adds_kickoff_columns(tmp_path) -> None:
    """A database from before the kickoff columns gets them on open."""
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE games (
            game_id TEXT PRIMARY KEY, year INTEGER NOT NULL, week INTEGER NOT NULL,
            game_date TEXT NOT NULL, home_team TEXT NOT NULL, away_team TEXT NOT NULL,
            status TEXT NOT NULL, home_score INTEGER, away_score INTEGER,
            home_points INTEGER, away_points INTEGER, quarter TEXT, clock TEXT,
            fetched_at TEXT NOT NULL)"""
    )
    conn.execute(
        "INSERT INTO games VALUES ('g1', 2026, 7, '2026-10-23', 'Bears', 'Patriots',"
        " 'completed', 30, 24, 30, 24, NULL, NULL, ?)",
        (datetime.now(UTC).isoformat(),),
    )
    conn.commit()
    conn.close()

    cache = Cache(str(db_path))

    (game,) = cache.get_games(2026, 7)
    assert game.kickoff is None
    assert game.kickoff_time_valid is True
    assert cache.is_fresh(2026, 7) is False

    kickoff = datetime(2026, 10, 23, 0, 15, tzinfo=UTC)
    cache.store_games([_game(kickoff, GameStatus.COMPLETED)], 2026)
    assert cache.get_games(2026, 7)[0].kickoff == kickoff
    assert cache.is_fresh(2026, 7) is True


def test_matchups_serialize_kickoff() -> None:
    kickoff = datetime(2026, 10, 23, 0, 15, tzinfo=UTC)
    result = SimulationResult(
        team_results={}, scenarios=[], iterations_run=100, cutoff_week=7,
        low_confidence=True, team_strengths={}, matchups_week=7,
        next_week_matchups=[
            MatchupOutcome(
                game_id="g1", week=7, date=kickoff.date(), home_team="Bears",
                away_team="Patriots", home_win_probability=0.5,
                away_win_probability=0.5, tie_probability=0.0, kickoff=kickoff,
            ),
            MatchupOutcome(
                game_id="g2", week=7, date=kickoff.date(), home_team="Bills",
                away_team="Jets", home_win_probability=0.5,
                away_win_probability=0.5, tie_probability=0.0,
            ),
        ],
    )

    first, second = _serialize_simulation_result(result)["next_week_matchups"]

    assert datetime.fromisoformat(first["kickoff"]) == kickoff
    assert first["kickoff_time_valid"] is True
    assert second["kickoff"] is None
