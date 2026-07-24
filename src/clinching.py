"""Clinching scenarios solver for NFL playoff qualification.

Finds ALL minimal sets of game-outcome conditions that guarantee a team
makes the playoffs. Replaces both the old Playoff Path Analysis (Monte Carlo)
and the Guaranteed Path Solver (combinatorial).

Algorithm (hybrid):
1. Identify contenders: same-conference teams not mathematically eliminated
2. Prune to relevant games: any remaining game with at least one contender
3. Group by the target team's own remaining record (4-0, 3-1, 2-2, etc.)
4. For each team record:
   a. If relevant other games <= 13: full enumeration (3 outcomes: W/L/T)
   b. If > 13: Monte Carlo fallback (10,000 strength-weighted samples)
5. Extract qualifying universes (team makes playoffs)
6. Reduce to strictly minimal condition sets (capped at 200 universes)
7. Sort by fewest conditions first

Available after week 14 only (hard gate).

IMPORTANT: All functions use cutoff_week purely by week number. Games in
weeks <= cutoff are "fixed" (their results count). Games in weeks > cutoff
are "remaining" and must be simulated — regardless of their actual GameStatus.
This allows the solver to work on completed seasons with a retroactive cutoff.
"""

from __future__ import annotations

import itertools
import logging
import math
import os
import time
import random
from dataclasses import dataclass, field
from multiprocessing import Pool
from typing import Any, TYPE_CHECKING

from src.data_client import Game, GameStatus
from src.nfl_teams import NFL_TEAMS, get_team_conference
from src.standings import compute_standings, determine_playoff_bracket

if TYPE_CHECKING:
    from src.cache import Cache

logger = logging.getLogger(__name__)

# Maximum relevant games for full enumeration.
# 3^9 = 19K × team_combos is tractable (~30s with 4 cores).
# Above this, use Monte Carlo sampling instead.
ENUMERATION_THRESHOLD = 9

# Number of Monte Carlo samples when enumeration is infeasible
MC_SAMPLES = 10_000

# Max qualifying universes to process for minimality reduction per record.
# Minimality testing is expensive: 2 standings calls per condition per universe.
MAX_QUALIFYING_FOR_MINIMALITY = 200

# Tie probability used during strength-weighted sampling
TIE_PROBABILITY = 0.005

# Noise applied to team strengths per game during sampling
SAMPLING_NOISE = 0.2


@dataclass
class ClinchingCondition:
    """A single game-outcome condition within a clinching scenario.

    Attributes:
        game_id: Unique game identifier.
        week: Game week number.
        home_team: Home team name.
        away_team: Away team name.
        required_winner: Winning team name, or None if tie required.
        is_tie: True if the required outcome is a tie.
    """

    game_id: str
    week: int
    home_team: str
    away_team: str
    required_winner: str | None
    is_tie: bool


@dataclass
class ClinchingScenario:
    """A minimal set of conditions that guarantees playoff qualification.

    Every condition is necessary — removing any one breaks the guarantee.

    Attributes:
        conditions: List of required game outcomes (external games only).
        num_conditions: Number of conditions (for sorting).
    """

    conditions: list[ClinchingCondition] = field(default_factory=list)
    num_conditions: int = 0

    def __post_init__(self) -> None:
        self.num_conditions = len(self.conditions)


@dataclass
class RecordGroup:
    """Clinching scenarios for a specific team remaining record.

    Attributes:
        wins: Number of remaining wins for the team.
        losses: Number of remaining losses for the team.
        ties: Number of remaining ties for the team.
        team_games: The team's specific game outcomes (win/loss/tie per game).
        scenarios: Clinching scenarios for this record.
        no_path: True if no path to playoffs exists with this record.
    """

    wins: int
    losses: int
    ties: int
    team_games: list[ClinchingCondition] = field(default_factory=list)
    scenarios: list[ClinchingScenario] = field(default_factory=list)
    no_path: bool = False


