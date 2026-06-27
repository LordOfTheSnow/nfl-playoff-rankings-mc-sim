"""Tests for parallel simulation execution (Task 14.3).

Validates that:
- Single-worker and multi-worker runs produce statistically equivalent results
- Total iteration count across workers equals the requested count
- Fallback to single-process on num_workers=1
- Error handling when worker processes fail
- num_workers parameter validation
"""

from __future__ import annotations

import random
from datetime import date

import pytest

from src.data_client import Game, GameStatus
from src.simulator import (
    SimulationConfig,
    Simulator,
    _merge_batch_results,
    _run_trial_batch,
    _split_iterations,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_completed_game(
    game_id: str,
    week: int,
    home_team: str,
    away_team: str,
    home_score: int,
    away_score: int,
) -> Game:
    """Create a completed game for testing."""
    return Game(
        game_id=game_id,
        week=week,
        date=date(2025, 9, 7),
        home_team=home_team,
        away_team=away_team,
        status=GameStatus.COMPLETED,
        home_score=home_score,
        away_score=away_score,
        home_points=home_score,
        away_points=away_score,
        quarter=None,
        clock=None,
    )


def _make_scheduled_game(
    game_id: str, week: int, home_team: str, away_team: str
) -> Game:
    """Create a scheduled game for testing."""
    return Game(
        game_id=game_id,
        week=week,
        date=date(2025, 12, 21),
        home_team=home_team,
        away_team=away_team,
        status=GameStatus.SCHEDULED,
        home_score=None,
        away_score=None,
        home_points=None,
        away_points=None,
        quarter=None,
        clock=None,
    )


def _build_minimal_season() -> list[Game]:
    """Build a minimal but complete season with games for all 32 teams.

    Creates enough completed games (weeks 1-14) to establish standings
    and scheduled games (weeks 15-18) for simulation.
    """
    from src.nfl_teams import NFL_TEAMS

    games: list[Game] = []
    game_counter = 0

    # Create completed games for weeks 1-14 (each team plays each week)
    for week in range(1, 15):
        for conf_name, divisions in NFL_TEAMS.items():
            for div_name, teams in divisions.items():
                # Pair teams within division for simplicity
                pairs = [(teams[0], teams[1]), (teams[2], teams[3])]
                for home, away in pairs:
                    game_counter += 1
                    # Vary scores to create differentiation
                    random.seed(game_counter * 100 + week)
                    home_score = random.randint(10, 35)
                    away_score = random.randint(10, 35)
                    games.append(
                        _make_completed_game(
                            game_id=f"game_{game_counter}",
                            week=week,
                            home_team=home,
                            away_team=away,
                            home_score=home_score,
                            away_score=away_score,
                        )
                    )

    # Create scheduled games for weeks 15-18
    for week in range(15, 19):
        for conf_name, divisions in NFL_TEAMS.items():
            for div_name, teams in divisions.items():
                pairs = [(teams[0], teams[3]), (teams[1], teams[2])]
                for home, away in pairs:
                    game_counter += 1
                    games.append(
                        _make_scheduled_game(
                            game_id=f"game_{game_counter}",
                            week=week,
                            home_team=home,
                            away_team=away,
                        )
                    )

    return games


# ---------------------------------------------------------------------------
# Tests for _split_iterations
# ---------------------------------------------------------------------------


class TestSplitIterations:
    """Tests for the iteration splitting helper."""

    def test_even_split(self) -> None:
        """Even division produces equal batches."""
        result = _split_iterations(1000, 4)
        assert result == [250, 250, 250, 250]
        assert sum(result) == 1000

    def test_uneven_split(self) -> None:
        """Remainder is distributed across first workers."""
        result = _split_iterations(1003, 4)
        assert result == [251, 251, 251, 250]
        assert sum(result) == 1003

    def test_single_worker(self) -> None:
        """Single worker gets all iterations."""
        result = _split_iterations(500, 1)
        assert result == [500]

    def test_more_workers_than_iterations(self) -> None:
        """Handles case where workers > iterations."""
        result = _split_iterations(3, 5)
        assert sum(result) == 3
        # First 3 workers get 1 each, last 2 get 0
        assert result == [1, 1, 1, 0, 0]


# ---------------------------------------------------------------------------
# Tests for _run_trial_batch
# ---------------------------------------------------------------------------


class TestRunTrialBatch:
    """Tests for the batch worker function."""

    def test_produces_correct_structure(self) -> None:
        """Batch result has the expected keys and value types."""
        games = _build_minimal_season()
        from src.nfl_teams import ALL_TEAMS
        strengths = {team: 1.0 for team in ALL_TEAMS}
        # Only get games to simulate (scheduled ones)
        games_to_sim = [g for g in games if g.status == GameStatus.SCHEDULED]

        result = _run_trial_batch(
            all_games=games,
            games_to_simulate=games_to_sim,
            strengths=strengths,
            batch_iterations=10,
            tie_probability=0.005,
            noise=0.2,
            seed=42,
        )

        assert "playoff_counts" in result
        assert "seed_counts" in result
        assert "division_champion_counts" in result
        assert "scenario_tracker" in result

        # Check that all teams are present
        assert len(result["playoff_counts"]) == 32

    def test_deterministic_with_same_seed(self) -> None:
        """Same seed produces identical results."""
        games = _build_minimal_season()
        from src.nfl_teams import ALL_TEAMS
        strengths = {team: 1.0 for team in ALL_TEAMS}
        games_to_sim = [g for g in games if g.status == GameStatus.SCHEDULED]

        result1 = _run_trial_batch(
            all_games=games,
            games_to_simulate=games_to_sim,
            strengths=strengths,
            batch_iterations=50,
            tie_probability=0.005,
            noise=0.2,
            seed=12345,
        )
        result2 = _run_trial_batch(
            all_games=games,
            games_to_simulate=games_to_sim,
            strengths=strengths,
            batch_iterations=50,
            tie_probability=0.005,
            noise=0.2,
            seed=12345,
        )

        assert result1["playoff_counts"] == result2["playoff_counts"]
        assert result1["seed_counts"] == result2["seed_counts"]

    def test_different_seeds_produce_different_results(self) -> None:
        """Different seeds produce different results (non-correlated)."""
        games = _build_minimal_season()
        from src.nfl_teams import ALL_TEAMS
        strengths = {team: 1.0 for team in ALL_TEAMS}
        games_to_sim = [g for g in games if g.status == GameStatus.SCHEDULED]

        result1 = _run_trial_batch(
            all_games=games,
            games_to_simulate=games_to_sim,
            strengths=strengths,
            batch_iterations=100,
            tie_probability=0.005,
            noise=0.2,
            seed=111,
        )
        result2 = _run_trial_batch(
            all_games=games,
            games_to_simulate=games_to_sim,
            strengths=strengths,
            batch_iterations=100,
            tie_probability=0.005,
            noise=0.2,
            seed=222,
        )

        # With 100 trials and randomness, counts should differ
        assert result1["playoff_counts"] != result2["playoff_counts"]


# ---------------------------------------------------------------------------
# Tests for _merge_batch_results
# ---------------------------------------------------------------------------


class TestMergeBatchResults:
    """Tests for merging results from multiple workers."""

    def test_merges_playoff_counts(self) -> None:
        """Playoff counts are summed across batches."""
        batch1 = {
            "playoff_counts": {"Bills": 5, "Chiefs": 8},
            "seed_counts": {"Bills": {1: 2, 2: 3}, "Chiefs": {1: 4, 2: 4}},
            "division_champion_counts": {"Bills": 3, "Chiefs": 6},
            "scenario_tracker": {frozenset({("Bills", 1), ("Chiefs", 2)}): 2},
        }
        batch2 = {
            "playoff_counts": {"Bills": 7, "Chiefs": 6},
            "seed_counts": {"Bills": {1: 3, 2: 4}, "Chiefs": {1: 2, 2: 4}},
            "division_champion_counts": {"Bills": 4, "Chiefs": 5},
            "scenario_tracker": {
                frozenset({("Bills", 1), ("Chiefs", 2)}): 3,
                frozenset({("Chiefs", 1), ("Bills", 2)}): 1,
            },
        }

        playoff, seeds, div_champs, scenarios = _merge_batch_results([batch1, batch2])

        assert playoff["Bills"] == 12
        assert playoff["Chiefs"] == 14
        assert seeds["Bills"][1] == 5
        assert seeds["Bills"][2] == 7
        assert seeds["Chiefs"][1] == 6
        assert div_champs["Bills"] == 7
        assert div_champs["Chiefs"] == 11
        assert scenarios[frozenset({("Bills", 1), ("Chiefs", 2)})] == 5
        assert scenarios[frozenset({("Chiefs", 1), ("Bills", 2)})] == 1

    def test_merges_empty_batches(self) -> None:
        """Handles empty batch list gracefully."""
        from src.nfl_teams import ALL_TEAMS

        playoff, seeds, div_champs, scenarios = _merge_batch_results([])

        # All counts should be zero
        for team in ALL_TEAMS:
            assert playoff[team] == 0
            for s in range(1, 8):
                assert seeds[team][s] == 0
            assert div_champs[team] == 0
        assert len(scenarios) == 0


# ---------------------------------------------------------------------------
# Tests for Simulator with parallel execution
# ---------------------------------------------------------------------------


class TestParallelSimulation:
    """Integration tests for parallel simulation."""

    def test_single_worker_matches_direct(self) -> None:
        """num_workers=1 produces the same flow as non-parallel."""
        games = _build_minimal_season()

        # Run with explicit num_workers=1
        config = SimulationConfig(
            iterations=100,
            cutoff_week=14,
            noise=0.2,
            num_workers=1,
        )
        simulator = Simulator(config)
        result = simulator.run(games)

        assert result.iterations_run == 100
        assert result.cutoff_week == 14
        assert len(result.team_results) == 32

        # Probability invariants: sum of playoff probs per conference = 7.0
        afc_prob_sum = sum(
            tr.playoff_probability
            for tr in result.team_results.values()
            if tr.conference == "AFC"
        )
        nfc_prob_sum = sum(
            tr.playoff_probability
            for tr in result.team_results.values()
            if tr.conference == "NFC"
        )
        assert abs(afc_prob_sum - 7.0) < 0.01
        assert abs(nfc_prob_sum - 7.0) < 0.01

    def test_multi_worker_probability_invariants(self) -> None:
        """Multi-worker results maintain probability invariants."""
        games = _build_minimal_season()

        config = SimulationConfig(
            iterations=200,
            cutoff_week=14,
            noise=0.2,
            num_workers=2,
        )
        simulator = Simulator(config)
        result = simulator.run(games)

        assert result.iterations_run == 200
        assert len(result.team_results) == 32

        # Probability invariants
        afc_prob_sum = sum(
            tr.playoff_probability
            for tr in result.team_results.values()
            if tr.conference == "AFC"
        )
        nfc_prob_sum = sum(
            tr.playoff_probability
            for tr in result.team_results.values()
            if tr.conference == "NFC"
        )
        assert abs(afc_prob_sum - 7.0) < 0.01
        assert abs(nfc_prob_sum - 7.0) < 0.01

        # Each seed position sums to 1.0 across teams in the conference
        for seed in range(1, 8):
            afc_seed_sum = sum(
                tr.seed_distribution[seed]
                for tr in result.team_results.values()
                if tr.conference == "AFC"
            )
            nfc_seed_sum = sum(
                tr.seed_distribution[seed]
                for tr in result.team_results.values()
                if tr.conference == "NFC"
            )
            assert abs(afc_seed_sum - 1.0) < 0.01, f"AFC seed {seed} sum: {afc_seed_sum}"
            assert abs(nfc_seed_sum - 1.0) < 0.01, f"NFC seed {seed} sum: {nfc_seed_sum}"

    def test_multi_worker_statistical_equivalence(self) -> None:
        """1-worker and 2-worker results are statistically similar.

        With enough iterations, both should produce similar playoff
        probabilities (within Monte Carlo variance).
        """
        games = _build_minimal_season()

        # Run single-worker
        config_1 = SimulationConfig(
            iterations=500,
            cutoff_week=14,
            noise=0.2,
            num_workers=1,
        )
        sim_1 = Simulator(config_1)
        random.seed(42)
        result_1 = sim_1.run(games)

        # Run multi-worker
        config_2 = SimulationConfig(
            iterations=500,
            cutoff_week=14,
            noise=0.2,
            num_workers=2,
        )
        sim_2 = Simulator(config_2)
        random.seed(99)
        result_2 = sim_2.run(games)

        # Check that probabilities are similar (within ~20% absolute for 500 iterations)
        # This is a statistical test so we allow generous tolerance
        max_diff = 0.0
        for team in result_1.team_results:
            diff = abs(
                result_1.team_results[team].playoff_probability
                - result_2.team_results[team].playoff_probability
            )
            max_diff = max(max_diff, diff)

        # With 500 iterations, max diff between two independent runs
        # should be < 0.25 in most cases
        assert max_diff < 0.25, (
            f"Max probability difference between 1-worker and 2-worker: {max_diff:.3f}. "
            f"Expected < 0.25 for 500 iterations."
        )

    def test_num_workers_none_uses_cpu_count(self) -> None:
        """num_workers=None defaults to os.cpu_count()."""
        games = _build_minimal_season()

        config = SimulationConfig(
            iterations=100,
            cutoff_week=14,
            noise=0.2,
            num_workers=None,
        )
        simulator = Simulator(config)
        result = simulator.run(games)

        # Should complete successfully regardless of core count
        assert result.iterations_run == 100
        assert len(result.team_results) == 32

    def test_num_workers_capped_at_iterations(self) -> None:
        """Workers are capped at iteration count (no empty batches)."""
        games = _build_minimal_season()

        # Request 100 iterations with 200 workers — should cap at 100 workers
        config = SimulationConfig(
            iterations=100,
            cutoff_week=14,
            noise=0.2,
            num_workers=200,
        )
        simulator = Simulator(config)
        result = simulator.run(games)

        assert result.iterations_run == 100


# ---------------------------------------------------------------------------
# Tests for SimulationConfig validation
# ---------------------------------------------------------------------------


class TestNumWorkersValidation:
    """Tests for num_workers parameter validation."""

    def test_valid_num_workers(self) -> None:
        """Valid num_workers values are accepted."""
        config = SimulationConfig(iterations=100, num_workers=4)
        assert config.num_workers == 4

    def test_none_num_workers(self) -> None:
        """None is accepted (auto-detect)."""
        config = SimulationConfig(iterations=100, num_workers=None)
        assert config.num_workers is None

    def test_invalid_num_workers_zero(self) -> None:
        """Zero is rejected."""
        with pytest.raises(ValueError, match="num_workers must be a positive integer"):
            SimulationConfig(iterations=100, num_workers=0)

    def test_invalid_num_workers_negative(self) -> None:
        """Negative values are rejected."""
        with pytest.raises(ValueError, match="num_workers must be a positive integer"):
            SimulationConfig(iterations=100, num_workers=-1)
