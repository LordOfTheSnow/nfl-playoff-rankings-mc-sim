"""CP-SAT based clinching/elimination solver.

Uses Google OR-Tools CP-SAT to determine whether an NFL team has
mathematically clinched or been eliminated from playoff contention.

The solver uses a hybrid strategy:
1. CP-SAT constrains the arithmetic: win/loss/tie counts, record bounds,
   and simple dominance relationships.
2. For each candidate record assignment that passes CP-SAT filtering, the
   existing standings engine (with full tiebreaker logic) determines the
   actual playoff bracket.
3. This avoids encoding ~11 tiebreaker steps as constraints while still
   leveraging CP-SAT's propagation to prune impossible record combinations.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from multiprocessing import Pool
from typing import Any

from src.data_client import Game, GameStatus
from src.nfl_teams import ALL_TEAMS, get_team_conference
from src.standings import compute_standings, determine_playoff_bracket

logger = logging.getLogger(__name__)

# OR-Tools import guard: the package is an optional dependency.
# All non-CP-solver endpoints remain operational when ortools is not installed.
try:
    from ortools.sat.python import cp_model  # noqa: F401

    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False


class ClinchStatus(Enum):
    """Clinch/elimination status for a team."""

    CLINCHED = "clinched"
    ELIMINATED = "eliminated"
    ALIVE = "alive"
    INCONCLUSIVE = "inconclusive"


@dataclass
class CPSolverResult:
    """Result from the CP solver for a single team.

    Attributes:
        team: Team name.
        status: Clinch/elimination status.
        clinched: True if team has clinched a playoff spot.
        eliminated: True if team is eliminated from contention.
        exhaustive: True if the solver completed all record groups.
        solve_time_ms: Wall-clock solve time in milliseconds.
        num_variables: Number of CP-SAT variables in the model.
        minimum_seed: Minimum possible seed (1-7) if clinched, None otherwise.
        magic_number: Wins needed to clinch (if alive and derivable), None otherwise.
        error: Error message if solver timed out or failed, None otherwise.
        record_groups_completed: How many record groups were fully processed.
        record_groups_total: Total number of record groups to process.
    """

    team: str
    status: ClinchStatus = ClinchStatus.ALIVE
    clinched: bool = False
    eliminated: bool = False
    exhaustive: bool = True
    solve_time_ms: int = 0
    num_variables: int = 0
    minimum_seed: int | None = None
    magic_number: int | None = None
    error: str | None = None
    record_groups_completed: int = 0
    record_groups_total: int = 0


@dataclass
class CPSolverConfig:
    """Configuration for the CP solver.

    Attributes:
        time_limit: Maximum wall-clock seconds for the solver (1-300).
        enumeration_threshold: Max remaining games for exhaustive search.
    """

    time_limit: int = 30
    enumeration_threshold: int = 13


# Valid team names set for O(1) lookup
_VALID_TEAMS: frozenset[str] = frozenset(ALL_TEAMS)


def _generate_record_bounds(
    team: str,
    team_remaining_games: list[Game],
    fixed_wins: int,
    fixed_losses: int,
    fixed_ties: int,
) -> list[tuple[int, int, int]]:
    """Generate all possible (total_wins, total_losses, total_ties) records.

    Enumerates every valid (wins_added, losses_added, ties_added) distribution
    from the team's remaining games where wins_added + losses_added + ties_added = N,
    then adds each to the fixed record to produce total records.

    With N remaining games, produces (N+1)(N+2)/2 distinct records.

    Args:
        team: Team name (used for logging/debugging context).
        team_remaining_games: Games in weeks > cutoff_week where the team
            participates (as home or away).
        fixed_wins: Wins from games in weeks <= cutoff_week.
        fixed_losses: Losses from games in weeks <= cutoff_week.
        fixed_ties: Ties from games in weeks <= cutoff_week.

    Returns:
        List of (wins, losses, ties) tuples representing all possible
        final records for the team.
    """
    n = len(team_remaining_games)
    records: list[tuple[int, int, int]] = []

    for wins_added in range(n + 1):
        for losses_added in range(n - wins_added + 1):
            ties_added = n - wins_added - losses_added
            records.append((
                fixed_wins + wins_added,
                fixed_losses + losses_added,
                fixed_ties + ties_added,
            ))

    return records


def _build_cpsat_model(
    team: str,
    conference: str,
    target_record: tuple[int, int, int],
    all_games: list[Game],
    remaining_games: list[Game],
    fixed_standings: dict[str, tuple[int, int, int]],
    contenders: list[str],
) -> tuple[Any, dict[str, Any], dict[str, tuple[Any, Any, Any]]]:
    """Build a CP-SAT model for the given target record.

    Creates integer variables for each remaining game outcome and links
    them to per-team win/loss/tie totals via Boolean decomposition.

    Variables:
    - One IntVar per remaining game with domain {0, 1, 2}
      (0=home_win, 1=away_win, 2=tie)
    - BoolVars for decomposing each game outcome into win/loss/tie indicators
    - IntVars for each contender team's total wins, losses, ties

    Constraints:
    - Win/loss/tie arithmetic: team_wins = fixed_wins + sum(game_outcomes where team wins)
    - Record consistency: W + L + T = 17 for each team
    - Target team record: force target team's record to the specified values
    - Simple dominance bounds: if a team can't reach 7th place by wins alone, prune

    Args:
        team: Target team name.
        conference: Conference of the target team ("AFC" or "NFC").
        target_record: (wins, losses, ties) to force for the target team.
        all_games: All season games.
        remaining_games: Games in weeks > cutoff (outcomes to be decided).
        fixed_standings: Dict mapping team name to (wins, losses, ties) from
            games in weeks <= cutoff.
        contenders: List of same-conference team names to model (includes
            target team).

    Returns:
        Tuple of (model, game_outcome_vars, team_record_vars) where:
        - model: The CpModel instance with all constraints added.
        - game_outcome_vars: Dict mapping game_id to the IntVar for that game.
        - team_record_vars: Dict mapping team name to (wins_var, losses_var, ties_var).
    """
    if not ORTOOLS_AVAILABLE:
        raise RuntimeError("OR-Tools is not installed.")

    model = cp_model.CpModel()

    # --- Game outcome variables ---
    # One IntVar per remaining game: 0=home_win, 1=away_win, 2=tie
    game_outcome_vars: dict[str, Any] = {}
    for game in remaining_games:
        var = model.new_int_var(0, 2, f"game_{game.game_id}")
        game_outcome_vars[game.game_id] = var

    # --- Boolean decomposition for each game ---
    # For each game, create 3 BoolVars: home_wins, away_wins, is_tie
    # These are linked to the outcome IntVar via channeling constraints.
    game_home_wins: dict[str, Any] = {}
    game_away_wins: dict[str, Any] = {}
    game_ties: dict[str, Any] = {}

    for game in remaining_games:
        gid = game.game_id
        outcome_var = game_outcome_vars[gid]

        hw = model.new_bool_var(f"hw_{gid}")
        aw = model.new_bool_var(f"aw_{gid}")
        tie = model.new_bool_var(f"tie_{gid}")

        # Exactly one of the three outcomes must be true
        model.add(hw + aw + tie == 1)

        # Channel: outcome_var == 0 iff home wins
        model.add(outcome_var == 0).only_enforce_if(hw)
        model.add(outcome_var != 0).only_enforce_if(hw.negated())

        # Channel: outcome_var == 1 iff away wins
        model.add(outcome_var == 1).only_enforce_if(aw)
        model.add(outcome_var != 1).only_enforce_if(aw.negated())

        # Channel: outcome_var == 2 iff tie
        model.add(outcome_var == 2).only_enforce_if(tie)
        model.add(outcome_var != 2).only_enforce_if(tie.negated())

        game_home_wins[gid] = hw
        game_away_wins[gid] = aw
        game_ties[gid] = tie

    # --- Build per-team game participation indices ---
    # For each contender, find remaining games where they are home or away
    contenders_set = set(contenders)
    team_home_games: dict[str, list[str]] = {t: [] for t in contenders}
    team_away_games: dict[str, list[str]] = {t: [] for t in contenders}

    for game in remaining_games:
        if game.home_team in contenders_set:
            team_home_games[game.home_team].append(game.game_id)
        if game.away_team in contenders_set:
            team_away_games[game.away_team].append(game.game_id)

    # --- Team record variables and arithmetic constraints ---
    team_record_vars: dict[str, tuple[Any, Any, Any]] = {}

    # Total games per team in the full season = 17
    total_season_games = 17

    for t in contenders:
        fw, fl, ft = fixed_standings.get(t, (0, 0, 0))

        # Count remaining games for this team
        remaining_home_gids = team_home_games[t]
        remaining_away_gids = team_away_games[t]
        n_remaining = len(remaining_home_gids) + len(remaining_away_gids)

        # Upper bounds for total record
        max_wins = fw + n_remaining
        max_losses = fl + n_remaining
        max_ties = ft + n_remaining

        # Create IntVars for total wins, losses, ties
        wins_var = model.new_int_var(fw, max_wins, f"wins_{t}")
        losses_var = model.new_int_var(fl, max_losses, f"losses_{t}")
        ties_var = model.new_int_var(ft, max_ties, f"ties_{t}")

        # Wins = fixed_wins + games where team wins
        # Team wins when: home and outcome==0, or away and outcome==1
        win_bools: list[Any] = []
        for gid in remaining_home_gids:
            win_bools.append(game_home_wins[gid])
        for gid in remaining_away_gids:
            win_bools.append(game_away_wins[gid])

        if win_bools:
            model.add(wins_var == fw + sum(win_bools))
        else:
            model.add(wins_var == fw)

        # Losses = fixed_losses + games where team loses
        # Team loses when: home and outcome==1, or away and outcome==0
        loss_bools: list[Any] = []
        for gid in remaining_home_gids:
            loss_bools.append(game_away_wins[gid])
        for gid in remaining_away_gids:
            loss_bools.append(game_home_wins[gid])

        if loss_bools:
            model.add(losses_var == fl + sum(loss_bools))
        else:
            model.add(losses_var == fl)

        # Ties = fixed_ties + games where team participates and result is tie
        tie_bools: list[Any] = []
        for gid in remaining_home_gids:
            tie_bools.append(game_ties[gid])
        for gid in remaining_away_gids:
            tie_bools.append(game_ties[gid])

        if tie_bools:
            model.add(ties_var == ft + sum(tie_bools))
        else:
            model.add(ties_var == ft)

        # W + L + T = 17 for every team
        model.add(wins_var + losses_var + ties_var == total_season_games)

        team_record_vars[t] = (wins_var, losses_var, ties_var)

    # --- Force target team's record to the specified target_record ---
    if team in team_record_vars:
        target_w, target_l, target_t = target_record
        tw_var, tl_var, tt_var = team_record_vars[team]
        model.add(tw_var == target_w)
        model.add(tl_var == target_l)
        model.add(tt_var == target_t)

    # --- Simple dominance bounds: prune teams that can't reach 7th place ---
    # Compute minimum possible wins for each contender (just their fixed wins)
    # and maximum possible wins (fixed_wins + remaining_games for that team).
    # If a team's max wins is less than the 7th-highest min wins, they cannot
    # possibly finish 7th, so we can add an upper bound on their wins that
    # tightens the model.
    min_wins_list: list[tuple[str, int]] = []
    max_wins_map: dict[str, int] = {}

    for t in contenders:
        fw, fl, ft_val = fixed_standings.get(t, (0, 0, 0))
        n_remaining = len(team_home_games[t]) + len(team_away_games[t])
        min_wins_list.append((t, fw))
        max_wins_map[t] = fw + n_remaining

    # Sort by min_wins descending to find the 7th-highest
    min_wins_list.sort(key=lambda x: -x[1])

    if len(min_wins_list) >= 7:
        seventh_min_wins = min_wins_list[6][1]

        # For any team whose max possible wins < seventh_min_wins,
        # they cannot possibly reach 7th place. We can tighten the model
        # by adding a constraint that eliminates impossible branches early.
        for t in contenders:
            if max_wins_map[t] < seventh_min_wins and t in team_record_vars:
                # This team cannot possibly finish in the top 7 by wins alone.
                # Add an explicit upper bound on their wins var (already limited
                # by domain, but adding it as a constraint helps propagation).
                tw_var, _, _ = team_record_vars[t]
                model.add(tw_var <= max_wins_map[t])

    return (model, game_outcome_vars, team_record_vars)


class PlayoffValidator(cp_model.CpSolverSolutionCallback):
    """CP-SAT solution callback that validates playoff brackets.

    For each feasible assignment found by CP-SAT, this callback:
    1. Extracts the game outcomes from variable assignments
    2. Calls compute_standings + determine_playoff_bracket
    3. Checks if the target team is in/out of the bracket
    4. Records the result for the solver's final determination
    """

    def __init__(
        self,
        team: str,
        all_games: list[Game],
        remaining_games: list[Game],
        game_outcome_vars: dict[str, Any],
        search_for_miss: bool,
    ) -> None:
        """Initialize the PlayoffValidator callback.

        Args:
            team: Target team name.
            all_games: All games in the season (the complete list, so we
                can build full standings).
            remaining_games: The remaining games (whose outcomes we're varying).
            game_outcome_vars: Dict mapping game_id to CP-SAT IntVar.
            search_for_miss: If True, we're looking for an assignment where
                team MISSES playoffs (clinch check). If False, looking for
                team MAKES playoffs (elimination check).
        """
        super().__init__()
        self._team = team
        self._all_games = all_games
        self._remaining_games = remaining_games
        self._game_outcome_vars = game_outcome_vars
        self._search_for_miss = search_for_miss
        self._conference = get_team_conference(team)

        # Build lookup from game_id to Game for remaining games
        self._remaining_game_lookup: dict[str, Game] = {
            g.game_id: g for g in remaining_games
        }

        # Result: whether a witness/counter-example was found
        self.found: bool = False

    def on_solution_callback(self) -> None:
        """Called by CP-SAT for each feasible solution.

        Extracts game outcomes, builds standings, checks playoff bracket,
        and stops search if the desired condition is met.
        """
        try:
            # Build simulated outcomes from CP-SAT variable assignments
            simulated_outcomes: list[tuple[str, str | None, bool]] = []

            for game_id, var in self._game_outcome_vars.items():
                outcome_value = self.value(var)
                game = self._remaining_game_lookup[game_id]

                if outcome_value == 0:
                    # Home win
                    simulated_outcomes.append(
                        (game_id, game.home_team, False)
                    )
                elif outcome_value == 1:
                    # Away win
                    simulated_outcomes.append(
                        (game_id, game.away_team, False)
                    )
                elif outcome_value == 2:
                    # Tie — winning_team can be either; is_tie=True
                    simulated_outcomes.append(
                        (game_id, game.home_team, True)
                    )

            # Compute standings with these simulated outcomes
            standings = compute_standings(
                self._all_games, simulated_outcomes=simulated_outcomes
            )

            # Determine the playoff bracket with simulated outcomes for tiebreaker
            bracket = determine_playoff_bracket(
                standings,
                all_games=self._all_games,
                simulated_game_ids=set(gid for gid, _, _ in simulated_outcomes),
                simulated_outcomes=simulated_outcomes,
            )

            # Get the seeds for the target team's conference
            if self._conference == "AFC":
                conference_seeds = bracket.afc_seeds
            else:
                conference_seeds = bracket.nfc_seeds

            # Check if the target team is in the bracket
            team_in_bracket = any(
                s.team == self._team for s in conference_seeds
            )

            if self._search_for_miss and not team_in_bracket:
                # Clinch check: found an assignment where team misses playoffs
                self.found = True
                self.stop_search()
            elif not self._search_for_miss and team_in_bracket:
                # Elimination check: found an assignment where team makes playoffs
                self.found = True
                self.stop_search()

        except Exception as e:
            # Handle exceptions from the standings engine gracefully —
            # log the error and continue searching
            logger.warning(
                "PlayoffValidator: standings engine raised an exception "
                "for team '%s': %s",
                self._team,
                e,
            )


def solve_clinch(
    team: str,
    all_games: list[Game],
    cutoff_week: int,
    config: CPSolverConfig | None = None,
) -> CPSolverResult:
    """Determine clinch/elimination status for a team.

    Main entry point. Models remaining games as CP-SAT variables,
    uses constraint propagation to prune impossible record combinations,
    and delegates tiebreaker resolution to the standings engine.

    Args:
        team: Team name to analyze (must be a valid NFL team name).
        all_games: All season games (list of Game objects).
        cutoff_week: Games in weeks <= cutoff are fixed. Must be 1-18.
        config: Solver configuration (uses defaults if None).

    Returns:
        CPSolverResult with clinch/elimination determination.

    Raises:
        RuntimeError: If OR-Tools is not installed.
    """
    from src.clinching import identify_contenders, get_relevant_games

    if not ORTOOLS_AVAILABLE:
        raise RuntimeError(
            "OR-Tools is not installed. Install with: pip install ortools>=9.9"
        )

    if config is None:
        config = CPSolverConfig()

    # Validate team name
    if team not in _VALID_TEAMS:
        return CPSolverResult(
            team=team,
            status=ClinchStatus.ALIVE,
            error=f"Unknown team: '{team}'. Valid teams: {sorted(_VALID_TEAMS)}",
        )

    # Validate cutoff_week (must be 1-18)
    if not isinstance(cutoff_week, int) or cutoff_week < 1 or cutoff_week > 18:
        return CPSolverResult(
            team=team,
            status=ClinchStatus.ALIVE,
            error=f"cutoff_week must be between 1 and 18, got: {cutoff_week}",
        )

    # Validate time_limit (must be 1-300)
    if (
        not isinstance(config.time_limit, int)
        or config.time_limit < 1
        or config.time_limit > 300
    ):
        return CPSolverResult(
            team=team,
            status=ClinchStatus.ALIVE,
            error=f"time_limit must be between 1 and 300 seconds, got: {config.time_limit}",
        )

    start_time = time.perf_counter()

    # --- Step 1: Partition games ---
    conference = get_team_conference(team)
    if not conference:
        return CPSolverResult(
            team=team,
            status=ClinchStatus.ALIVE,
            error=f"Could not determine conference for team: {team}",
        )

    contenders = identify_contenders(team, all_games, cutoff_week)
    # Include the target team in the contenders list for model building
    all_contenders = [team] + [t for t in contenders if t != team]

    team_remaining_games, relevant_other_games = get_relevant_games(
        team, all_games, cutoff_week, contenders
    )
    # All remaining conference games (team's + others')
    remaining_games = team_remaining_games + relevant_other_games

    # --- Step 2: Compute fixed standings ---
    # Tally W-L-T for each contender from games in weeks <= cutoff_week
    fixed_standings: dict[str, tuple[int, int, int]] = {}
    for t in all_contenders:
        wins, losses, ties = 0, 0, 0
        for game in all_games:
            if game.week > cutoff_week:
                continue
            if game.home_team != t and game.away_team != t:
                continue
            # Determine outcome from scores (treat games without scores as not
            # contributing)
            if game.home_score is not None and game.away_score is not None:
                if game.home_score > game.away_score:
                    if game.home_team == t:
                        wins += 1
                    else:
                        losses += 1
                elif game.away_score > game.home_score:
                    if game.away_team == t:
                        wins += 1
                    else:
                        losses += 1
                else:
                    ties += 1
            elif game.status == GameStatus.COMPLETED:
                # Completed but no scores — treat as a tie for safety
                ties += 1
        fixed_standings[t] = (wins, losses, ties)

    # --- Step 3: Get target team's fixed record ---
    fixed_wins, fixed_losses, fixed_ties = fixed_standings.get(team, (0, 0, 0))

    # --- Step 4: Generate record groups ---
    record_groups = _generate_record_bounds(
        team, team_remaining_games, fixed_wins, fixed_losses, fixed_ties
    )
    record_groups_total = len(record_groups)

    # Track metadata
    num_variables = 0
    record_groups_completed = 0

    # --- Step 5: Elimination check first (early termination) ---
    # For each record group (sorted by wins descending — most likely to make
    # playoffs first), search for an assignment where the team MAKES playoffs.
    # If found for ANY record group → team is NOT eliminated.
    elim_groups_sorted = sorted(record_groups, key=lambda r: -r[0])

    team_not_eliminated = False
    elim_groups_completed = 0

    for target_record in elim_groups_sorted:
        # Check time limit
        elapsed = time.perf_counter() - start_time
        if elapsed >= config.time_limit:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return CPSolverResult(
                team=team,
                status=ClinchStatus.INCONCLUSIVE,
                exhaustive=False,
                solve_time_ms=elapsed_ms,
                num_variables=num_variables,
                error=(
                    f"Timed out after {int(elapsed)}s: "
                    f"{elim_groups_completed}/{record_groups_total} "
                    f"record groups completed"
                ),
                record_groups_completed=elim_groups_completed,
                record_groups_total=record_groups_total,
            )

        # Build model for this record group
        model, game_outcome_vars, team_record_vars = _build_cpsat_model(
            team=team,
            conference=conference,
            target_record=target_record,
            all_games=all_games,
            remaining_games=remaining_games,
            fixed_standings=fixed_standings,
            contenders=all_contenders,
        )

        # Track number of variables (use first model's count)
        if num_variables == 0:
            num_variables = len(game_outcome_vars)

        # Create validator: search_for_miss=False → looking for team making playoffs
        validator = PlayoffValidator(
            team=team,
            all_games=all_games,
            remaining_games=remaining_games,
            game_outcome_vars=game_outcome_vars,
            search_for_miss=False,
        )

        # Run the solver — enumerate solutions so callback can find witness
        solver = cp_model.CpSolver()
        solver.parameters.enumerate_all_solutions = True
        remaining_time = config.time_limit - (time.perf_counter() - start_time)
        remaining_groups = record_groups_total - elim_groups_completed
        if remaining_groups > 0 and remaining_time > 0:
            solver.parameters.max_time_in_seconds = remaining_time / remaining_groups
        else:
            solver.parameters.max_time_in_seconds = 1.0

        solver.solve(model, validator)
        elim_groups_completed += 1

        if validator.found:
            # Team CAN make playoffs for this record → NOT eliminated
            team_not_eliminated = True
            break

    # If team cannot make playoffs for ANY record group → ELIMINATED
    if not team_not_eliminated:
        # Check if we completed all groups or timed out
        elapsed = time.perf_counter() - start_time
        if elim_groups_completed < record_groups_total and elapsed >= config.time_limit:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return CPSolverResult(
                team=team,
                status=ClinchStatus.INCONCLUSIVE,
                exhaustive=False,
                solve_time_ms=elapsed_ms,
                num_variables=num_variables,
                error=(
                    f"Timed out after {int(elapsed)}s: "
                    f"{elim_groups_completed}/{record_groups_total} "
                    f"record groups completed"
                ),
                record_groups_completed=elim_groups_completed,
                record_groups_total=record_groups_total,
            )
        # All groups processed, no assignment found where team makes playoffs
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return CPSolverResult(
            team=team,
            status=ClinchStatus.ELIMINATED,
            clinched=False,
            eliminated=True,
            exhaustive=True,
            solve_time_ms=elapsed_ms,
            num_variables=num_variables,
            record_groups_completed=record_groups_total,
            record_groups_total=record_groups_total,
        )

    # --- Step 6: Clinch check ---
    # For each record group (sorted by wins ascending — most likely to miss
    # playoffs first), search for an assignment where team MISSES playoffs.
    # If found for ANY record group → team is NOT clinched.
    clinch_groups_sorted = sorted(record_groups, key=lambda r: r[0])

    team_not_clinched = False
    clinch_groups_completed = 0
    # Track which record groups (by wins level) are clinched for magic number
    clinch_results_by_wins: dict[int, bool] = {}  # wins → True if clinched at that level

    for target_record in clinch_groups_sorted:
        # Check time limit
        elapsed = time.perf_counter() - start_time
        if elapsed >= config.time_limit:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            total_completed = elim_groups_completed + clinch_groups_completed
            return CPSolverResult(
                team=team,
                status=ClinchStatus.INCONCLUSIVE,
                exhaustive=False,
                solve_time_ms=elapsed_ms,
                num_variables=num_variables,
                error=(
                    f"Timed out after {int(elapsed)}s: "
                    f"{total_completed}/{record_groups_total * 2} "
                    f"record groups completed"
                ),
                record_groups_completed=clinch_groups_completed,
                record_groups_total=record_groups_total,
            )

        # Build model for this record group
        model, game_outcome_vars, team_record_vars = _build_cpsat_model(
            team=team,
            conference=conference,
            target_record=target_record,
            all_games=all_games,
            remaining_games=remaining_games,
            fixed_standings=fixed_standings,
            contenders=all_contenders,
        )

        # Create validator: search_for_miss=True → looking for team missing playoffs
        validator = PlayoffValidator(
            team=team,
            all_games=all_games,
            remaining_games=remaining_games,
            game_outcome_vars=game_outcome_vars,
            search_for_miss=True,
        )

        # Run the solver — enumerate solutions so callback can find counter-example.
        # Uses randomized search to diversify exploration and find witnesses faster.
        solver = cp_model.CpSolver()
        solver.parameters.enumerate_all_solutions = True
        solver.parameters.random_seed = clinch_groups_completed
        remaining_time = config.time_limit - (time.perf_counter() - start_time)
        remaining_groups = record_groups_total - clinch_groups_completed
        per_group_time = remaining_time / remaining_groups if remaining_groups > 0 and remaining_time > 0 else 1.0
        solver.parameters.max_time_in_seconds = per_group_time

        solver.solve(model, validator)
        clinch_groups_completed += 1

        target_wins = target_record[0]
        if validator.found:
            # Team CAN miss playoffs for this record → NOT clinched
            team_not_clinched = True
            clinch_results_by_wins[target_wins] = False
            # Can skip remaining groups for clinch — we know team is not clinched
            break
        else:
            # No assignment where team misses for this record → clinched at this level
            clinch_results_by_wins[target_wins] = True

    # --- Step 7: Check if timed out during clinch check ---
    elapsed = time.perf_counter() - start_time
    if not team_not_clinched and clinch_groups_completed < record_groups_total:
        if elapsed >= config.time_limit:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            total_completed = elim_groups_completed + clinch_groups_completed
            return CPSolverResult(
                team=team,
                status=ClinchStatus.INCONCLUSIVE,
                exhaustive=False,
                solve_time_ms=elapsed_ms,
                num_variables=num_variables,
                error=(
                    f"Timed out after {int(elapsed)}s: "
                    f"{total_completed}/{record_groups_total * 2} "
                    f"record groups completed"
                ),
                record_groups_completed=clinch_groups_completed,
                record_groups_total=record_groups_total,
            )

    # --- Step 8: Status determination ---
    if not team_not_clinched and clinch_groups_completed == record_groups_total:
        # All record groups processed, no assignment found where team misses
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return CPSolverResult(
            team=team,
            status=ClinchStatus.CLINCHED,
            clinched=True,
            eliminated=False,
            exhaustive=True,
            solve_time_ms=elapsed_ms,
            num_variables=num_variables,
            record_groups_completed=record_groups_total,
            record_groups_total=record_groups_total,
        )

    # --- Step 9: ALIVE — derive magic number ---
    # Sort record groups by wins descending, find minimum wins W where
    # clinch check succeeds (no counter-example at that win level).
    magic_number: int | None = None
    exhaustive = (
        elim_groups_completed >= 1  # At least found non-elimination
        and clinch_groups_completed >= 1  # At least checked one clinch group
    )

    # We checked clinch groups in ascending wins order. The
    # clinch_results_by_wins dict contains {wins: True/False} for groups checked.
    # Find the minimum wins level where clinch holds (True) — that means
    # at that many wins, the team is guaranteed.
    # Since we break early on finding team_not_clinched, we may only have
    # partial data. The magic number is derivable only if we have a wins
    # threshold that separates clinched from not-clinched.
    clinched_win_levels = sorted(
        [w for w, clinched in clinch_results_by_wins.items() if clinched]
    )

    if clinched_win_levels:
        min_clinch_wins = clinched_win_levels[0]
        magic_number = min_clinch_wins - fixed_wins
        if magic_number < 0:
            magic_number = 0

    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
    return CPSolverResult(
        team=team,
        status=ClinchStatus.ALIVE,
        clinched=False,
        eliminated=False,
        exhaustive=(clinch_groups_completed == record_groups_total),
        solve_time_ms=elapsed_ms,
        num_variables=num_variables,
        magic_number=magic_number,
        record_groups_completed=elim_groups_completed + clinch_groups_completed,
        record_groups_total=record_groups_total,
    )


def _solve_clinch_worker(
    args: tuple[str, list[Game], int, CPSolverConfig],
) -> tuple[str, CPSolverResult]:
    """Worker function for parallel solve_clinch_all processing.

    Args:
        args: Tuple of (team, all_games, cutoff_week, config).

    Returns:
        Tuple of (team_name, result).
    """
    team, all_games, cutoff_week, config = args
    try:
        result = solve_clinch(team, all_games, cutoff_week, config)
    except Exception as e:
        logger.error("CP solver failed for %s: %s", team, e)
        result = CPSolverResult(
            team=team,
            status=ClinchStatus.INCONCLUSIVE,
            error=f"Solver failed: {e}",
        )
    return (team, result)


def solve_clinch_all(
    all_games: list[Game],
    cutoff_week: int,
    config: CPSolverConfig | None = None,
) -> dict[str, CPSolverResult]:
    """Determine clinch/elimination status for all 32 teams.

    Processes teams in parallel using available CPU cores. Individual
    team failures do not affect other teams' results.

    Args:
        all_games: All season games.
        cutoff_week: Games in weeks <= cutoff are fixed. Must be 1-18.
        config: Solver configuration (uses defaults if None).

    Returns:
        Dict mapping team name to CPSolverResult.

    Raises:
        RuntimeError: If OR-Tools is not installed.
    """
    if not ORTOOLS_AVAILABLE:
        raise RuntimeError(
            "OR-Tools is not installed. Install with: pip install ortools>=9.9"
        )

    if config is None:
        config = CPSolverConfig()

    num_workers = min(os.cpu_count() or 1, len(ALL_TEAMS))

    worker_args = [
        (team, all_games, cutoff_week, config) for team in ALL_TEAMS
    ]

    results: dict[str, CPSolverResult] = {}

    if num_workers <= 1:
        # Single-process fallback
        for args in worker_args:
            team, result = _solve_clinch_worker(args)
            results[team] = result
    else:
        with Pool(processes=num_workers) as pool:
            for team, result in pool.map(_solve_clinch_worker, worker_args):
                results[team] = result

    return results