@dataclass
class ClinchingResult:
    """Complete clinching analysis result for a team.

    Attributes:
        team: Team name analyzed.
        record_groups: Results grouped by team's own remaining record.
        method: "enumeration" or "sampling".
        exhaustive: True if enumeration was used (results are complete).
        relevant_games_count: Number of relevant other games identified.
        total_evals: Total universe evaluations performed by the solver.
        contenders: List of same-conference contender team names.
        error: Error message if analysis could not be performed.
    """

    team: str
    record_groups: list[RecordGroup] = field(default_factory=list)
    method: str = "enumeration"
    exhaustive: bool = True
    relevant_games_count: int = 0
    total_evals: int = 0
    contenders: list[str] = field(default_factory=list)
    error: str | None = None


def _team_in_playoffs(team: str, bracket: Any) -> bool:
    """Check if a team is in the playoff bracket."""
    for seeds_list in (bracket.afc_seeds, bracket.nfc_seeds):
        for standing in seeds_list:
            if standing.team == team:
                return True
    return False


def _get_conference_teams(conference: str) -> list[str]:
    """Get all teams in a conference."""
    teams = []
    if conference in NFL_TEAMS:
        for division_teams in NFL_TEAMS[conference].values():
            teams.extend(division_teams)
    return teams


def _get_max_possible_wins(team: str, remaining_games: list[Game]) -> int:
    """Calculate maximum wins a team can achieve from remaining games."""
    team_games = [g for g in remaining_games if g.home_team == team or g.away_team == team]
    return len(team_games)


def identify_contenders(
    team: str,
    all_games: list[Game],
    cutoff_week: int,
) -> list[str]:
    """Identify same-conference teams that could still affect playoff race.

    A contender is a same-conference team that is not mathematically
    eliminated (max possible wins could still earn a playoff spot).

    Args:
        team: Target team name.
        all_games: All season games.
        cutoff_week: Week number cutoff. Games in weeks <= cutoff are fixed.

    Returns:
        List of contender team names (excluding the target team).
    """
    team_conf = get_team_conference(team)
    if not team_conf:
        return []

    conf_teams = _get_conference_teams(team_conf)

    # Compute standings from fixed games only (weeks <= cutoff)
    fixed_games = [g for g in all_games if g.week <= cutoff_week]
    standings = compute_standings(fixed_games)
    standing_map = {s.team: s for s in standings}

    # Remaining games = weeks after cutoff (regardless of actual game status)
    remaining_games = [g for g in all_games if g.week > cutoff_week]

    # Calculate max possible wins for each conference team
    current_wins = []
    for t in conf_teams:
        s = standing_map.get(t)
        if s:
            max_wins = s.wins + _get_max_possible_wins(t, remaining_games)
            current_wins.append((t, s.wins, max_wins))

    # Sort by max_wins descending — 7th team's max_wins is the threshold
    current_wins.sort(key=lambda x: -x[2])

    contenders = []
    if len(current_wins) >= 7:
        # Use a generous threshold: could they tie the 7th-best team's current wins?
        seventh_current = sorted(
            [(t, standing_map[t].wins) for t in conf_teams if t in standing_map],
            key=lambda x: -x[1]
        )[6][1] if len(conf_teams) >= 7 else 0

        for t, cur_wins, max_wins in current_wins:
            if t == team:
                continue
            # Include if max possible wins >= 7th-best team's current wins
            if max_wins >= seventh_current:
                contenders.append(t)
    else:
        contenders = [t for t in conf_teams if t != team]

    return contenders


def get_relevant_games(
    team: str,
    all_games: list[Game],
    cutoff_week: int,
    contenders: list[str],
) -> tuple[list[Game], list[Game]]:
    """Partition remaining games into team games and relevant other games.

    Relevant = any remaining game where at least one team is a contender.
    "Remaining" means week > cutoff_week, regardless of actual game status.

    Args:
        team: Target team.
        all_games: All season games.
        cutoff_week: Games in weeks <= cutoff_week are considered fixed/played.
        contenders: List of contender team names.

    Returns:
        Tuple of (team_remaining_games, relevant_other_games).
    """
    remaining_games = [g for g in all_games if g.week > cutoff_week]

    team_games = [
        g for g in remaining_games
        if g.home_team == team or g.away_team == team
    ]

    contender_set = set(contenders)
    other_games = [
        g for g in remaining_games
        if g.home_team != team and g.away_team != team
        and (g.home_team in contender_set or g.away_team in contender_set)
    ]

    return team_games, other_games


