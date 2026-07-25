"""Tests for clinching solver tiebreaker accuracy.

Verifies that the two-pass clinching solver produces correct results when
a team's playoff path depends on NFL tiebreaker resolution (H2H, division
record, conference record, SoV, SoS).

These tests use real 2024 season data to validate against known outcomes.
Requires cached 2024 game data (run POST /api/fetch-data with season=2024).
"""

import pytest

from src.cache import Cache
from src.clinching import compute_clinching_scenarios


@pytest.fixture(scope="module")
def games_2024():
    """Load cached 2024 season games. Skip if not available."""
    cache = Cache()
    games = cache.get_games(2024)
    if not games:
        pytest.skip("No cached 2024 game data available")
    return games


@pytest.fixture(scope="class")
def falcons_result(games_2024):
    """Run clinching solver for Falcons once, share across all tests in class."""
    return compute_clinching_scenarios(
        "Falcons", games_2024, 17,
        num_workers=1,
        playoff_probability=22.6,
        enumeration_threshold=9,
    )


@pytest.fixture(scope="class")
def buccaneers_result(games_2024):
    """Run clinching solver for Buccaneers once, share across all tests in class."""
    return compute_clinching_scenarios(
        "Buccaneers", games_2024, 17,
        num_workers=1,
        playoff_probability=77.3,
        enumeration_threshold=9,
    )


class TestFalconsTiebreakerPath:
    """Falcons 2024 week 17: MC sim shows ~22% but fast path reports no path.

    The Falcons can make the playoffs only by winning tiebreakers against
    the Buccaneers. The fast path (win% + alphabetical) misses this because
    it doesn't resolve head-to-head or division record tiebreakers.
    """

    def test_falcons_win_has_path(self, falcons_result):
        """Falcons finishing 1-0 should have a path to playoffs."""
        rg_win = next(
            (rg for rg in falcons_result.record_groups if rg.wins == 1 and rg.losses == 0 and rg.ties == 0),
            None,
        )
        assert rg_win is not None
        assert rg_win.no_path is False
        # Should have at least one scenario with conditions
        real_scenarios = [s for s in rg_win.scenarios if s.num_conditions > 0]
        assert len(real_scenarios) >= 1

    def test_falcons_win_needs_saints_to_beat_bucs(self, falcons_result):
        """Falcons' clinching condition requires Saints to beat Buccaneers."""
        rg_win = next(
            (rg for rg in falcons_result.record_groups if rg.wins == 1 and rg.losses == 0 and rg.ties == 0),
            None,
        )
        real_scenarios = [s for s in rg_win.scenarios if s.num_conditions > 0]
        # The simplest scenario should be: Saints beat Buccaneers
        simplest = min(real_scenarios, key=lambda s: s.num_conditions)
        assert simplest.num_conditions == 1
        cond = simplest.conditions[0]
        assert cond.home_team == "Buccaneers"
        assert cond.away_team == "Saints"
        assert cond.required_winner == "Saints"

    def test_falcons_loss_or_tie_no_path(self, falcons_result):
        """Falcons finishing 0-1 or 0-0-1 should have no path."""
        for rg in falcons_result.record_groups:
            if rg.wins == 0:
                assert rg.no_path is True, f"Expected no_path for {rg.wins}-{rg.losses}-{rg.ties}"


class TestBuccaneersFalseClinch:
    """Buccaneers 2024 week 17: fast path falsely reports 'clinches regardless'.

    The fast path (alphabetical tiebreaker) places Buccaneers ahead of
    Falcons in ties, but with real tiebreakers the Falcons can overtake
    them if both win. The Bucs only truly clinch if they win or tie.
    """

    def test_bucs_win_clinches(self, buccaneers_result):
        """Buccaneers finishing 1-0 should clinch regardless."""
        rg_win = next(
            (rg for rg in buccaneers_result.record_groups if rg.wins == 1 and rg.losses == 0 and rg.ties == 0),
            None,
        )
        assert rg_win is not None
        assert rg_win.no_path is False
        # Should be a 0-condition scenario (clinches regardless)
        assert len(rg_win.scenarios) == 1
        assert rg_win.scenarios[0].num_conditions == 0

    def test_bucs_tie_clinches(self, buccaneers_result):
        """Buccaneers finishing 0-0-1 should clinch regardless."""
        rg_tie = next(
            (rg for rg in buccaneers_result.record_groups if rg.wins == 0 and rg.losses == 0 and rg.ties == 1),
            None,
        )
        assert rg_tie is not None
        assert rg_tie.no_path is False
        assert len(rg_tie.scenarios) == 1
        assert rg_tie.scenarios[0].num_conditions == 0

    def test_bucs_loss_does_not_clinch(self, buccaneers_result):
        """Buccaneers finishing 0-1 should NOT clinch regardless."""
        rg_loss = next(
            (rg for rg in buccaneers_result.record_groups if rg.wins == 0 and rg.losses == 1 and rg.ties == 0),
            None,
        )
        assert rg_loss is not None
        assert rg_loss.no_path is False
        # Should have conditional scenarios (not a blanket clinch)
        real_scenarios = [s for s in rg_loss.scenarios if s.num_conditions > 0]
        assert len(real_scenarios) >= 1

    def test_bucs_loss_needs_falcons_to_lose(self, buccaneers_result):
        """Buccaneers losing need Panthers to beat Falcons."""
        rg_loss = next(
            (rg for rg in buccaneers_result.record_groups if rg.wins == 0 and rg.losses == 1 and rg.ties == 0),
            None,
        )
        real_scenarios = [s for s in rg_loss.scenarios if s.num_conditions > 0]
        simplest = min(real_scenarios, key=lambda s: s.num_conditions)
        assert simplest.num_conditions == 1
        cond = simplest.conditions[0]
        assert cond.home_team == "Falcons"
        assert cond.away_team == "Panthers"
        assert cond.required_winner == "Panthers"
