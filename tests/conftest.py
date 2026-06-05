"""Shared test fixtures for NFL Monte Carlo simulator tests."""

from datetime import date

import pytest

from src.data_client import Game, GameStatus
from src.nfl_teams import ALL_TEAMS, NFL_TEAMS


@pytest.fixture
def all_teams() -> list[str]:
    """All 32 NFL team abbreviations as a flat list."""
    return ALL_TEAMS


@pytest.fixture
def nfl_structure() -> dict[str, dict[str, list[str]]]:
    """Full NFL team structure: conference -> division -> teams."""
    return NFL_TEAMS


@pytest.fixture
def sample_completed_game() -> Game:
    """A sample completed game for testing."""
    return Game(
        game_id="401547417",
        week=1,
        date=date(2024, 9, 5),
        home_team="Chiefs",
        away_team="Ravens",
        status=GameStatus.COMPLETED,
        home_score=27,
        away_score=20,
        home_points=27,
        away_points=20,
        quarter=None,
        clock=None,
    )


@pytest.fixture
def sample_scheduled_game() -> Game:
    """A sample scheduled game for testing."""
    return Game(
        game_id="401547500",
        week=18,
        date=date(2025, 1, 5),
        home_team="Bills",
        away_team="Patriots",
        status=GameStatus.SCHEDULED,
        home_score=None,
        away_score=None,
        home_points=None,
        away_points=None,
        quarter=None,
        clock=None,
    )


@pytest.fixture
def sample_in_progress_game() -> Game:
    """A sample in-progress game for testing."""
    return Game(
        game_id="401547450",
        week=14,
        date=date(2024, 12, 8),
        home_team="Eagles",
        away_team="Cowboys",
        status=GameStatus.IN_PROGRESS,
        home_score=21,
        away_score=14,
        home_points=21,
        away_points=14,
        quarter=3,
        clock="5:32",
    )


@pytest.fixture
def sample_postponed_game() -> Game:
    """A sample postponed game for testing."""
    return Game(
        game_id="401547460",
        week=13,
        date=date(2024, 12, 1),
        home_team="Bills",
        away_team="49ers",
        status=GameStatus.POSTPONED,
        home_score=None,
        away_score=None,
        home_points=None,
        away_points=None,
        quarter=None,
        clock=None,
    )


@pytest.fixture
def sample_cancelled_game() -> Game:
    """A sample cancelled game for testing."""
    return Game(
        game_id="401547470",
        week=17,
        date=date(2024, 12, 29),
        home_team="Bengals",
        away_team="Steelers",
        status=GameStatus.CANCELLED,
        home_score=None,
        away_score=None,
        home_points=None,
        away_points=None,
        quarter=None,
        clock=None,
    )


@pytest.fixture
def sample_week_games() -> list[Game]:
    """A sample set of games for a single week (Week 1, 2024)."""
    return [
        Game(
            game_id="401547417",
            week=1,
            date=date(2024, 9, 5),
            home_team="Chiefs",
            away_team="Ravens",
            status=GameStatus.COMPLETED,
            home_score=27,
            away_score=20,
            home_points=27,
            away_points=20,
            quarter=None,
            clock=None,
        ),
        Game(
            game_id="401547418",
            week=1,
            date=date(2024, 9, 8),
            home_team="Eagles",
            away_team="Packers",
            status=GameStatus.COMPLETED,
            home_score=34,
            away_score=29,
            home_points=34,
            away_points=29,
            quarter=None,
            clock=None,
        ),
        Game(
            game_id="401547419",
            week=1,
            date=date(2024, 9, 8),
            home_team="Bills",
            away_team="Cardinals",
            status=GameStatus.COMPLETED,
            home_score=34,
            away_score=28,
            home_points=34,
            away_points=28,
            quarter=None,
            clock=None,
        ),
        Game(
            game_id="401547420",
            week=1,
            date=date(2024, 9, 8),
            home_team="Lions",
            away_team="Rams",
            status=GameStatus.COMPLETED,
            home_score=26,
            away_score=20,
            home_points=26,
            away_points=20,
            quarter=None,
            clock=None,
        ),
    ]


@pytest.fixture
def mixed_status_games() -> list[Game]:
    """Games with a mix of all statuses for testing filtering."""
    return [
        Game(
            game_id="g1",
            week=10,
            date=date(2024, 11, 10),
            home_team="Chiefs",
            away_team="Broncos",
            status=GameStatus.COMPLETED,
            home_score=24,
            away_score=17,
            home_points=24,
            away_points=17,
            quarter=None,
            clock=None,
        ),
        Game(
            game_id="g2",
            week=10,
            date=date(2024, 11, 10),
            home_team="Eagles",
            away_team="Cowboys",
            status=GameStatus.IN_PROGRESS,
            home_score=14,
            away_score=7,
            home_points=14,
            away_points=7,
            quarter=2,
            clock="8:45",
        ),
        Game(
            game_id="g3",
            week=11,
            date=date(2024, 11, 17),
            home_team="Bills",
            away_team="Jets",
            status=GameStatus.SCHEDULED,
            home_score=None,
            away_score=None,
            home_points=None,
            away_points=None,
            quarter=None,
            clock=None,
        ),
        Game(
            game_id="g4",
            week=10,
            date=date(2024, 11, 10),
            home_team="Ravens",
            away_team="Steelers",
            status=GameStatus.COMPLETED,
            home_score=30,
            away_score=23,
            home_points=30,
            away_points=23,
            quarter=None,
            clock=None,
        ),
        Game(
            game_id="g5",
            week=11,
            date=date(2024, 11, 17),
            home_team="Lions",
            away_team="Bears",
            status=GameStatus.POSTPONED,
            home_score=None,
            away_score=None,
            home_points=None,
            away_points=None,
            quarter=None,
            clock=None,
        ),
        Game(
            game_id="g6",
            week=12,
            date=date(2024, 11, 24),
            home_team="49ers",
            away_team="Seahawks",
            status=GameStatus.CANCELLED,
            home_score=None,
            away_score=None,
            home_points=None,
            away_points=None,
            quarter=None,
            clock=None,
        ),
    ]
