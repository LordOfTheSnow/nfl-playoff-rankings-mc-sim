"""The simulate job's serialized result carries the data-driven indicator."""

from __future__ import annotations

from datetime import date

import pytest

from src.data_client import Game, GameStatus
from src.server import _serialize_simulation_result
from src.simulator import SimulationConfig, Simulator


def _game(gid: str, week: int, home: str, away: str, completed: bool) -> Game:
    return Game(
        game_id=gid, week=week, date=date(2026, 9, 7), home_team=home, away_team=away,
        status=GameStatus.COMPLETED if completed else GameStatus.SCHEDULED,
        home_score=24 if completed else None, away_score=17 if completed else None,
        home_points=24 if completed else None, away_points=17 if completed else None,
    )


def test_serialized_result_has_data_driven_fields() -> None:
    games = [
        _game("g1", 1, "Bills", "Jets", True),
        _game("g2", 2, "Bills", "Dolphins", False),
    ]
    result = Simulator(SimulationConfig(iterations=1000, cutoff_week=1, num_workers=1)).run(games)
    # One completed game: Bills and Jets have n=1 (weight 1/9), the other 30 teams 0.
    expected_share = 2 * (1 / 9) / 32
    assert result.data_driven_share == pytest.approx(expected_share)

    data = _serialize_simulation_result(result, games=games)
    assert data["data_driven_pct"] == round(expected_share * 100, 1)
    assert data["data_confidence"] == "Very low"