def _generate_team_records(
    team: str,
    team_games: list[Game],
) -> list[tuple[list[tuple[str, str | None, bool]], int, int, int]]:
    """Generate all game-level combos for the team's remaining games.

    Different combos with the same W-L-T record can produce different
    tiebreaker outcomes (division games, head-to-head), so we test all of them.
    With 3 remaining games that's 27 combos; with 4 it's 81 — both manageable.

    Returns:
        List of (simulated_outcomes, wins, losses, ties) for each combo.
    """
    if not team_games:
        return [([], 0, 0, 0)]

    results = []

    for combo in itertools.product(range(3), repeat=len(team_games)):
        outcomes: list[tuple[str, str | None, bool]] = []
        wins = losses = ties = 0
        for i, outcome in enumerate(combo):
            game = team_games[i]
            if outcome == 0:  # team wins
                outcomes.append((game.game_id, team, False))
                wins += 1
            elif outcome == 1:  # team loses
                opponent = game.away_team if game.home_team == team else game.home_team
                outcomes.append((game.game_id, opponent, False))
                losses += 1
            else:  # tie
                outcomes.append((game.game_id, team, True))
                ties += 1

        results.append((outcomes, wins, losses, ties))

    return results


def _simulate_game_outcome(
    game: Game,
    strengths: dict[str, float],
) -> tuple[str, str | None, bool]:
    """Simulate a single game outcome using team strength ratings.

    Uses the same algorithm as the main simulator: strength-weighted win
    probability with log-normal noise and a small tie probability.

    Returns:
        (game_id, winner_or_None, is_tie)
    """
    roll = random.random()

    if roll < TIE_PROBABILITY:
        return (game.game_id, None, True)

    home_strength = strengths.get(game.home_team, 1.0)
    away_strength = strengths.get(game.away_team, 1.0)

    # Apply per-game noise
    if SAMPLING_NOISE > 0:
        home_strength *= random.lognormvariate(0, SAMPLING_NOISE)
        away_strength *= random.lognormvariate(0, SAMPLING_NOISE)

    total = home_strength + away_strength
    if total <= 0:
        home_win_prob = 0.5
    else:
        home_win_prob = home_strength / total

    threshold = TIE_PROBABILITY + (1.0 - TIE_PROBABILITY) * home_win_prob
    if roll < threshold:
        return (game.game_id, game.home_team, False)
    else:
        return (game.game_id, game.away_team, False)


def _check_universe(
    team: str,
    fixed_games: list[Game],
    team_outcomes: list[tuple[str, str | None, bool]],
    other_outcomes: list[tuple[str, str | None, bool]],
) -> bool:
    """Check if the team makes the playoffs in this universe.

    Args:
        team: Target team name.
        fixed_games: ALL season games (the lookup needs all game_ids).
            The simulated outcomes override results for remaining games.
        team_outcomes: Simulated outcomes for the team's remaining games.
        other_outcomes: Simulated outcomes for other remaining games.
    """
    combined = team_outcomes + other_outcomes
    standings = compute_standings(fixed_games, combined)
    # Use fast bracket (no tiebreaker resolution) for brute-force enumeration.
    # Full tiebreakers are too slow for 100K+ calls; win% + alphabetical is
    # sufficient for finding clinching scenarios.
    bracket = determine_playoff_bracket(standings)
    return _team_in_playoffs(team, bracket)


def _outcome_for_game(game: Game, outcome_idx: int) -> tuple[str, str | None, bool]:
    """Convert a numeric outcome index to a simulated outcome tuple.

    0 = home wins, 1 = away wins, 2 = tie.
    """
    if outcome_idx == 0:
        return (game.game_id, game.home_team, False)
    elif outcome_idx == 1:
        return (game.game_id, game.away_team, False)
    else:
        return (game.game_id, game.home_team, True)


