"""Monte Carlo simulation engine for NFL playoff probability estimation.

Runs repeated random trials to estimate playoff outcome probabilities.
Each trial simulates all remaining/unplayed games, computes standings
using the NFL's official tiebreaker rules, and records which teams
make the playoffs and at which seed.

Requirements: 5.1-5.13, 6.1-6.5
"""

from __future__ import annotations

import logging
import random
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
        MIN_ITERATIONS: Class-level minimum allowed iterations.
        MAX_ITERATIONS: Class-level maximum allowed iterations.
    """

    iterations: int = 10_000
    tie_probability: float = 0.005
    cutoff_week: int | None = None
    noise: float = 0.2

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
# Simulator Class
# ---------------------------------------------------------------------------


class Simulator:
    """Monte Carlo simulation engine for NFL playoff probabilities.

    Partitions games into fixed inputs (completed games up to cutoff week)
    and games to simulate. Runs multiple trials, each simulating remaining
    games and computing standings to determine playoff outcomes.
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

        # Initialize tracking structures
        playoff_counts: dict[str, int] = {team: 0 for team in ALL_TEAMS}
        seed_counts: dict[str, dict[int, int]] = {
            team: {seed: 0 for seed in range(1, 8)} for team in ALL_TEAMS
        }
        division_champion_counts: dict[str, int] = {team: 0 for team in ALL_TEAMS}
        scenario_tracker: dict[frozenset[tuple[str, int]], int] = {}

        iterations = self._config.iterations

        # Trial loop
        for _trial in range(iterations):
            # Simulate remaining games
            simulated_outcomes = self._simulate_remaining_games(
                games_to_simulate, strengths
            )

            # Compute standings with fixed games + simulated outcomes
            standings = compute_standings(all_games, simulated_outcomes)

            # Determine playoff bracket
            bracket = determine_playoff_bracket(standings)

            # Record outcomes
            self._record_trial_outcomes(
                bracket,
                playoff_counts,
                seed_counts,
                division_champion_counts,
                scenario_tracker,
            )

        # Aggregate probabilities
        team_results = self._aggregate_results(
            playoff_counts,
            seed_counts,
            division_champion_counts,
            strengths,
            iterations,
        )

        # Compute impact games for each team
        self._compute_all_impact_games(
            team_results,
            all_games,
            games_to_simulate,
            fixed_games,
            strengths,
            iterations,
        )

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

    def analyze_path(self, team: str, all_games: list[Game]) -> dict[str, Any]:
        """Run on-demand playoff path analysis for a specific team with causality filtering.

        Runs a focused mini-simulation, records qualifying trial outcomes,
        then applies counterfactual testing to filter out correlation artifacts.

        Args:
            team: Team name to analyze.
            all_games: Complete list of games for the season.

        Returns:
            Path analysis dict with 'path' list of causal game outcomes.
        """
        # Determine cutoff and partition
        cutoff_week = self._determine_cutoff_week(all_games)
        fixed_games, games_to_simulate = self._partition_games(all_games, cutoff_week)

        # Calculate team strengths
        strengths = self._strength_calculator.calculate(fixed_games)
        from src.nfl_teams import ALL_TEAMS
        for t in ALL_TEAMS:
            if t not in strengths:
                strengths[t] = 1.0

        iterations = self._config.iterations
        tie_prob = self._config.tie_probability

        # Run focused simulation, recording outcomes for qualifying trials
        qualifying_outcomes: list[list[tuple[str, str | None, bool]]] = []
        total_qualifying = 0

        for _ in range(iterations):
            simulated_outcomes = self._simulate_remaining_games(games_to_simulate, strengths)
            standings = compute_standings(all_games, simulated_outcomes)
            bracket = determine_playoff_bracket(standings)

            # Check if team made playoffs
            made_it = False
            for seeds_list in (bracket.afc_seeds, bracket.nfc_seeds):
                for standing in seeds_list:
                    if standing.team == team:
                        made_it = True
                        break
                if made_it:
                    break

            if made_it:
                total_qualifying += 1
                if len(qualifying_outcomes) < 200:
                    qualifying_outcomes.append(simulated_outcomes)

        if total_qualifying < 5:
            return {
                "team": team,
                "playoff_probability": round(total_qualifying / iterations * 100, 1),
                "qualifying_trials": total_qualifying,
                "path": [],
                "message": "Not enough qualifying trials for reliable path analysis.",
            }

        num_trials = len(qualifying_outcomes)
        team_conf = get_team_conference(team)

        # Build game lookup
        game_lookup: dict[str, Game] = {g.game_id: g for g in games_to_simulate}

        # Count outcome frequencies across qualifying trials
        game_outcome_counts: dict[str, dict[str, int]] = {}
        for outcomes in qualifying_outcomes:
            for game_id, winner, is_tie in outcomes:
                # Only consider games involving the team's conference
                game = game_lookup.get(game_id)
                if not game:
                    continue
                home_conf = get_team_conference(game.home_team)
                away_conf = get_team_conference(game.away_team)
                if home_conf != team_conf and away_conf != team_conf:
                    continue

                if game_id not in game_outcome_counts:
                    game_outcome_counts[game_id] = {}
                key = "tie" if is_tie else (winner or "unknown")
                game_outcome_counts[game_id][key] = game_outcome_counts[game_id].get(key, 0) + 1

        # Identify candidate path games (dominant outcome > 60%)
        candidates: list[dict[str, Any]] = []
        for game_id, outcomes in game_outcome_counts.items():
            game = game_lookup.get(game_id)
            if not game:
                continue
            most_common = max(outcomes.items(), key=lambda x: x[1])
            outcome_winner = most_common[0]
            outcome_count = most_common[1]
            pct = outcome_count / num_trials
            if pct < 0.6:
                continue
            candidates.append({
                "game_id": game_id,
                "week": game.week,
                "home_team": game.home_team,
                "away_team": game.away_team,
                "required_winner": outcome_winner if outcome_winner != "tie" else None,
                "is_tie": outcome_winner == "tie",
                "frequency": round(pct * 100, 1),
                "involves_team": game.home_team == team or game.away_team == team,
            })

        # Causality filtering: for each candidate, check if flipping the outcome
        # actually changes the team's playoff status in a sample of qualifying trials
        causal_games: list[dict[str, Any]] = []
        sample_size = min(20, num_trials)  # Test with a subset for performance

        for candidate in candidates:
            # Team's own games are always causal (they must win)
            if candidate["involves_team"]:
                causal_games.append(candidate)
                continue

            # Counterfactual test: flip this game's outcome in some qualifying trials
            flips_that_matter = 0
            for trial_outcomes in qualifying_outcomes[:sample_size]:
                # Create modified outcomes with this game flipped
                flipped = []
                for game_id, winner, is_tie in trial_outcomes:
                    if game_id == candidate["game_id"]:
                        # Flip the winner
                        game = game_lookup[game_id]
                        if is_tie:
                            # Flip tie to a win for the non-preferred team
                            other = candidate["required_winner"]
                            flipped_winner = game.away_team if other == game.home_team else game.home_team
                            flipped.append((game_id, flipped_winner, False))
                        else:
                            # Flip winner to the other team
                            other_team = game.away_team if winner == game.home_team else game.home_team
                            flipped.append((game_id, other_team, False))
                    else:
                        flipped.append((game_id, winner, is_tie))

                # Re-compute standings with flipped outcome
                flipped_standings = compute_standings(all_games, flipped)
                flipped_bracket = determine_playoff_bracket(flipped_standings)

                # Check if team still makes playoffs
                still_in = False
                for seeds_list in (flipped_bracket.afc_seeds, flipped_bracket.nfc_seeds):
                    for standing in seeds_list:
                        if standing.team == team:
                            still_in = True
                            break
                    if still_in:
                        break

                if not still_in:
                    flips_that_matter += 1

            # Only include if flipping actually dropped the team in >25% of tested trials
            if flips_that_matter > sample_size * 0.25:
                candidate["causality"] = round(flips_that_matter / sample_size * 100, 1)
                causal_games.append(candidate)

        # Sort: team's own games first, then by week, then by frequency desc
        causal_games.sort(key=lambda x: (not x["involves_team"], x["week"], -x["frequency"]))

        return {
            "team": team,
            "playoff_probability": round(total_qualifying / iterations * 100, 1),
            "qualifying_trials": total_qualifying,
            "path": causal_games,
        }

    def _compute_all_impact_games(
        self,
        team_results: dict[str, TeamResult],
        all_games: list[Game],
        games_to_simulate: list[Game],
        fixed_games: list[Game],
        strengths: dict[str, float],
        iterations: int,
    ) -> None:
        """Compute impact games for each team.

        For each team, identifies the top 5 games (from games_to_simulate)
        where the team's playoff probability changes the most between
        "team wins" and "team loses" scenarios.

        This is an approximation using a smaller sample size for efficiency.

        Args:
            team_results: Current team results (modified in place).
            all_games: All games in the season.
            games_to_simulate: Games being simulated.
            fixed_games: Fixed input games.
            strengths: Team strength ratings.
            iterations: Total iterations for the main simulation.
        """
        from src.nfl_teams import ALL_TEAMS

        # Use a reduced iteration count for impact analysis (for performance)
        impact_iterations = min(200, iterations)

        for team in ALL_TEAMS:
            # Find games involving this team or games that could affect this team
            # For simplicity, check games involving the team directly
            relevant_games = [
                g for g in games_to_simulate
                if g.home_team == team or g.away_team == team
            ]

            if not relevant_games:
                continue

            impact_scores: list[tuple[str, float]] = []

            for game in relevant_games:
                # Compute playoff probability when this team wins this game
                prob_if_win = self._estimate_prob_with_forced_outcome(
                    team, game, "win", all_games, games_to_simulate,
                    strengths, impact_iterations,
                )

                # Compute playoff probability when this team loses this game
                prob_if_lose = self._estimate_prob_with_forced_outcome(
                    team, game, "lose", all_games, games_to_simulate,
                    strengths, impact_iterations,
                )

                impact = abs(prob_if_win - prob_if_lose)
                impact_scores.append((game.game_id, impact))

            # Sort by impact descending, take top 5
            impact_scores.sort(key=lambda x: x[1], reverse=True)
            team_results[team].impact_games = impact_scores[:5]

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
            bracket = determine_playoff_bracket(standings)

            # Check if team made playoffs
            for seeds_list in (bracket.afc_seeds, bracket.nfc_seeds):
                for standing in seeds_list:
                    if standing.team == team:
                        playoff_count += 1
                        break

        return playoff_count / iterations if iterations > 0 else 0.0
