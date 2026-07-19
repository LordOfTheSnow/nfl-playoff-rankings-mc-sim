"""Monte Carlo simulation engine for NFL playoff probability estimation.

Runs repeated random trials to estimate playoff outcome probabilities.
Each trial simulates all remaining/unplayed games, computes standings
using the NFL's official tiebreaker rules, and records which teams
make the playoffs and at which seed.

Supports parallel execution via multiprocessing: since each trial is
independent, iteration batches are distributed across worker processes
for near-linear speedup on multi-core machines.

Requirements: 5.1-5.13, 6.1-6.5, 15.1-15.8
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from src.data_client import Game, GameStatus
from src.nfl_teams import NFL_TEAMS, get_team_conference, get_team_division
from src.standings import (
    PlayoffBracket,
    compute_standings,
    determine_playoff_bracket,
)
from src.team_strength import TeamStrengthCalculator

logger = logging.getLogger(__name__)

# Use 'fork' start method on Unix for efficiency (child inherits parent memory
# via copy-on-write, no re-import overhead). On Windows, 'fork' is unavailable
# so we fall back to the default start method ('spawn').
import sys
if sys.platform == "win32":
    _mp_context = multiprocessing.get_context("spawn")
else:
    _mp_context = multiprocessing.get_context("fork")


# ---------------------------------------------------------------------------
# Configuration and Result Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SimulationConfig:
    """Configuration for a Monte Carlo simulation run.

    Attributes:
        iterations: Number of simulation trials to run (default 10000).
        tie_probability: Probability of a game ending in a tie (default 0.5%).
        cutoff_week: Optional explicit cutoff week (1-18). If None, auto-detected.
        noise: Per-game strength noise as a standard deviation (default 0.2).
            Before each simulated game, both teams' strengths are multiplied by
            a random factor drawn from a log-normal distribution with this sigma.
            0.0 = no noise (deterministic strengths), 0.2 = moderate "any given
            Sunday" variance, 0.5 = high chaos. The jitter is independent per
            game and per trial, modeling game-to-game performance fluctuation.
        num_workers: Number of worker processes for parallel simulation.
            None = auto-detect using os.cpu_count(). 1 = single-process (no overhead).
        MIN_ITERATIONS: Class-level minimum allowed iterations.
        MAX_ITERATIONS: Class-level maximum allowed iterations.
    """

    iterations: int = 10_000
    tie_probability: float = 0.005
    cutoff_week: int | None = None
    noise: float = 0.2
    num_workers: int | None = None

    MIN_ITERATIONS: int = field(default=100, init=False, repr=False)
    MAX_ITERATIONS: int = field(default=1_000_000, init=False, repr=False)

    def __post_init__(self) -> None:
        """Validate configuration parameters."""
        self.validate()

    def validate(self) -> None:
        """Validate configuration values.

        Raises:
            ValueError: If iterations or cutoff_week are outside valid ranges.
        """
        if not isinstance(self.iterations, int) or self.iterations != int(self.iterations):
            raise ValueError(
                f"iterations must be a positive integer between "
                f"{self.MIN_ITERATIONS} and {self.MAX_ITERATIONS}, got {self.iterations!r}"
            )
        if self.iterations < self.MIN_ITERATIONS or self.iterations > self.MAX_ITERATIONS:
            raise ValueError(
                f"iterations must be between {self.MIN_ITERATIONS} and "
                f"{self.MAX_ITERATIONS}, got {self.iterations}"
            )
        if self.cutoff_week is not None:
            if not isinstance(self.cutoff_week, int):
                raise ValueError(
                    f"cutoff_week must be a positive integer between 1 and 18, "
                    f"got {self.cutoff_week!r}"
                )
            if self.cutoff_week < 1 or self.cutoff_week > 18:
                raise ValueError(
                    f"cutoff_week must be between 1 and 18, got {self.cutoff_week}"
                )
        if not isinstance(self.noise, (int, float)) or self.noise < 0.0 or self.noise > 1.0:
            raise ValueError(
                f"noise must be a number between 0.0 and 1.0, got {self.noise}"
            )
        if self.num_workers is not None:
            if not isinstance(self.num_workers, int) or self.num_workers < 1:
                raise ValueError(
                    f"num_workers must be a positive integer, got {self.num_workers!r}"
                )


@dataclass
class TeamResult:
    """Simulation results for a single team.

    Attributes:
        team: Team short name (e.g., "Chiefs").
        conference: Team's conference ("AFC" or "NFC").
        division: Team's division (e.g., "West").
        playoff_probability: Probability of making playoffs (0.0 to 1.0).
        seed_distribution: Mapping of seed (1-7) to probability.
        division_champion_probability: Probability of winning the division.
        strength_rating: Calculated team strength rating.
        impact_games: Top 5 games with largest effect on playoff probability.
    """

    team: str
    conference: str
    division: str
    playoff_probability: float
    seed_distribution: dict[int, float]
    division_champion_probability: float
    strength_rating: float
    impact_games: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class ScenarioResult:
    """A distinct playoff bracket scenario observed during simulation.

    Attributes:
        bracket: Frozenset of (team, seed) tuples defining the scenario.
        frequency: Number of times this scenario was observed.
        probability: Frequency / total iterations.
    """

    bracket: frozenset[tuple[str, int]]
    frequency: int
    probability: float


@dataclass
class SimulationResult:
    """Complete results of a Monte Carlo simulation run.

    Attributes:
        team_results: Mapping of team name to TeamResult.
        scenarios: Top 50 most likely distinct scenarios.
        iterations_run: Number of iterations actually executed.
        cutoff_week: The cutoff week used for this simulation.
        low_confidence: True if statistical confidence is low.
        team_strengths: Mapping of team name to strength rating.
    """

    team_results: dict[str, TeamResult]
    scenarios: list[ScenarioResult]
    iterations_run: int
    cutoff_week: int
    low_confidence: bool
    team_strengths: dict[str, float]
    fixed_games_count: int = 0
    simulated_games_count: int = 0


# ---------------------------------------------------------------------------
# Parallel Execution Support
# ---------------------------------------------------------------------------


def _split_iterations(total: int, num_workers: int) -> list[int]:
    """Split total iterations into approximately equal batches.

    Distributes remainder across the first workers so no worker
    gets more than one extra iteration.

    Args:
        total: Total number of iterations to distribute.
        num_workers: Number of workers.

    Returns:
        List of batch sizes, one per worker.
    """
    base = total // num_workers
    remainder = total % num_workers
    return [base + (1 if i < remainder else 0) for i in range(num_workers)]


def _simulate_game_standalone(
    home_team: str,
    away_team: str,
    strengths: dict[str, float],
    tie_prob: float,
    noise: float,
    rng: random.Random,
) -> tuple[str | None, bool]:
    """Simulate a single game outcome (standalone, uses explicit RNG).

    Args:
        home_team: Home team name.
        away_team: Away team name.
        strengths: Team strength ratings.
        tie_prob: Probability of a tie.
        noise: Log-normal noise sigma for per-game jitter.
        rng: Random instance for this worker.

    Returns:
        Tuple of (winning_team_or_None, is_tie).
    """
    roll = rng.random()

    if roll < tie_prob:
        return (None, True)

    home_strength = strengths.get(home_team, 1.0)
    away_strength = strengths.get(away_team, 1.0)

    if noise > 0:
        home_strength *= rng.lognormvariate(0, noise)
        away_strength *= rng.lognormvariate(0, noise)

    total_strength = home_strength + away_strength
    if total_strength <= 0:
        home_win_prob = 0.5
    else:
        home_win_prob = home_strength / total_strength

    threshold = tie_prob + (1.0 - tie_prob) * home_win_prob
    if roll < threshold:
        return (home_team, False)
    else:
        return (away_team, False)


def _run_trial_batch(
    all_games: list[Game],
    games_to_simulate: list[Game],
    strengths: dict[str, float],
    batch_iterations: int,
    tie_probability: float,
    noise: float,
    seed: int | None,
) -> dict:
    """Run a batch of simulation trials (can execute in a worker process).

    This is the core trial loop, extracted as a module-level function so it
    can be pickled and sent to worker processes.

    Args:
        all_games: Complete list of games for the season.
        games_to_simulate: Games that need to be simulated each trial.
        strengths: Pre-computed team strength ratings.
        batch_iterations: Number of trials to run in this batch.
        tie_probability: Probability of a tie per game.
        noise: Per-game strength noise sigma.
        seed: Random seed for this worker (None for unseeded).

    Returns:
        Dict with playoff_counts, seed_counts, division_champion_counts,
        scenario_tracker.
    """
    from src.nfl_teams import ALL_TEAMS

    # Each worker gets its own RNG seeded independently
    rng = random.Random(seed)

    # Initialize tracking structures
    playoff_counts: dict[str, int] = {team: 0 for team in ALL_TEAMS}
    seed_counts: dict[str, dict[int, int]] = {
        team: {s: 0 for s in range(1, 8)} for team in ALL_TEAMS
    }
    division_champion_counts: dict[str, int] = {team: 0 for team in ALL_TEAMS}
    scenario_tracker: dict[frozenset[tuple[str, int]], int] = {}

    for _trial in range(batch_iterations):
        # Simulate remaining games
        outcomes: list[tuple[str, str | None, bool]] = []
        for game in games_to_simulate:
            winner, is_tie = _simulate_game_standalone(
                game.home_team, game.away_team, strengths, tie_probability, noise, rng
            )
            outcomes.append((game.game_id, winner, is_tie))

        # Compute standings with fixed games + simulated outcomes
        standings = compute_standings(all_games, outcomes)

        # Determine playoff bracket
        bracket = determine_playoff_bracket(standings, all_games=all_games, simulated_outcomes=outcomes)

        # Record outcomes
        scenario_key: set[tuple[str, int]] = set()

        for seeds_list in (bracket.afc_seeds, bracket.nfc_seeds):
            for standing in seeds_list:
                team = standing.team
                seed_val = standing.seed

                if seed_val is None:
                    continue

                playoff_counts[team] += 1

                if seed_val in seed_counts.get(team, {}):
                    seed_counts[team][seed_val] += 1

                if standing.is_division_champion:
                    division_champion_counts[team] += 1

                scenario_key.add((team, seed_val))

        frozen_scenario = frozenset(scenario_key)
        scenario_tracker[frozen_scenario] = (
            scenario_tracker.get(frozen_scenario, 0) + 1
        )

    return {
        "playoff_counts": playoff_counts,
        "seed_counts": seed_counts,
        "division_champion_counts": division_champion_counts,
        "scenario_tracker": scenario_tracker,
    }


def _run_trial_batch_wrapper(args: tuple) -> dict:
    """Wrapper for _run_trial_batch that unpacks a tuple of arguments.

    Required because ProcessPoolExecutor.map() passes a single argument
    per call.

    Args:
        args: Tuple of (all_games, games_to_simulate, strengths,
              batch_iterations, tie_probability, noise, seed).

    Returns:
        Result dict from _run_trial_batch.
    """
    (all_games, games_to_simulate, strengths, batch_iterations,
     tie_probability, noise, seed) = args
    return _run_trial_batch(
        all_games, games_to_simulate, strengths, batch_iterations,
        tie_probability, noise, seed,
    )


def _compute_team_impact_worker(args: tuple) -> list[tuple[str, float]]:
    """Worker function for parallel impact games computation.

    Computes the top 5 impact games for a single team by running
    mini-simulations with forced outcomes.

    Args:
        args: Tuple of (team, all_games, games_to_simulate, strengths,
              impact_iterations, tie_probability, noise).

    Returns:
        Top 5 (game_id, impact) tuples sorted by impact descending.
    """
    (team, all_games, games_to_simulate, strengths,
     impact_iterations, tie_probability, noise) = args

    relevant_games = [
        g for g in games_to_simulate
        if g.home_team == team or g.away_team == team
    ]

    rng = random.Random()
    impact_scores: list[tuple[str, float]] = []

    for game in relevant_games:
        # Estimate probability with forced win
        prob_if_win = _estimate_prob_forced(
            team, game, "win", all_games, games_to_simulate,
            strengths, impact_iterations, tie_probability, noise, rng,
        )
        # Estimate probability with forced loss
        prob_if_lose = _estimate_prob_forced(
            team, game, "lose", all_games, games_to_simulate,
            strengths, impact_iterations, tie_probability, noise, rng,
        )
        impact = abs(prob_if_win - prob_if_lose)
        impact_scores.append((game.game_id, impact))

    impact_scores.sort(key=lambda x: x[1], reverse=True)
    return impact_scores[:5]


def _estimate_prob_forced(
    team: str,
    forced_game: Game,
    outcome: str,
    all_games: list[Game],
    games_to_simulate: list[Game],
    strengths: dict[str, float],
    iterations: int,
    tie_probability: float,
    noise: float,
    rng: random.Random,
) -> float:
    """Estimate a team's playoff probability with one game forced (standalone).

    Used by the parallel impact worker.
    """
    playoff_count = 0

    if outcome == "win":
        forced_winner: str | None = team
    else:
        if forced_game.home_team == team:
            forced_winner = forced_game.away_team
        else:
            forced_winner = forced_game.home_team

    for _ in range(iterations):
        outcomes: list[tuple[str, str | None, bool]] = []

        for game in games_to_simulate:
            if game.game_id == forced_game.game_id:
                outcomes.append((game.game_id, forced_winner, False))
            else:
                winner, is_tie = _simulate_game_standalone(
                    game.home_team, game.away_team, strengths,
                    tie_probability, noise, rng,
                )
                outcomes.append((game.game_id, winner, is_tie))

        standings = compute_standings(all_games, outcomes)
        bracket = determine_playoff_bracket(standings, all_games=all_games, simulated_outcomes=outcomes)

        for seeds_list in (bracket.afc_seeds, bracket.nfc_seeds):
            for standing in seeds_list:
                if standing.team == team:
                    playoff_count += 1
                    break

    return playoff_count / iterations if iterations > 0 else 0.0


def _merge_batch_results(
    batch_results: list[dict],
) -> tuple[
    dict[str, int],
    dict[str, dict[int, int]],
    dict[str, int],
    dict[frozenset[tuple[str, int]], int],
]:
    """Merge results from multiple worker batches into unified counters.

    Args:
        batch_results: List of result dicts from _run_trial_batch.

    Returns:
        Tuple of (playoff_counts, seed_counts, division_champion_counts,
        scenario_tracker) with summed values across all batches.
    """
    from src.nfl_teams import ALL_TEAMS

    # Initialize merged structures
    playoff_counts: dict[str, int] = {team: 0 for team in ALL_TEAMS}
    seed_counts: dict[str, dict[int, int]] = {
        team: {s: 0 for s in range(1, 8)} for team in ALL_TEAMS
    }
    division_champion_counts: dict[str, int] = {team: 0 for team in ALL_TEAMS}
    scenario_tracker: dict[frozenset[tuple[str, int]], int] = {}

    for result in batch_results:
        # Sum playoff counts
        for team, count in result["playoff_counts"].items():
            playoff_counts[team] += count

        # Sum seed counts
        for team, seeds in result["seed_counts"].items():
            for seed_val, count in seeds.items():
                seed_counts[team][seed_val] += count

        # Sum division champion counts
        for team, count in result["division_champion_counts"].items():
            division_champion_counts[team] += count

        # Merge scenario trackers
        for scenario_key, count in result["scenario_tracker"].items():
            scenario_tracker[scenario_key] = (
                scenario_tracker.get(scenario_key, 0) + count
            )

    return playoff_counts, seed_counts, division_champion_counts, scenario_tracker


# ---------------------------------------------------------------------------
# Simulator Class
# ---------------------------------------------------------------------------


class Simulator:
    """Monte Carlo simulation engine for NFL playoff probabilities.

    Partitions games into fixed inputs (completed games up to cutoff week)
    and games to simulate. Runs multiple trials, each simulating remaining
    games and computing standings to determine playoff outcomes.

    Supports parallel execution: when num_workers > 1, distributes trial
    batches across multiple processes for near-linear speedup.
    """

    def __init__(self, config: SimulationConfig | None = None) -> None:
        """Initialize the simulator with configuration.

        Args:
            config: Simulation configuration. Uses defaults if None.
        """
        self._config = config or SimulationConfig()
        self._strength_calculator = TeamStrengthCalculator()

    def run(self, all_games: list[Game]) -> SimulationResult:
        """Run the Monte Carlo simulation.

        Partitions games by cutoff_week:
        - Weeks 1..cutoff with status=completed → fixed inputs
        - All other games (including in-progress) → simulated

        Calculates team strengths from fixed games only.
        In-progress games are treated as unplayed — live scores are
        informational only and do not influence simulation.

        When num_workers > 1, distributes iterations across worker processes
        for parallel execution.

        Args:
            all_games: Complete list of games for the season.

        Returns:
            SimulationResult with probabilities and scenario data.
        """
        # Determine cutoff week
        cutoff_week = self._determine_cutoff_week(all_games)

        # Partition games
        fixed_games, games_to_simulate = self._partition_games(all_games, cutoff_week)

        # Calculate team strengths from fixed games only
        strengths = self._strength_calculator.calculate(fixed_games)

        # Ensure all 32 teams have a strength rating (default 1.0 for missing)
        from src.nfl_teams import ALL_TEAMS
        for team in ALL_TEAMS:
            if team not in strengths:
                strengths[team] = 1.0

        iterations = self._config.iterations

        # Determine number of workers
        num_workers = self._config.num_workers
        if num_workers is None:
            num_workers = os.cpu_count() or 1
        num_workers = min(num_workers, iterations)  # Don't use more workers than iterations

        if num_workers <= 1:
            # Single-process execution (no multiprocessing overhead)
            batch_result = _run_trial_batch(
                all_games=all_games,
                games_to_simulate=games_to_simulate,
                strengths=strengths,
                batch_iterations=iterations,
                tie_probability=self._config.tie_probability,
                noise=self._config.noise,
                seed=None,
            )
            playoff_counts = batch_result["playoff_counts"]
            seed_counts = batch_result["seed_counts"]
            division_champion_counts = batch_result["division_champion_counts"]
            scenario_tracker = batch_result["scenario_tracker"]
        else:
            # Parallel execution across multiple worker processes
            logger.info(
                "Running simulation with %d workers (%d iterations each, approx.)",
                num_workers,
                iterations // num_workers,
            )
            batch_sizes = _split_iterations(iterations, num_workers)
            # Generate independent seeds for each worker
            seeds = [random.randint(0, 2**63 - 1) for _ in range(num_workers)]

            batch_args = [
                (all_games, games_to_simulate, strengths, batch_size,
                 self._config.tie_probability, self._config.noise, seed)
                for batch_size, seed in zip(batch_sizes, seeds)
            ]

            try:
                with ProcessPoolExecutor(max_workers=num_workers, mp_context=_mp_context) as pool:
                    batch_results = list(pool.map(_run_trial_batch_wrapper, batch_args))
            except Exception as e:
                raise RuntimeError(
                    f"Parallel simulation failed: {e}. "
                    f"Try running with num_workers=1 to disable parallelism."
                ) from e

            # Merge results from all workers
            playoff_counts, seed_counts, division_champion_counts, scenario_tracker = (
                _merge_batch_results(batch_results)
            )

        # Aggregate probabilities
        team_results = self._aggregate_results(
            playoff_counts,
            seed_counts,
            division_champion_counts,
            strengths,
            iterations,
        )

        # Compute impact games for each team (parallelized)
        import time as _time
        t_impact_start = _time.perf_counter()

        num_workers = self._config.num_workers
        if num_workers is None:
            num_workers = os.cpu_count() or 1

        self._compute_all_impact_games(
            team_results,
            all_games,
            games_to_simulate,
            fixed_games,
            strengths,
            iterations,
            num_workers,
        )
        t_impact_elapsed = _time.perf_counter() - t_impact_start
        logger.info("Impact games computation took %.2fs", t_impact_elapsed)

        # Get top 50 scenarios
        scenarios = self._get_top_scenarios(scenario_tracker, iterations)

        # Determine low confidence
        low_confidence = iterations < 1000

        return SimulationResult(
            team_results=team_results,
            scenarios=scenarios,
            iterations_run=iterations,
            cutoff_week=cutoff_week,
            low_confidence=low_confidence,
            team_strengths=strengths,
            fixed_games_count=len(fixed_games),
            simulated_games_count=len(games_to_simulate),
        )

    def _determine_cutoff_week(self, games: list[Game]) -> int:
        """Determine the cutoff week for the simulation.

        If an explicit cutoff_week is configured, use it.
        Otherwise, find the latest week where ALL games are completed.
        If no week is fully complete, return 0 (all games simulated).

        Args:
            games: All games in the season.

        Returns:
            The cutoff week number (0-18).
        """
        if self._config.cutoff_week is not None:
            return self._config.cutoff_week

        # Find the latest week where ALL games are completed
        for week in range(18, 0, -1):
            week_games = [g for g in games if g.week == week]
            if week_games and all(
                g.status == GameStatus.COMPLETED for g in week_games
            ):
                return week

        return 0  # No completed weeks

    def _partition_games(
        self, all_games: list[Game], cutoff_week: int
    ) -> tuple[list[Game], list[Game]]:
        """Partition games into fixed inputs and games to simulate.

        Fixed inputs: completed games in weeks 1..cutoff_week.
        To simulate: all other games (scheduled, in-progress, postponed in
        any week, plus all games in weeks > cutoff_week regardless of status).

        In-progress games are treated as unplayed — their current scores
        are IGNORED.

        Args:
            all_games: Complete list of games.
            cutoff_week: The cutoff week boundary.

        Returns:
            Tuple of (fixed_games, games_to_simulate).
        """
        fixed_games: list[Game] = []
        games_to_simulate: list[Game] = []

        for game in all_games:
            if (
                game.week <= cutoff_week
                and game.status == GameStatus.COMPLETED
            ):
                fixed_games.append(game)
            else:
                games_to_simulate.append(game)

        return fixed_games, games_to_simulate

    def _simulate_game(
        self,
        home_team: str,
        away_team: str,
        strengths: dict[str, float],
        tie_prob: float,
    ) -> tuple[str | None, bool]:
        """Simulate a single game outcome with per-game strength noise.

        Algorithm:
        1. Apply noise: jitter both teams' strengths by multiplying with a
           random factor drawn from a log-normal distribution (mu=0, sigma=noise).
           This models game-to-game performance variance ("any given Sunday").
        2. Roll random.random()
        3. If roll < tie_prob → tie
        4. Otherwise, home_win_prob = jittered_home / (jittered_home + jittered_away)
           If roll < tie_prob + (1 - tie_prob) * home_win_prob → home wins
           Else → away wins

        Args:
            home_team: Home team name.
            away_team: Away team name.
            strengths: Team strength ratings.
            tie_prob: Probability of a tie.

        Returns:
            Tuple of (winning_team_or_None, is_tie).
            If tie: (None, True). If home wins: (home_team, False).
            If away wins: (away_team, False).
        """
        roll = random.random()

        # Check for tie
        if roll < tie_prob:
            return (None, True)

        # Get base strengths
        home_strength = strengths.get(home_team, 1.0)
        away_strength = strengths.get(away_team, 1.0)

        # Apply per-game noise (log-normal jitter preserves positivity)
        noise = self._config.noise
        if noise > 0:
            home_strength *= random.lognormvariate(0, noise)
            away_strength *= random.lognormvariate(0, noise)

        # Avoid division by zero
        total_strength = home_strength + away_strength
        if total_strength <= 0:
            home_win_prob = 0.5
        else:
            home_win_prob = home_strength / total_strength

        # Check if home wins
        threshold = tie_prob + (1.0 - tie_prob) * home_win_prob
        if roll < threshold:
            return (home_team, False)
        else:
            return (away_team, False)

    def _simulate_remaining_games(
        self,
        games_to_simulate: list[Game],
        strengths: dict[str, float],
    ) -> list[tuple[str, str | None, bool]]:
        """Simulate all remaining games for one trial.

        Args:
            games_to_simulate: Games that need to be simulated.
            strengths: Team strength ratings.

        Returns:
            List of (game_id, winning_team, is_tie) tuples.
            For ties, winning_team is None.
        """
        outcomes: list[tuple[str, str | None, bool]] = []
        tie_prob = self._config.tie_probability

        for game in games_to_simulate:
            winner, is_tie = self._simulate_game(
                game.home_team, game.away_team, strengths, tie_prob
            )
            outcomes.append((game.game_id, winner, is_tie))

        return outcomes

    def _record_trial_outcomes(
        self,
        bracket: PlayoffBracket,
        playoff_counts: dict[str, int],
        seed_counts: dict[str, dict[int, int]],
        division_champion_counts: dict[str, int],
        scenario_tracker: dict[frozenset[tuple[str, int]], int],
    ) -> None:
        """Record the outcomes of a single trial.

        Args:
            bracket: The playoff bracket from this trial.
            playoff_counts: Running count of playoff appearances per team.
            seed_counts: Running count of seed assignments per team.
            division_champion_counts: Running count of division titles per team.
            scenario_tracker: Running count of distinct scenarios.
        """
        # Build scenario key from this bracket
        scenario_key: set[tuple[str, int]] = set()

        for seeds_list in (bracket.afc_seeds, bracket.nfc_seeds):
            for standing in seeds_list:
                team = standing.team
                seed = standing.seed

                if seed is None:
                    continue

                # Record playoff appearance
                playoff_counts[team] += 1

                # Record seed
                if seed in seed_counts.get(team, {}):
                    seed_counts[team][seed] += 1

                # Record division champion
                if standing.is_division_champion:
                    division_champion_counts[team] += 1

                # Add to scenario
                scenario_key.add((team, seed))

        # Track scenario
        frozen_scenario = frozenset(scenario_key)
        scenario_tracker[frozen_scenario] = (
            scenario_tracker.get(frozen_scenario, 0) + 1
        )

    def _aggregate_results(
        self,
        playoff_counts: dict[str, int],
        seed_counts: dict[str, dict[int, int]],
        division_champion_counts: dict[str, int],
        strengths: dict[str, float],
        iterations: int,
    ) -> dict[str, TeamResult]:
        """Aggregate trial results into probabilities.

        Args:
            playoff_counts: Total playoff appearances per team.
            seed_counts: Total seed assignments per team.
            division_champion_counts: Total division titles per team.
            strengths: Team strength ratings.
            iterations: Total number of iterations run.

        Returns:
            Dictionary mapping team name to TeamResult.
        """
        from src.nfl_teams import ALL_TEAMS

        team_results: dict[str, TeamResult] = {}

        for team in ALL_TEAMS:
            conference = get_team_conference(team) or "Unknown"
            div_info = get_team_division(team)
            division = div_info[1] if div_info else "Unknown"

            playoff_prob = playoff_counts[team] / iterations if iterations > 0 else 0.0

            seed_dist: dict[int, float] = {}
            for seed in range(1, 8):
                count = seed_counts.get(team, {}).get(seed, 0)
                seed_dist[seed] = count / iterations if iterations > 0 else 0.0

            div_champ_prob = (
                division_champion_counts[team] / iterations if iterations > 0 else 0.0
            )

            team_results[team] = TeamResult(
                team=team,
                conference=conference,
                division=division,
                playoff_probability=playoff_prob,
                seed_distribution=seed_dist,
                division_champion_probability=div_champ_prob,
                strength_rating=strengths.get(team, 1.0),
            )

        return team_results

    def _get_top_scenarios(
        self,
        scenario_tracker: dict[frozenset[tuple[str, int]], int],
        iterations: int,
    ) -> list[ScenarioResult]:
        """Get the top scenarios, taking at least 50 and expanding through ties.

        Always includes at least 50 scenarios (or all if fewer exist). If the
        50th scenario ties in frequency with subsequent ones, continues including
        all scenarios at that same frequency. Capped at 200.

        Args:
            scenario_tracker: Mapping of scenario → frequency count.
            iterations: Total iterations run.

        Returns:
            List of ScenarioResult objects, sorted by frequency descending.
        """
        if not scenario_tracker:
            return []

        # Sort by frequency descending
        sorted_scenarios = sorted(
            scenario_tracker.items(), key=lambda x: x[1], reverse=True
        )

        # Take at least 50, then expand through ties at the boundary
        # But don't expand for single-occurrence scenarios (frequency=1) as those are noise
        min_count = 50
        results: list[ScenarioResult] = []

        for i, (bracket_key, frequency) in enumerate(sorted_scenarios):
            probability = frequency / iterations if iterations > 0 else 0.0

            if i >= min_count:
                # Past the minimum — only continue if same frequency as previous
                # AND frequency > 1 (don't expand for single-occurrence noise)
                if frequency < results[-1].frequency or frequency <= 1:
                    break

            results.append(
                ScenarioResult(
                    bracket=bracket_key,
                    frequency=frequency,
                    probability=probability,
                )
            )

            # Safety cap
            if len(results) >= 200:
                break

        return results

    def _compute_all_impact_games(
        self,
        team_results: dict[str, TeamResult],
        all_games: list[Game],
        games_to_simulate: list[Game],
        fixed_games: list[Game],
        strengths: dict[str, float],
        iterations: int,
        num_workers: int = 1,
    ) -> None:
        """Compute impact games for each team.

        For each team, identifies the top 5 games (from games_to_simulate)
        where the team's playoff probability changes the most between
        "team wins" and "team loses" scenarios.

        This is an approximation using a smaller sample size for efficiency.
        When num_workers > 1, teams are processed in parallel.

        Args:
            team_results: Current team results (modified in place).
            all_games: All games in the season.
            games_to_simulate: Games being simulated.
            fixed_games: Fixed input games.
            strengths: Team strength ratings.
            iterations: Total iterations for the main simulation.
            num_workers: Number of parallel workers to use.
        """
        from src.nfl_teams import ALL_TEAMS

        # Use a reduced iteration count for impact analysis (for performance)
        impact_iterations = min(200, iterations)

        # Collect teams that have relevant games
        teams_with_games = []
        for team in ALL_TEAMS:
            relevant_games = [
                g for g in games_to_simulate
                if g.home_team == team or g.away_team == team
            ]
            if relevant_games:
                teams_with_games.append(team)

        if not teams_with_games:
            return

        if num_workers <= 1 or len(teams_with_games) < 2:
            # Single-process: compute sequentially
            for team in teams_with_games:
                impact_scores = self._compute_team_impact(
                    team, all_games, games_to_simulate, strengths, impact_iterations
                )
                team_results[team].impact_games = impact_scores
        else:
            # Parallel: distribute teams across workers
            args_list = [
                (team, all_games, games_to_simulate, strengths, impact_iterations,
                 self._config.tie_probability, self._config.noise)
                for team in teams_with_games
            ]
            try:
                with ProcessPoolExecutor(max_workers=num_workers, mp_context=_mp_context) as pool:
                    results = list(pool.map(_compute_team_impact_worker, args_list))
                for team, impact_scores in zip(teams_with_games, results):
                    team_results[team].impact_games = impact_scores
            except Exception as e:
                logger.warning("Parallel impact computation failed (%s), falling back to sequential", e)
                for team in teams_with_games:
                    impact_scores = self._compute_team_impact(
                        team, all_games, games_to_simulate, strengths, impact_iterations
                    )
                    team_results[team].impact_games = impact_scores

    def _compute_team_impact(
        self,
        team: str,
        all_games: list[Game],
        games_to_simulate: list[Game],
        strengths: dict[str, float],
        impact_iterations: int,
    ) -> list[tuple[str, float]]:
        """Compute impact scores for a single team's relevant games.

        Args:
            team: Team name.
            all_games: All games in the season.
            games_to_simulate: Games being simulated.
            strengths: Team strength ratings.
            impact_iterations: Number of mini-trials per forced outcome.

        Returns:
            Top 5 (game_id, impact) tuples sorted by impact descending.
        """
        relevant_games = [
            g for g in games_to_simulate
            if g.home_team == team or g.away_team == team
        ]

        impact_scores: list[tuple[str, float]] = []

        for game in relevant_games:
            prob_if_win = self._estimate_prob_with_forced_outcome(
                team, game, "win", all_games, games_to_simulate,
                strengths, impact_iterations,
            )
            prob_if_lose = self._estimate_prob_with_forced_outcome(
                team, game, "lose", all_games, games_to_simulate,
                strengths, impact_iterations,
            )
            impact = abs(prob_if_win - prob_if_lose)
            impact_scores.append((game.game_id, impact))

        impact_scores.sort(key=lambda x: x[1], reverse=True)
        return impact_scores[:5]

    def _estimate_prob_with_forced_outcome(
        self,
        team: str,
        forced_game: Game,
        outcome: str,
        all_games: list[Game],
        games_to_simulate: list[Game],
        strengths: dict[str, float],
        iterations: int,
    ) -> float:
        """Estimate a team's playoff probability with one game's outcome forced.

        Args:
            team: Team to compute probability for.
            forced_game: The game whose outcome is forced.
            outcome: "win" or "lose" for the specified team.
            all_games: All games in the season.
            games_to_simulate: Games being simulated.
            strengths: Team strength ratings.
            iterations: Number of mini-trials to run.

        Returns:
            Estimated playoff probability (0.0 to 1.0).
        """
        playoff_count = 0
        tie_prob = self._config.tie_probability

        # Determine the forced outcome
        if outcome == "win":
            forced_winner: str | None = team
            forced_is_tie = False
        else:
            # Team loses — the other team wins
            if forced_game.home_team == team:
                forced_winner = forced_game.away_team
            else:
                forced_winner = forced_game.home_team
            forced_is_tie = False

        for _ in range(iterations):
            outcomes: list[tuple[str, str | None, bool]] = []

            for game in games_to_simulate:
                if game.game_id == forced_game.game_id:
                    outcomes.append((game.game_id, forced_winner, forced_is_tie))
                else:
                    winner, is_tie = self._simulate_game(
                        game.home_team, game.away_team, strengths, tie_prob
                    )
                    outcomes.append((game.game_id, winner, is_tie))

            standings = compute_standings(all_games, outcomes)
            bracket = determine_playoff_bracket(standings, all_games=all_games, simulated_outcomes=outcomes)

            # Check if team made playoffs
            for seeds_list in (bracket.afc_seeds, bracket.nfc_seeds):
                for standing in seeds_list:
                    if standing.team == team:
                        playoff_count += 1
                        break

        return playoff_count / iterations if iterations > 0 else 0.0