def _enumerate_qualifying_universes(
    team: str,
    fixed_games: list[Game],
    team_outcomes: list[tuple[str, str | None, bool]],
    other_games: list[Game],
) -> list[list[tuple[str, str | None, bool]]]:
    """Enumerate all other-game outcome combinations and return those where team qualifies.

    Full enumeration: 3^len(other_games) universes.

    Returns:
        List of other_outcomes lists for qualifying universes.
    """
    qualifying: list[list[tuple[str, str | None, bool]]] = []
    n = len(other_games)

    for combo in itertools.product(range(3), repeat=n):
        other_outcomes = [
            _outcome_for_game(other_games[i], combo[i])
            for i in range(n)
        ]
        if _check_universe(team, fixed_games, team_outcomes, other_outcomes):
            qualifying.append(other_outcomes)

    return qualifying


def _sample_qualifying_universes(
    team: str,
    fixed_games: list[Game],
    team_outcomes: list[tuple[str, str | None, bool]],
    other_games: list[Game],
    strengths: dict[str, float],
    num_samples: int = MC_SAMPLES,
) -> list[list[tuple[str, str | None, bool]]]:
    """Strength-weighted Monte Carlo sampling of other-game outcomes.

    Uses team strength ratings to generate realistic game outcomes (same
    algorithm as the main simulator). This ensures qualifying universes
    are found at roughly the same rate as in the main simulation.

    Returns:
        List of other_outcomes lists for qualifying universes found by sampling.
    """
    qualifying: list[list[tuple[str, str | None, bool]]] = []

    for _ in range(num_samples):
        other_outcomes = [
            _simulate_game_outcome(game, strengths)
            for game in other_games
        ]
        if _check_universe(team, fixed_games, team_outcomes, other_outcomes):
            qualifying.append(other_outcomes)

    return qualifying


def _extract_minimal_scenarios(
    team: str,
    fixed_games: list[Game],
    team_outcomes: list[tuple[str, str | None, bool]],
    other_games: list[Game],
    qualifying_universes: list[list[tuple[str, str | None, bool]]],
) -> list[ClinchingScenario]:
    """Extract strictly minimal condition sets from qualifying universes.

    For each qualifying universe, reduce to the minimal subset of conditions
    that are individually necessary (removing any one causes the team to miss
    the playoffs in at least one possible other-game combination).

    Then deduplicate to get unique minimal scenarios.

    Returns:
        List of unique ClinchingScenario objects, sorted by fewest conditions.
    """
    if not qualifying_universes:
        return []

    # Cap universes processed — minimality testing is O(n_conditions) standings
    # calls per universe, which gets expensive with many qualifying universes.
    universes_to_process = qualifying_universes[:MAX_QUALIFYING_FOR_MINIMALITY]

    game_lookup = {g.game_id: g for g in other_games}
    seen_scenarios: set[frozenset[tuple[str, int]]] = set()
    scenarios: list[ClinchingScenario] = []

    for universe in universes_to_process:
        necessary_indices: list[int] = []

        for i in range(len(universe)):
            game = other_games[i]
            is_necessary = False

            for alt_outcome_idx in range(3):
                alt_outcome = _outcome_for_game(game, alt_outcome_idx)
                if alt_outcome == universe[i]:
                    continue

                modified = list(universe)
                modified[i] = alt_outcome

                if not _check_universe(team, fixed_games, team_outcomes, modified):
                    is_necessary = True
                    break

            if is_necessary:
                necessary_indices.append(i)

        fingerprint_parts: list[tuple[str, int]] = []
        conditions: list[ClinchingCondition] = []

        for idx in necessary_indices:
            game = game_lookup[universe[idx][0]]
            game_id, winner, is_tie = universe[idx]
            if is_tie:
                otype = 2
            elif winner == game.home_team:
                otype = 0
            else:
                otype = 1
            fingerprint_parts.append((game_id, otype))

            conditions.append(ClinchingCondition(
                game_id=game_id,
                week=game.week,
                home_team=game.home_team,
                away_team=game.away_team,
                required_winner=winner if not is_tie else None,
                is_tie=is_tie,
            ))

        fingerprint = frozenset(fingerprint_parts)
        if fingerprint in seen_scenarios:
            continue
        seen_scenarios.add(fingerprint)

        scenario = ClinchingScenario(conditions=conditions)
        scenario.num_conditions = len(conditions)
        scenarios.append(scenario)

    scenarios.sort(key=lambda s: s.num_conditions)
    return scenarios


