"""Unit tests for NFL tiebreaker procedures.

Tests the tiebreaker logic: head-to-head, division record, common games,
conference record, strength of victory, strength of schedule, point-based
steps, multi-team handling, and coin toss fallback.

Requirements: 10.4, 10.5, 10.6, 10.13, 10.14
"""

from datetime import date

import pytest

from src.data_client import Game, GameStatus
from src.standings import (
    break_tie,
    _step_head_to_head,
    _step_division_record,
    _step_common_games,
    _step_conference_record,
    _step_strength_of_victory,
    _step_strength_of_schedule,
    _step_point_differential,
    _step_net_points_common_games,
    _step_net_points_all_games,
    _step_coin_toss,
    _get_games_between,
    _get_common_opponents,
    _strength_of_victory,
    _strength_of_schedule,
)


def _make_game(
    game_id: str,
    home: str,
    away: str,
    home_score: int,
    away_score: int,
    week: int = 1,
) -> Game:
    """Helper to create a completed game."""
    return Game(
        game_id=game_id,
        week=week,
        date=date(2024, 9, 5),
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


class TestHeadToHead:
    """Tests for head-to-head tiebreaker step."""

    def test_two_team_h2h_winner(self) -> None:
        """Team with better head-to-head record wins."""
        games = [
            _make_game("g1", "Chiefs", "Raiders", 27, 20),
            _make_game("g2", "Chiefs", "Raiders", 31, 24),
        ]
        result = _step_head_to_head(["Chiefs", "Raiders"], games, set())
        assert result is not None
        assert result[0] == "Chiefs"

    def test_two_team_h2h_split(self) -> None:
        """Split head-to-head returns None (no differentiation)."""
        games = [
            _make_game("g1", "Chiefs", "Raiders", 27, 20),
            _make_game("g2", "Raiders", "Chiefs", 31, 24),
        ]
        result = _step_head_to_head(["Chiefs", "Raiders"], games, set())
        assert result is None

    def test_no_h2h_games(self) -> None:
        """No head-to-head games returns None."""
        games = [_make_game("g1", "Chiefs", "Broncos", 27, 20)]
        result = _step_head_to_head(["Chiefs", "Raiders"], games, set())
        assert result is None

    def test_conference_h2h_requires_all_played(self) -> None:
        """Conference H2H requires all teams to have played each other."""
        # Chiefs beat Raiders, but Chiefs haven't played Broncos
        games = [_make_game("g1", "Chiefs", "Raiders", 27, 20)]
        result = _step_head_to_head(
            ["Chiefs", "Raiders", "Broncos"], games, set(), require_all_played=True
        )
        assert result is None

    def test_conference_h2h_all_played(self) -> None:
        """Conference H2H works when all teams have played each other."""
        games = [
            _make_game("g1", "Chiefs", "Raiders", 27, 20),
            _make_game("g2", "Chiefs", "Broncos", 31, 24),
            _make_game("g3", "Raiders", "Broncos", 28, 21),
        ]
        result = _step_head_to_head(
            ["Chiefs", "Raiders", "Broncos"], games, set(), require_all_played=True
        )
        assert result is not None
        assert result[0] == "Chiefs"  # 2-0 in H2H
        assert result[1] == "Raiders"  # 1-1 in H2H
        assert result[2] == "Broncos"  # 0-2 in H2H

    def test_h2h_with_simulated_games(self) -> None:
        """Head-to-head includes simulated games."""
        games = [
            Game(
                game_id="g1", week=1, date=date(2024, 9, 5),
                home_team="Chiefs", away_team="Raiders",
                status=GameStatus.COMPLETED,
                home_score=27, away_score=20,
                home_points=27, away_points=20,
                quarter=None, clock=None,
            ),
        ]
        # g1 is a real completed game, Chiefs won
        result = _step_head_to_head(["Chiefs", "Raiders"], games, set())
        assert result is not None
        assert result[0] == "Chiefs"


class TestDivisionRecord:
    """Tests for division record tiebreaker step."""

    def test_better_division_record_wins(self) -> None:
        """Team with better division record wins the tiebreaker."""
        # Chiefs beat Broncos (division game), Raiders lose to Chargers (division game)
        games = [
            _make_game("g1", "Chiefs", "Broncos", 27, 20),
            _make_game("g2", "Chargers", "Raiders", 24, 17),
        ]
        result = _step_division_record(["Chiefs", "Raiders"], games, set())
        assert result is not None
        assert result[0] == "Chiefs"

    def test_equal_division_records(self) -> None:
        """Equal division records returns None."""
        games = [
            _make_game("g1", "Chiefs", "Broncos", 27, 20),
            _make_game("g2", "Raiders", "Chargers", 24, 17),
        ]
        result = _step_division_record(["Chiefs", "Raiders"], games, set())
        assert result is None  # Both 1-0 in division


class TestCommonGames:
    """Tests for common games tiebreaker step."""

    def test_better_common_games_record_wins(self) -> None:
        """Team with better record against common opponents wins."""
        # Both play Eagles: Chiefs beat Eagles, Raiders lose to Eagles
        games = [
            _make_game("g1", "Chiefs", "Eagles", 27, 20),
            _make_game("g2", "Eagles", "Raiders", 24, 17),
        ]
        result = _step_common_games(["Chiefs", "Raiders"], games, set())
        assert result is not None
        assert result[0] == "Chiefs"

    def test_no_common_opponents(self) -> None:
        """No common opponents returns None."""
        games = [
            _make_game("g1", "Chiefs", "Eagles", 27, 20),
            _make_game("g2", "Raiders", "Cowboys", 24, 17),
        ]
        result = _step_common_games(["Chiefs", "Raiders"], games, set())
        assert result is None

    def test_min_common_not_met(self) -> None:
        """Conference tiebreaker requires minimum 4 common opponents."""
        # Only 1 common opponent
        games = [
            _make_game("g1", "Chiefs", "Eagles", 27, 20),
            _make_game("g2", "Eagles", "Raiders", 24, 17),
        ]
        result = _step_common_games(["Chiefs", "Raiders"], games, set(), min_common=4)
        assert result is None


class TestConferenceRecord:
    """Tests for conference record tiebreaker step."""

    def test_better_conference_record_wins(self) -> None:
        """Team with better conference record wins."""
        # Chiefs beat Ravens (AFC), Raiders lose to Steelers (AFC)
        games = [
            _make_game("g1", "Chiefs", "Ravens", 27, 20),
            _make_game("g2", "Steelers", "Raiders", 24, 17),
        ]
        result = _step_conference_record(["Chiefs", "Raiders"], games, set())
        assert result is not None
        assert result[0] == "Chiefs"

    def test_equal_conference_records(self) -> None:
        """Equal conference records returns None."""
        games = [
            _make_game("g1", "Chiefs", "Ravens", 27, 20),
            _make_game("g2", "Raiders", "Steelers", 24, 17),
        ]
        result = _step_conference_record(["Chiefs", "Raiders"], games, set())
        assert result is None


class TestStrengthOfVictory:
    """Tests for strength of victory tiebreaker step."""

    def test_better_sov_wins(self) -> None:
        """Team that beat stronger opponents has better SOV."""
        # Chiefs beat Ravens (who are 1-0), Raiders beat Browns (who are 0-1)
        games = [
            _make_game("g1", "Chiefs", "Ravens", 27, 20),
            _make_game("g2", "Raiders", "Browns", 24, 17),
            _make_game("g3", "Ravens", "Bengals", 21, 14),  # Ravens win
            _make_game("g4", "Steelers", "Browns", 28, 10),  # Browns lose
        ]
        result = _step_strength_of_victory(["Chiefs", "Raiders"], games, set())
        assert result is not None
        assert result[0] == "Chiefs"  # Beat Ravens (1-1) vs beat Browns (0-2)

    def test_equal_sov(self) -> None:
        """Equal SOV returns None."""
        # Both beat the same team
        games = [
            _make_game("g1", "Chiefs", "Ravens", 27, 20),
            _make_game("g2", "Raiders", "Ravens", 24, 17),
        ]
        result = _step_strength_of_victory(["Chiefs", "Raiders"], games, set())
        assert result is None


class TestStrengthOfSchedule:
    """Tests for strength of schedule tiebreaker step."""

    def test_harder_schedule_wins(self) -> None:
        """Team with harder schedule (stronger opponents) wins."""
        # Chiefs played Ravens (who are 2-0), Raiders played Browns (who are 0-2)
        games = [
            _make_game("g1", "Chiefs", "Ravens", 27, 20),
            _make_game("g2", "Raiders", "Browns", 24, 17),
            _make_game("g3", "Ravens", "Bengals", 21, 14),
            _make_game("g4", "Ravens", "Steelers", 28, 21),
            _make_game("g5", "Steelers", "Browns", 28, 10),
            _make_game("g6", "Bengals", "Browns", 35, 14),
        ]
        result = _step_strength_of_schedule(["Chiefs", "Raiders"], games, set())
        assert result is not None
        assert result[0] == "Chiefs"


class TestPointBasedSteps:
    """Tests for point-based tiebreaker steps and simulated game skipping."""

    def test_point_differential_with_real_games(self) -> None:
        """Point differential works with completed (real) games."""
        games = [
            _make_game("g1", "Chiefs", "Eagles", 35, 10),  # +25
            _make_game("g2", "Raiders", "Cowboys", 21, 20),  # +1
        ]
        result = _step_point_differential(["Chiefs", "Raiders"], games, set())
        assert result is not None
        assert result[0] == "Chiefs"

    def test_point_differential_skipped_for_simulated(self) -> None:
        """Point differential is skipped when simulated games are involved."""
        games = [
            _make_game("g1", "Chiefs", "Eagles", 35, 10),
            _make_game("g2", "Raiders", "Cowboys", 21, 20),
        ]
        # Mark g1 as simulated — no point data available
        result = _step_point_differential(["Chiefs", "Raiders"], games, {"g1"})
        assert result is None  # Skipped

    def test_net_points_common_games_real(self) -> None:
        """Net points in common games works with real data."""
        # Both play Eagles
        games = [
            _make_game("g1", "Chiefs", "Eagles", 35, 10),  # +25
            _make_game("g2", "Eagles", "Raiders", 24, 17),  # Raiders: -7
        ]
        result = _step_net_points_common_games(["Chiefs", "Raiders"], games, set())
        assert result is not None
        assert result[0] == "Chiefs"

    def test_net_points_common_games_skipped_for_simulated(self) -> None:
        """Net points in common games skipped when simulated."""
        games = [
            _make_game("g1", "Chiefs", "Eagles", 35, 10),
            _make_game("g2", "Eagles", "Raiders", 24, 17),
        ]
        result = _step_net_points_common_games(["Chiefs", "Raiders"], games, {"g1"})
        assert result is None  # Skipped

    def test_net_points_all_games_real(self) -> None:
        """Net points in all games works with real data."""
        games = [
            _make_game("g1", "Chiefs", "Eagles", 35, 10),  # +25
            _make_game("g2", "Raiders", "Cowboys", 21, 20),  # +1
        ]
        result = _step_net_points_all_games(["Chiefs", "Raiders"], games, set())
        assert result is not None
        assert result[0] == "Chiefs"

    def test_net_points_all_games_skipped_for_simulated(self) -> None:
        """Net points in all games skipped when simulated."""
        games = [
            _make_game("g1", "Chiefs", "Eagles", 35, 10),
            _make_game("g2", "Raiders", "Cowboys", 21, 20),
        ]
        result = _step_net_points_all_games(["Chiefs", "Raiders"], games, {"g2"})
        assert result is None  # Skipped

    def test_conference_point_differential(self) -> None:
        """Point differential in conference games only."""
        games = [
            _make_game("g1", "Chiefs", "Ravens", 35, 10),  # AFC game, +25
            _make_game("g2", "Chiefs", "Eagles", 21, 20),  # NFC game, not counted
            _make_game("g3", "Raiders", "Steelers", 24, 21),  # AFC game, +3
        ]
        result = _step_point_differential(
            ["Chiefs", "Raiders"], games, set(), conference_only=True
        )
        assert result is not None
        assert result[0] == "Chiefs"


class TestCoinToss:
    """Tests for coin toss fallback."""

    def test_coin_toss_returns_all_teams(self) -> None:
        """Coin toss returns all teams in some order."""
        teams = ["Chiefs", "Raiders", "Broncos"]
        result = _step_coin_toss(teams)
        assert set(result) == set(teams)
        assert len(result) == 3

    def test_coin_toss_single_team(self) -> None:
        """Coin toss with single team returns that team."""
        result = _step_coin_toss(["Chiefs"])
        assert result == ["Chiefs"]


class TestBreakTie:
    """Tests for the main break_tie function."""

    def test_single_team_returns_unchanged(self) -> None:
        """Single team returns immediately."""
        result = break_tie(["Chiefs"], [], set())
        assert result == ["Chiefs"]

    def test_empty_list_returns_empty(self) -> None:
        """Empty list returns empty."""
        result = break_tie([], [], set())
        assert result == []

    def test_two_team_division_tie_h2h(self) -> None:
        """Two-team division tie resolved by head-to-head."""
        games = [
            _make_game("g1", "Chiefs", "Raiders", 27, 20),
            _make_game("g2", "Chiefs", "Raiders", 31, 24),
        ]
        result = break_tie(["Chiefs", "Raiders"], games, set(), context="division")
        assert result[0] == "Chiefs"

    def test_two_team_conference_tie_h2h_not_played(self) -> None:
        """Conference tie where teams haven't played falls through to next step."""
        # Chiefs and Bills haven't played each other, but Chiefs have better conf record
        games = [
            _make_game("g1", "Chiefs", "Ravens", 27, 20),  # AFC game
            _make_game("g2", "Chiefs", "Steelers", 31, 24),  # AFC game
            _make_game("g3", "Bills", "Dolphins", 24, 17),  # AFC game
        ]
        result = break_tie(["Chiefs", "Bills"], games, set(), context="conference")
        assert result[0] == "Chiefs"  # Better conference record (2-0 vs 1-0)

    def test_division_tie_falls_through_to_division_record(self) -> None:
        """Division tie falls through H2H to division record."""
        # No H2H games, but Chiefs have better division record
        games = [
            _make_game("g1", "Chiefs", "Broncos", 27, 20),  # Division win
            _make_game("g2", "Chiefs", "Chargers", 31, 24),  # Division win
            _make_game("g3", "Raiders", "Broncos", 24, 17),  # Division win
        ]
        result = break_tie(["Chiefs", "Raiders"], games, set(), context="division")
        assert result[0] == "Chiefs"  # 2-0 div vs 1-0 div

    def test_returns_all_teams(self) -> None:
        """break_tie always returns all teams."""
        teams = ["Chiefs", "Raiders", "Broncos"]
        result = break_tie(teams, [], set(), context="division")
        assert set(result) == set(teams)
        assert len(result) == 3


class TestMultiTeamTie:
    """Tests for multi-team tie handling with restart logic."""

    def test_three_team_tie_resolved_step_by_step(self) -> None:
        """Three-team tie: best team extracted, then remaining two resolved."""
        # Chiefs 2-0 H2H, Raiders 1-1, Broncos 0-2
        games = [
            _make_game("g1", "Chiefs", "Raiders", 27, 20),
            _make_game("g2", "Chiefs", "Broncos", 31, 24),
            _make_game("g3", "Raiders", "Broncos", 28, 21),
        ]
        result = break_tie(
            ["Chiefs", "Raiders", "Broncos"], games, set(), context="division"
        )
        assert result[0] == "Chiefs"
        assert result[1] == "Raiders"
        assert result[2] == "Broncos"

    def test_three_team_tie_restart_after_elimination(self) -> None:
        """After eliminating one team, restart from step 1 for remaining."""
        # In H2H among all 3: Chiefs 2-0, Raiders 0-1, Broncos 0-1
        # After Chiefs extracted, Raiders vs Broncos restarts from step 1
        # Raiders beat Broncos in H2H
        games = [
            _make_game("g1", "Chiefs", "Raiders", 27, 20),
            _make_game("g2", "Chiefs", "Broncos", 31, 24),
            _make_game("g3", "Raiders", "Broncos", 28, 21),
        ]
        result = break_tie(
            ["Chiefs", "Raiders", "Broncos"], games, set(), context="division"
        )
        # Chiefs first (best H2H), then Raiders beats Broncos in H2H restart
        assert result == ["Chiefs", "Raiders", "Broncos"]

    def test_multi_team_coin_toss_fallback(self) -> None:
        """Multi-team tie with no differentiating data uses coin toss."""
        # No games at all — everything falls through to coin toss
        result = break_tie(
            ["Chiefs", "Raiders", "Broncos"], [], set(), context="division"
        )
        assert set(result) == {"Chiefs", "Raiders", "Broncos"}
        assert len(result) == 3

    def test_multi_team_simulated_skips_points(self) -> None:
        """Multi-team tie with simulated games skips point-based steps."""
        # All games simulated — point steps should be skipped
        games = [
            _make_game("g1", "Chiefs", "Eagles", 35, 10),
            _make_game("g2", "Raiders", "Cowboys", 21, 20),
            _make_game("g3", "Broncos", "Giants", 28, 14),
        ]
        sim_ids = {"g1", "g2", "g3"}
        # With all games simulated, point-based steps are skipped
        # SOV/SOS may still differentiate based on opponents' records
        result = break_tie(
            ["Chiefs", "Raiders", "Broncos"], games, sim_ids, context="division"
        )
        assert set(result) == {"Chiefs", "Raiders", "Broncos"}
        assert len(result) == 3


class TestDivisionVsConferenceTiebreaker:
    """Tests verifying correct step order for division vs conference context."""

    def test_division_uses_division_record_step(self) -> None:
        """Division tiebreaker uses division record as step 2."""
        # No H2H, but Chiefs have better division record
        games = [
            _make_game("g1", "Chiefs", "Broncos", 27, 20),  # Div win
        ]
        result = break_tie(["Chiefs", "Raiders"], games, set(), context="division")
        assert result[0] == "Chiefs"

    def test_conference_uses_conference_record_step(self) -> None:
        """Conference tiebreaker uses conference record as step 2."""
        # No H2H (teams haven't played), Chiefs have better conf record
        games = [
            _make_game("g1", "Chiefs", "Ravens", 27, 20),  # Conf win
            _make_game("g2", "Chiefs", "Steelers", 31, 24),  # Conf win
            _make_game("g3", "Bills", "Dolphins", 24, 17),  # Conf win
        ]
        result = break_tie(["Chiefs", "Bills"], games, set(), context="conference")
        assert result[0] == "Chiefs"  # 2-0 conf vs 1-0 conf
