"""Team strength calculator using iterative strength-of-schedule weighting.

Computes team ratings by iteratively weighting game results by opponent
strength until convergence. Stronger opponents make wins worth more and
losses less damaging.

Algorithm:
1. Initialize all teams with rating 1.0
2. For each iteration:
   - For each team, compute new rating as SOS-adjusted win percentage:
     rating = (sum of opponent ratings for wins) / (sum of all opponent ratings)
   - Ties contribute 0.5 × opponent rating to the numerator
3. Normalize ratings so the average is 1.0
4. Check convergence: if max |new_rating - old_rating| < 0.001, stop
5. If 100 iterations reached without convergence, log warning and use final values
6. Teams with no completed games receive the league-wide average strength (1.0)
7. Apply Bayesian dampening based on sample size (see below)

Dampening (regression to the mean):
  After convergence, ratings are blended toward the league average (1.0)
  based on how many games each team has played:

    dampened = (games / (games + K)) * raw_rating + (K / (games + K)) * 1.0

  With K=8 (default), the effect is:
    - 2 games played: 80% average, 20% calculated → ratings stay near 1.0
    - 8 games played: 50% average, 50% calculated → balanced
    - 17 games (full season): 68% calculated, 32% average → mostly earned

  This prevents extreme ratings early in the season when a 2-0 start
  could otherwise produce unrealistically high playoff probabilities.
  As more games are played, the dampening effect diminishes and ratings
  increasingly reflect actual performance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.data_client import Game, GameStatus

logger = logging.getLogger(__name__)


@dataclass
class TeamRating:
    """A team's calculated strength rating.

    Attributes:
        team: The team's short name (e.g., "Chiefs").
        strength: The calculated strength rating (normalized so average = 1.0).
        games_played: Number of completed games used in the calculation.
    """

    team: str
    strength: float
    games_played: int


class TeamStrengthCalculator:
    """Iterative convergence algorithm for strength-of-schedule-weighted ratings.

    Calculates team strength ratings by repeatedly weighting game results
    by opponent quality until ratings stabilize (converge). Only uses
    completed games — the caller is responsible for filtering by cutoff week.

    Class Constants:
        CONVERGENCE_THRESHOLD: Maximum allowed delta between iterations (0.001).
        MAX_ITERATIONS: Maximum number of iterations before stopping (100).
    """

    CONVERGENCE_THRESHOLD: float = 0.001
    MAX_ITERATIONS: int = 200
    DAMPENING_K: int = 8  # Games needed before trusting the rating fully
    RELAXATION_FACTOR: float = 0.5  # Blend old and new ratings to dampen oscillation

    def calculate(self, completed_games: list[Game]) -> dict[str, float]:
        """Calculate team strength ratings from completed games.

        Iterates until max change < CONVERGENCE_THRESHOLD or MAX_ITERATIONS
        reached. Only uses games with status COMPLETED. Teams with no
        completed games receive the league-average strength (1.0).

        After convergence, applies Bayesian dampening to pull ratings toward
        the league average (1.0) based on sample size. This prevents extreme
        ratings when few games have been played.

        Dampening formula:
            dampened = (games / (games + K)) * raw_rating + (K / (games + K)) * 1.0

        With K=8, a team needs ~8 games before their rating is weighted 50/50
        between calculated and average. This produces more realistic playoff
        probabilities early in the season.

        Args:
            completed_games: List of Game objects. Only games with
                status == COMPLETED are used; others are ignored.

        Returns:
            Dictionary mapping team name to strength rating.
            Ratings are normalized so the average across all teams is 1.0.
        """
        # Filter to only completed games
        games = [g for g in completed_games if g.status == GameStatus.COMPLETED]

        # Collect all teams that appear in completed games
        teams: set[str] = set()
        for game in games:
            teams.add(game.home_team)
            teams.add(game.away_team)

        # If no completed games, return empty dict
        if not teams:
            return {}

        # Count games per team for dampening
        games_per_team: dict[str, int] = {team: 0 for team in teams}
        for game in games:
            games_per_team[game.home_team] += 1
            games_per_team[game.away_team] += 1

        # Initialize all teams at 1.0
        ratings = self._initial_ratings(teams)

        # Bootstrap: compute initial differentiation from win percentages
        # to break the symmetry (all-1.0 ratings produce all-1.0 outputs).
        # This seeds the iterative algorithm with meaningful initial values.
        ratings = self._bootstrap_ratings(teams, games)

        # Iteratively compute ratings until convergence
        deltas = []  # Track convergence history
        for iteration in range(self.MAX_ITERATIONS):
            new_ratings = self._iterate(ratings, games)
            
            # Apply relaxation to dampen oscillation
            relaxed_ratings = {
                team: self.RELAXATION_FACTOR * new_ratings[team] + (1 - self.RELAXATION_FACTOR) * ratings[team]
                for team in ratings
            }

            # Check convergence
            max_delta = self._max_delta(ratings, relaxed_ratings)
            deltas.append(max_delta)
            if max_delta < self.CONVERGENCE_THRESHOLD:
                logger.debug(
                    "Team strength converged after %d iterations (max delta: %.6f)",
                    iteration + 1,
                    max_delta,
                )
                return self._apply_dampening(relaxed_ratings, games_per_team)

            ratings = relaxed_ratings

        # Max iterations reached without convergence
        final_relaxed = {
            team: self.RELAXATION_FACTOR * self._iterate(ratings, games)[team] + (1 - self.RELAXATION_FACTOR) * ratings[team]
            for team in ratings
        }
        final_delta = self._max_delta(ratings, final_relaxed)
        avg_last_10_deltas = sum(deltas[-10:]) / min(10, len(deltas)) if deltas else final_delta
        convergence_rate = (deltas[0] - final_delta) / self.MAX_ITERATIONS if deltas else 0
        
        logger.warning(
            "Team strength calculation did not converge within %d iterations "
            "(final max delta: %.6f, avg last 10: %.6f, rate: %.9f/iter). "
            "Using final iteration ratings.",
            self.MAX_ITERATIONS,
            final_delta,
            avg_last_10_deltas,
            convergence_rate,
        )
        return self._apply_dampening(final_relaxed, games_per_team)

    def _initial_ratings(self, teams: set[str]) -> dict[str, float]:
        """Initialize all teams with a rating of 1.0.

        Args:
            teams: Set of team names to initialize.

        Returns:
            Dictionary mapping each team name to 1.0.
        """
        return {team: 1.0 for team in teams}

    def _bootstrap_ratings(
        self, teams: set[str], games: list[Game]
    ) -> dict[str, float]:
        """Compute initial ratings from win percentages to break symmetry.

        The iterative algorithm cannot differentiate teams when all ratings
        are equal (win weight = loss weight = 1.0 when opponent rating = 1.0).
        This method seeds the iteration with win-percentage-based ratings
        normalized to average 1.0, with a minimum floor to avoid division
        by zero in subsequent iterations.

        Args:
            teams: Set of team names.
            games: List of completed Game objects.

        Returns:
            Initial ratings based on win percentage, normalized to average 1.0.
            All ratings are guaranteed to be > 0.
        """
        wins: dict[str, float] = {team: 0.0 for team in teams}
        game_counts: dict[str, int] = {team: 0 for team in teams}

        for game in games:
            home = game.home_team
            away = game.away_team
            if home not in teams or away not in teams:
                continue
            if game.home_score is None or game.away_score is None:
                continue

            game_counts[home] += 1
            game_counts[away] += 1

            if game.home_score > game.away_score:
                wins[home] += 1.0
            elif game.away_score > game.home_score:
                wins[away] += 1.0
            else:
                wins[home] += 0.5
                wins[away] += 0.5

        # Compute win percentage for each team (default 0.5 for no games)
        # Use a floor of 0.1 to avoid zero ratings (which cause division by zero)
        raw_ratings: dict[str, float] = {}
        for team in teams:
            if game_counts[team] > 0:
                win_pct = wins[team] / game_counts[team]
                # Floor at 0.1 to prevent zero ratings
                raw_ratings[team] = max(win_pct, 0.1)
            else:
                raw_ratings[team] = 0.5

        # Normalize so average is 1.0
        return self._normalize(raw_ratings)

    def _iterate(
        self, ratings: dict[str, float], games: list[Game]
    ) -> dict[str, float]:
        """Compute one iteration of updated ratings.

        For each team, calculates a new rating as the weighted win ratio:
        - Each game contributes opponent_rating to the denominator (total schedule strength)
        - Each win contributes opponent_rating to the numerator
        - Each tie contributes 0.5 * opponent_rating to the numerator
        - Losses contribute 0 to the numerator

        New rating = (sum of win credits) / (sum of opponent ratings),
        then normalized so the average rating across all teams is 1.0.

        This produces a strength-of-schedule-adjusted win percentage.
        Teams with no completed games get strength 1.0 (league average).

        Args:
            ratings: Current team ratings (team name → rating).
            games: List of completed Game objects.

        Returns:
            New ratings dictionary after one iteration, normalized.
        """
        # Accumulate weighted wins and total opponent strength per team
        team_weighted_wins: dict[str, float] = {team: 0.0 for team in ratings}
        team_total_opp_strength: dict[str, float] = {team: 0.0 for team in ratings}

        for game in games:
            home = game.home_team
            away = game.away_team

            # Skip games involving teams not in our ratings dict
            if home not in ratings or away not in ratings:
                continue

            home_rating = max(ratings[home], 1e-10)
            away_rating = max(ratings[away], 1e-10)

            home_score = game.home_score
            away_score = game.away_score

            if home_score is None or away_score is None:
                continue

            # Both teams accumulate opponent strength in denominator
            team_total_opp_strength[home] += away_rating
            team_total_opp_strength[away] += home_rating

            if home_score > away_score:
                # Home team won — gets full credit of opponent's rating
                team_weighted_wins[home] += away_rating
                # Away team lost — gets 0 credit
            elif away_score > home_score:
                # Away team won
                team_weighted_wins[away] += home_rating
                # Home team lost — gets 0 credit
            else:
                # Tie — both get half credit
                team_weighted_wins[home] += 0.5 * away_rating
                team_weighted_wins[away] += 0.5 * home_rating

        # Compute new ratings
        new_ratings: dict[str, float] = {}
        for team in ratings:
            if team_total_opp_strength[team] > 0:
                # Rating = weighted wins / total opponent strength
                # This is essentially SOS-adjusted win percentage
                # Floor at a small positive value to prevent zero ratings
                raw = team_weighted_wins[team] / team_total_opp_strength[team]
                new_ratings[team] = max(raw, 0.01)
            else:
                new_ratings[team] = 1.0

        # Normalize so average rating is 1.0
        new_ratings = self._normalize(new_ratings)

        return new_ratings

    def _normalize(self, ratings: dict[str, float]) -> dict[str, float]:
        """Normalize ratings so the average is 1.0.

        Args:
            ratings: Raw ratings dictionary.

        Returns:
            Normalized ratings where the mean value is 1.0.
        """
        if not ratings:
            return ratings

        avg = sum(ratings.values()) / len(ratings)
        if avg == 0:
            # Avoid division by zero — shouldn't happen in practice
            return ratings

        return {team: rating / avg for team, rating in ratings.items()}

    def _max_delta(
        self, old: dict[str, float], new: dict[str, float]
    ) -> float:
        """Compute the maximum absolute change between two rating sets.

        Args:
            old: Previous iteration's ratings.
            new: Current iteration's ratings.

        Returns:
            Maximum absolute difference across all teams.
        """
        if not old or not new:
            return 0.0

        return max(abs(new[team] - old[team]) for team in old if team in new)

    def _apply_dampening(
        self, ratings: dict[str, float], games_per_team: dict[str, int]
    ) -> dict[str, float]:
        """Apply Bayesian dampening to pull ratings toward the mean based on sample size.

        With few games played, we lack evidence to be confident in a team's
        true strength. This method blends the calculated rating toward the
        league average (1.0) proportionally to how many games have been played.

        Formula:
            dampened = (n / (n + K)) * raw_rating + (K / (n + K)) * 1.0

        Where:
            n = number of games played by the team
            K = DAMPENING_K constant (default 8)

        Effect by games played (K=8):
            2 games:  20% calculated, 80% average
            4 games:  33% calculated, 67% average
            8 games:  50% calculated, 50% average
            12 games: 60% calculated, 40% average
            17 games: 68% calculated, 32% average

        After dampening, ratings are re-normalized so the average is 1.0.

        Args:
            ratings: Converged raw ratings (team → rating).
            games_per_team: Number of completed games per team.

        Returns:
            Dampened and normalized ratings.
        """
        k = self.DAMPENING_K
        dampened: dict[str, float] = {}

        for team, raw_rating in ratings.items():
            n = games_per_team.get(team, 0)
            weight = n / (n + k)
            dampened[team] = weight * raw_rating + (1.0 - weight) * 1.0

        # Re-normalize so average is still 1.0
        return self._normalize(dampened)