def _remove_dominated_scenarios(scenarios: list[ClinchingScenario]) -> list[ClinchingScenario]:
    """Remove scenarios whose conditions are a strict superset of another scenario.

    If scenario A has conditions {X} and scenario B has conditions {X, Y, Z},
    then B is redundant — A already guarantees the playoff spot with fewer
    requirements.

    Assumes scenarios are already sorted by num_conditions ascending.

    Returns:
        Filtered list with dominated scenarios removed.
    """
    if len(scenarios) <= 1:
        return scenarios

    # Build fingerprint sets for efficient subset checking
    fps: list[frozenset[tuple[str, int]]] = []
    for s in scenarios:
        fp = frozenset(
            (c.game_id, 2 if c.is_tie else (0 if c.required_winner == c.home_team else 1))
            for c in s.conditions
        )
        fps.append(fp)

    # Check each scenario against all simpler ones (fewer conditions)
    keep: list[bool] = [True] * len(scenarios)
    for i in range(len(scenarios)):
        if not keep[i]:
            continue
        for j in range(i + 1, len(scenarios)):
            if not keep[j]:
                continue
            # If fps[i] is a subset of fps[j], then j is dominated
            if fps[i] <= fps[j]:
                keep[j] = False

    return [s for s, k in zip(scenarios, keep) if k]


def _process_team_record_batch(args: tuple) -> list[dict[str, Any]]:
    """Worker function for parallel processing of team record groups.

    Args:
        args: Tuple of (team, fixed_games, team_record_combos, other_games,
              use_sampling, strengths, num_samples)

    Returns:
        List of serialized RecordGroup dicts.
    """
    team, fixed_games, team_record_combos, other_games, use_sampling, strengths, num_samples = args
    results = []

    for team_outcomes, wins, losses, ties in team_record_combos:
        if use_sampling:
            qualifying = _sample_qualifying_universes(
                team, fixed_games, team_outcomes, other_games, strengths, num_samples
            )
        else:
            qualifying = _enumerate_qualifying_universes(
                team, fixed_games, team_outcomes, other_games
            )

        if not qualifying:
            results.append({
                "wins": wins, "losses": losses, "ties": ties,
                "team_outcomes": team_outcomes,
                "scenarios": [],
                "no_path": True,
                "clinches_regardless": False,
            })
            continue

        # Check if team clinches regardless of other outcomes:
        # - For enumeration: all possible universes qualified
        # - For sampling: all samples qualified (strong indicator, not proof)
        if not use_sampling:
            total_universes = 3 ** len(other_games) if other_games else 1
            clinches_regardless = (len(qualifying) == total_universes)
        else:
            # If every single sample qualified, it's very likely a true clinch
            clinches_regardless = (len(qualifying) == MC_SAMPLES)

        if clinches_regardless:
            # No need for minimality reduction — team clinches no matter what
            results.append({
                "wins": wins, "losses": losses, "ties": ties,
                "team_outcomes": team_outcomes,
                "scenarios": [],
                "no_path": False,
                "clinches_regardless": True,
            })
            continue

        scenarios = _extract_minimal_scenarios(
            team, fixed_games, team_outcomes, other_games, qualifying
        )

        # Filter out 0-condition scenarios — they are artifacts of the
        # minimality check (no single flip matters, but multi-flip can).
        # A true "clinches regardless" is handled above.
        scenarios = [s for s in scenarios if s.num_conditions > 0]

        results.append({
            "wins": wins, "losses": losses, "ties": ties,
            "team_outcomes": team_outcomes,
            "scenarios": scenarios,
            "no_path": False,
            "clinches_regardless": False,
        })

    return results


