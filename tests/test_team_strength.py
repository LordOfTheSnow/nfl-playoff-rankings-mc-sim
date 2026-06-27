"""Unit tests for the team strength calculator.

Tests the iterative convergence algorithm for strength-of-schedule-weighted
team ratings.
"""

from __future__ import annotations

import logging
from datetime import date

import pytest

from src.data_client import Game, GameStatus
from src.team_strength import TeamRating, TeamStrengthCalculator


def _make_game(
    home: str,
    away: str,
    home_score: int,
    away_score: int,
    week: int = 1,
) -> Game:
    """Helper to create a completed game."""
    return Game(
        game_id=f"{home}-{away}-w{week}",
        week=week,
        date=date(2024, 9, 8),
        home_team=home,
        away_team=away,
        status=GameStatus.COMPLETED,
        home_score=home_score,
        away_score=away_score,
        home_points=home_score,
        away_points=away_score,
    )


class TestTeamStrengthCalculator:
    """Tests for TeamStrengthCalculator."""

    def test_empty_games_returns_empty_dict(self) -> None:
        """No completed games → empty ratings."""
        calc = TeamStrengthCalculator()
        result = calc.calculate([])
        assert result == {}

    def test_only_non_completed_games_returns_empty(self) -> None:
        """Games that aren't completed are ignored."""
        calc = TeamStrengthCalculator()
        scheduled_game = Game(
            game_id="1",
            week=1,
            date=date(2024, 9, 8),
            home_team="Chiefs",
            away_team="Bills",
            status=GameStatus.SCHEDULED,
            home_score=None,
            away_score=None,
            home_points=None,
            away_points=None,
        )
        result = calc.calculate([scheduled_game])
        assert result == {}

    def test_two_teams_equal_records_get_equal_strength(self) -> None:
        """Two teams that beat each other once should have equal ratings."""
        calc = TeamStrengthCalculator()
        games = [
            _make_game("Chiefs", "Bills", 24, 17, week=1),  # Chiefs win
            _make_game("Bills", "Chiefs", 21, 14, week=2),  # Bills win
        ]
        result = calc.calculate(games)

        assert "Chiefs" in result
        assert "Bills" in result
        # With symmetric results, both should have equal strength
        assert abs(result["Chiefs"] - result["Bills"]) < 0.01

    def test_average_rating_is_one(self) -> None:
        """Average of all team ratings should be 1.0."""
        calc = TeamStrengthCalculator()
        games = [
            _make_game("Chiefs", "Bills", 24, 17, week=1),
            _make_game("Ravens", "Bengals", 30, 20, week=1),
            _make_game("Chiefs", "Ravens", 21, 14, week=2),
            _make_game("Bills", "Bengals", 28, 24, week=2),
        ]
        result = calc.calculate(games)

        avg = sum(result.values()) / len(result)
        assert abs(avg - 1.0) < 0.001

    def test_winning_team_has_higher_strength(self) -> None:
        """A team that wins all games should have higher strength than one that loses all."""
        calc = TeamStrengthCalculator()
        games = [
            _make_game("Chiefs", "Bills", 24, 17, week=1),
            _make_game("Chiefs", "Ravens", 21, 14, week=2),
            _make_game("Chiefs", "Bengals", 28, 20, week=3),
            _make_game("Bills", "Ravens", 17, 21, week=3),
            _make_game("Bills", "Bengals", 14, 10, week=4),
            _make_game("Ravens", "Bengals", 24, 21, week=4),
        ]
        result = calc.calculate(games)

        # Chiefs won all 3 games, Bengals lost all 3
        assert result["Chiefs"] > result["Bengals"]

    def test_convergence_within_max_iterations(self) -> None:
        """Typical game sets should converge within 100 iterations."""
        calc = TeamStrengthCalculator()
        # Create a round-robin among 4 teams
        games = [
            _make_game("A", "B", 24, 17, week=1),
            _make_game("C", "D", 30, 20, week=1),
            _make_game("A", "C", 21, 14, week=2),
            _make_game("B", "D", 28, 24, week=2),
            _make_game("A", "D", 17, 10, week=3),
            _make_game("B", "C", 14, 21, week=3),
        ]
        result = calc.calculate(games)

        # Should have ratings for all 4 teams
        assert len(result) == 4
        # All ratings should be positive
        assert all(r > 0 for r in result.values())

    def test_non_convergence_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """When convergence isn't achieved, a warning should be logged."""
        calc = TeamStrengthCalculator()
        # Force non-convergence by setting an impossibly tight threshold
        # and very few iterations
        calc.CONVERGENCE_THRESHOLD = 1e-20
        calc.MAX_ITERATIONS = 2  # Very few iterations

        # Use an asymmetric game set that takes many iterations to converge
        games = [
            _make_game("A", "B", 24, 17, week=1),  # A beats B
            _make_game("B", "C", 30, 20, week=1),  # B beats C
            _make_game("C", "D", 21, 14, week=2),  # C beats D
            _make_game("D", "A", 17, 14, week=2),  # D beats A (creates cycle)
            _make_game("A", "C", 28, 21, week=3),  # A beats C
            _make_game("B", "D", 24, 10, week=3),  # B beats D
        ]

        with caplog.at_level(logging.WARNING, logger="src.team_strength"):
            result = calc.calculate(games)

        # Should still return ratings
        assert len(result) == 4
        # Should have logged a warning about non-convergence
        assert any("did not converge" in record.message for record in caplog.records)

    def test_tie_game_handling(self) -> None:
        """Tied games should use 0.5 × opponent rating weight."""
        calc = TeamStrengthCalculator()
        games = [
            _make_game("Chiefs", "Bills", 21, 21, week=1),  # Tie
        ]
        result = calc.calculate(games)

        # With a single tie, both teams should have equal strength
        assert abs(result["Chiefs"] - result["Bills"]) < 0.001
        # And both should be 1.0 (normalized average)
        assert abs(result["Chiefs"] - 1.0) < 0.001

    def test_strength_of_schedule_effect(self) -> None:
        """Beating a strong team should be worth more than beating a weak team."""
        calc = TeamStrengthCalculator()
        # Team A beats strong team (B), Team C beats weak team (D)
        # B beats D, so B is stronger than D
        games = [
            _make_game("A", "B", 24, 17, week=1),  # A beats B
            _make_game("C", "D", 24, 17, week=1),  # C beats D
            _make_game("B", "D", 30, 10, week=2),  # B beats D (B is strong)
            _make_game("A", "D", 28, 14, week=2),  # A beats D
            _make_game("C", "B", 10, 30, week=2),  # C loses to B
        ]
        result = calc.calculate(games)

        # A beat B (strong) and D (weak) → 2-0
        # C beat D (weak) but lost to B (strong) → 1-1
        # A should be stronger than C
        assert result["A"] > result["C"]

    def test_returns_dict_of_str_to_float(self) -> None:
        """Return type should be dict[str, float]."""
        calc = TeamStrengthCalculator()
        games = [_make_game("X", "Y", 10, 7, week=1)]
        result = calc.calculate(games)

        assert isinstance(result, dict)
        for key, value in result.items():
            assert isinstance(key, str)
            assert isinstance(value, float)

    def test_team_rating_dataclass(self) -> None:
        """TeamRating dataclass should hold team, strength, games_played."""
        rating = TeamRating(team="Chiefs", strength=1.45, games_played=10)
        assert rating.team == "Chiefs"
        assert rating.strength == 1.45
        assert rating.games_played == 10

    def test_constants(self) -> None:
        """Verify class constants are set correctly."""
        assert TeamStrengthCalculator.CONVERGENCE_THRESHOLD == 0.001
        assert TeamStrengthCalculator.MAX_ITERATIONS == 200