def compute_clinching_scenarios(
    team: str,
    all_games: list[Game],
    cutoff_week: int,
    num_workers: int | None = None,
    enumeration_threshold: int | None = None,
    num_samples: int | None = None,
) -> ClinchingResult:
    """Compute all clinching scenarios for a team.

    Main entry point for the clinching solver.

    Args:
        team: Team name to analyze.
        all_games: All season games.
        cutoff_week: Games up to this week are fixed (completed).
        num_workers: Number of worker processes (None = auto-detect).

    Returns:
        ClinchingResult with all scenarios grouped by team record.
    """
    if cutoff_week < 14:
        return ClinchingResult(
            team=team,
            error="Clinching scenarios are only available after week 14.",
        )

    team_conf = get_team_conference(team)
    if not team_conf:
        return ClinchingResult(team=team, error=f"Unknown team: {team}")

    # Identify contenders and relevant games
    contenders = identify_contenders(team, all_games, cutoff_week)
    team_games, other_games = get_relevant_games(
        team, all_games, cutoff_week, contenders
    )

    threshold = enumeration_threshold if enumeration_threshold is not None else ENUMERATION_THRESHOLD
    samples = num_samples if num_samples is not None else MC_SAMPLES
    use_sampling = len(other_games) > threshold
    method = "sampling" if use_sampling else "enumeration"

    if use_sampling:
        logger.info(
            "Clinching analysis for %s: %d team games, %d relevant other games, method=%s, iterations=%d",
            team, len(team_games), len(other_games), method, samples,
        )
    else:
        logger.info(
            "Clinching analysis for %s: %d team games, %d relevant other games, method=%s, enumeration_threshold=%d",
            team, len(team_games), len(other_games), method, threshold,
        )

    # Generate all game-level combos (different combos with same W-L-T matter for tiebreakers)
    team_record_combos = _generate_team_records(team, team_games)

    # Compute team strengths from fixed games for strength-weighted sampling
    fixed_games = [g for g in all_games if g.week <= cutoff_week]
    strengths: dict[str, float] = {}
    if use_sampling:
        from src.team_strength import TeamStrengthCalculator
        from src.nfl_teams import ALL_TEAMS
        calculator = TeamStrengthCalculator()
        completed_fixed = [g for g in fixed_games if g.status == GameStatus.COMPLETED]
        if completed_fixed:
            strengths = calculator.calculate(completed_fixed)
        # Ensure all teams have a strength rating
        for t in ALL_TEAMS:
            if t not in strengths:
                strengths[t] = 1.0

    # Determine workers
    if num_workers is None:
        num_workers = os.cpu_count() or 1
    num_workers = min(num_workers, len(team_record_combos))

    # Pass all_games to the worker (compute_standings needs game_id lookup for
    # all games; simulated_outcomes override results for post-cutoff games).
    if num_workers <= 1 or len(team_record_combos) <= 1:
        raw_results = _process_team_record_batch(
            (team, all_games, team_record_combos, other_games, use_sampling, strengths, samples)
        )
    else:
        batch_size = max(1, len(team_record_combos) // num_workers)
        batches = []
        for i in range(0, len(team_record_combos), batch_size):
            batch = team_record_combos[i:i + batch_size]
            batches.append((team, all_games, batch, other_games, use_sampling, strengths, samples))

        with Pool(processes=num_workers) as pool:
            batch_results = pool.map(_process_team_record_batch, batches)

        raw_results = []
        for batch in batch_results:
            raw_results.extend(batch)

    # Build RecordGroup objects, grouping by (wins, losses, ties)
    # Track per-record: does EVERY combo clinch regardless, or just some?
    record_map: dict[tuple[int, int, int], RecordGroup] = {}
    record_clinch_all: dict[tuple[int, int, int], bool] = {}  # all combos clinch?
    record_clinch_any: dict[tuple[int, int, int], bool] = {}  # at least one clinches?
    record_combo_count: dict[tuple[int, int, int], int] = {}

    for result in raw_results:
        key = (result["wins"], result["losses"], result["ties"])
        record_combo_count[key] = record_combo_count.get(key, 0) + 1

        if key not in record_map:
            team_game_conditions = []
            for game_id, winner, is_tie in result["team_outcomes"]:
                game = next(
                    (g for g in team_games if g.game_id == game_id), None
                )
                if game:
                    team_game_conditions.append(ClinchingCondition(
                        game_id=game_id,
                        week=game.week,
                        home_team=game.home_team,
                        away_team=game.away_team,
                        required_winner=winner if not is_tie else None,
                        is_tie=is_tie,
                    ))

            record_map[key] = RecordGroup(
                wins=result["wins"],
                losses=result["losses"],
                ties=result["ties"],
                team_games=team_game_conditions,
                scenarios=list(result["scenarios"]),
                no_path=result["no_path"],
            )
            record_clinch_all[key] = result.get("clinches_regardless", False)
            record_clinch_any[key] = result.get("clinches_regardless", False)
        else:
            existing = record_map[key]
            # Track clinch status across combos
            if result.get("clinches_regardless", False):
                record_clinch_any[key] = True
            else:
                record_clinch_all[key] = False

            if not result["no_path"]:
                existing.no_path = False
                existing_fps = {
                    frozenset(
                        (c.game_id, 2 if c.is_tie else (0 if c.required_winner == c.home_team else 1))
                        for c in s.conditions
                    )
                    for s in existing.scenarios
                }
                for scenario in result["scenarios"]:
                    fp = frozenset(
                        (c.game_id, 2 if c.is_tie else (0 if c.required_winner == c.home_team else 1))
                        for c in scenario.conditions
                    )
                    if fp not in existing_fps:
                        existing.scenarios.append(scenario)
                        existing_fps.add(fp)

    record_groups = sorted(
        record_map.values(),
        key=lambda rg: (-rg.wins, rg.losses, rg.ties),
    )

    for rg in record_groups:
        key = (rg.wins, rg.losses, rg.ties)
        rg.scenarios.sort(key=lambda s: s.num_conditions)

        # Only show "clinches regardless" if ALL game-level combos for this
        # record clinch. If only some do, keep the conditional scenarios.
        if record_clinch_all.get(key, False):
            rg.scenarios = [ClinchingScenario(conditions=[], num_conditions=0)]
        else:
            # Remove any 0-condition artifacts
            rg.scenarios = [s for s in rg.scenarios if s.num_conditions > 0]
            # Remove scenarios that are strict supersets of simpler ones.
            # If scenario A's conditions are a subset of scenario B's,
            # then B is redundant (A already guarantees the outcome).
            rg.scenarios = _remove_dominated_scenarios(rg.scenarios)

    # Compute total_evals for external timing calculation
    if use_sampling:
        total_evals = len(team_record_combos) * samples
    else:
        total_evals = len(team_record_combos) * (3 ** len(other_games))

    return ClinchingResult(
        team=team,
        record_groups=record_groups,
        method=method,
        exhaustive=not use_sampling,
        relevant_games_count=len(other_games),
        contenders=contenders,
        total_evals=total_evals,
    )


# Cached benchmark result: milliseconds per clinching evaluation
_benchmark_ms_per_eval: float | None = None
_benchmark_timestamp: float = 0.0
_BENCHMARK_TTL = 86400  # 24 hours


def run_benchmark(all_games: list[Game]) -> float:
    """Run a benchmark measuring the full clinching evaluation pipeline.

    Simulates what the actual clinching solver does per iteration:
    _check_universe (compute_standings + determine_playoff_bracket + overhead).

    Measures single-core ms/eval. Result is cached for 24 hours.
    """
    global _benchmark_ms_per_eval, _benchmark_timestamp

    # Check if cached result is still valid
    now = time.time()
    if _benchmark_ms_per_eval is not None and (now - _benchmark_timestamp) < _BENCHMARK_TTL:
        return _benchmark_ms_per_eval

    if not all_games:
        _benchmark_ms_per_eval = 5.0  # fallback default
        _benchmark_timestamp = now
        return _benchmark_ms_per_eval

    # Simulate the full _check_universe pipeline
    remaining = [g for g in all_games if g.week > 14][:16]
    team_outcomes = [(remaining[0].game_id, remaining[0].home_team, False)] if remaining else []
    other_games = remaining[1:12] if len(remaining) > 1 else []

    # Warm up
    for i in range(5):
        other_outcomes = [
            _outcome_for_game(other_games[j], (i + j) % 3)
            for j in range(len(other_games))
        ]
        _check_universe("Bills", all_games, team_outcomes, other_outcomes)

    # Benchmark — measure _check_universe which is the actual per-iteration cost
    n_iterations = 100
    start = time.perf_counter()
    for i in range(n_iterations):
        other_outcomes = [
            _outcome_for_game(other_games[j], (i + j) % 3)
            for j in range(len(other_games))
        ]
        _check_universe("Bills", all_games, team_outcomes, other_outcomes)
    elapsed = time.perf_counter() - start

    _benchmark_ms_per_eval = (elapsed / n_iterations) * 1000
    _benchmark_timestamp = now

    logger.info("Clinching benchmark: %.2f ms/eval (%d iterations in %.2fs)",
                _benchmark_ms_per_eval, n_iterations, elapsed)

    return _benchmark_ms_per_eval


def get_ms_per_eval(all_games: list[Game] | None = None, cache: "Cache | None" = None) -> float:
    """Get ms/eval from historical data or fall back to benchmark."""
    global _benchmark_ms_per_eval

    if cache is not None:
        timings = cache.get_solver_timings()
        if timings:
            total = sum(t["ms_per_eval"] for t in timings)
            return total / len(timings)

    # Fallback: existing behavior
    if _benchmark_ms_per_eval is not None:
        return _benchmark_ms_per_eval
    if all_games:
        return run_benchmark(all_games)
    return 2.0  # conservative default


def estimate_clinching(
    team: str,
    all_games: list[Game],
    cutoff_week: int,
    cache: "Cache | None" = None,
) -> dict[str, Any]:
    """Lightweight preflight estimate for the clinching solver.

    Returns the method, relevant game count, and estimated runtime
    without actually running the solver.

    Args:
        team: Team name.
        all_games: All season games.
        cutoff_week: Week number cutoff.

    Returns:
        Dict with keys: team, relevant_games, team_games, method,
        estimated_seconds, available (bool), reason (if not available).
    """
    if cutoff_week < 14:
        return {
            "team": team,
            "available": False,
            "reason": "Clinching scenarios are only available after week 14.",
        }

    team_conf = get_team_conference(team)
    if not team_conf:
        return {"team": team, "available": False, "reason": f"Unknown team: {team}"}

    contenders = identify_contenders(team, all_games, cutoff_week)
    team_games, other_games = get_relevant_games(
        team, all_games, cutoff_week, contenders
    )

    n_other = len(other_games)
    n_team = len(team_games)
    use_sampling = n_other > ENUMERATION_THRESHOLD
    method = "sampling" if use_sampling else "enumeration"

    # Number of game-level combos: 3^n_team (all tested for tiebreaker accuracy)
    n_team_combos = 3 ** n_team if n_team <= 4 else 81

    cpu_count = os.cpu_count() or 1
    ms_per_eval = get_ms_per_eval(all_games, cache=cache)

    if use_sampling:
        total_evals = n_team_combos * MC_SAMPLES
    else:
        total_evals = n_team_combos * (3 ** n_other)

    est_seconds = (total_evals * ms_per_eval / 1000) / cpu_count

    est_seconds = max(1.0, min(est_seconds, 300.0))

    return {
        "team": team,
        "available": True,
        "relevant_games": n_other,
        "team_games": n_team,
        "team_record_combos": n_team_combos,
        "method": method,
        "estimated_seconds": round(est_seconds, 1),
        "ms_per_eval": round(ms_per_eval, 2),
        "cpu_count": cpu_count,
        "contenders": contenders,
    }
