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


def _build_ranking_model(
    team: str,
    conference: str,
    all_games: list[Game],
    remaining_games: list[Game],
    fixed_standings: dict[str, tuple[int, int, int]],
    contenders: list[str],
) -> tuple[Any, dict[str, Any], dict[str, tuple[Any, Any, Any]]]:
    """Build a CP-SAT model WITHOUT forcing the target team's record.

    Same as _build_cpsat_model but without the target_record constraint,
    allowing the solver to explore all possible final records for the target.

    Returns:
        Tuple of (model, game_outcome_vars, team_record_vars).
    """
    if not ORTOOLS_AVAILABLE:
        raise RuntimeError("OR-Tools is not installed.")

    model = cp_model.CpModel()

    game_outcome_vars: dict[str, Any] = {}
    for game in remaining_games:
        var = model.new_int_var(0, 2, f"game_{game.game_id}")
        game_outcome_vars[game.game_id] = var

    game_home_wins: dict[str, Any] = {}
    game_away_wins: dict[str, Any] = {}
    game_ties: dict[str, Any] = {}

    for game in remaining_games:
        gid = game.game_id
        outcome_var = game_outcome_vars[gid]

        hw = model.new_bool_var(f"hw_{gid}")
        aw = model.new_bool_var(f"aw_{gid}")
        tie = model.new_bool_var(f"tie_{gid}")

        model.add(hw + aw + tie == 1)
        model.add(outcome_var == 0).only_enforce_if(hw)
        model.add(outcome_var != 0).only_enforce_if(hw.negated())
        model.add(outcome_var == 1).only_enforce_if(aw)
        model.add(outcome_var != 1).only_enforce_if(aw.negated())
        model.add(outcome_var == 2).only_enforce_if(tie)
        model.add(outcome_var != 2).only_enforce_if(tie.negated())

        game_home_wins[gid] = hw
        game_away_wins[gid] = aw
        game_ties[gid] = tie

    contenders_set = set(contenders)
    team_home_games: dict[str, list[str]] = {t: [] for t in contenders}
    team_away_games: dict[str, list[str]] = {t: [] for t in contenders}

    for game in remaining_games:
        if game.home_team in contenders_set:
            team_home_games[game.home_team].append(game.game_id)
        if game.away_team in contenders_set:
            team_away_games[game.away_team].append(game.game_id)

    team_record_vars: dict[str, tuple[Any, Any, Any]] = {}
    total_season_games = 17

    for t in contenders:
        fw, fl, ft = fixed_standings.get(t, (0, 0, 0))
        remaining_home_gids = team_home_games[t]
        remaining_away_gids = team_away_games[t]
        n_remaining = len(remaining_home_gids) + len(remaining_away_gids)

        max_wins = fw + n_remaining
        max_losses = fl + n_remaining
        max_ties = ft + n_remaining

        wins_var = model.new_int_var(fw, max_wins, f"wins_{t}")
        losses_var = model.new_int_var(fl, max_losses, f"losses_{t}")
        ties_var = model.new_int_var(ft, max_ties, f"ties_{t}")

        win_bools: list[Any] = []
        for gid in remaining_home_gids:
            win_bools.append(game_home_wins[gid])
        for gid in remaining_away_gids:
            win_bools.append(game_away_wins[gid])

        if win_bools:
            model.add(wins_var == fw + sum(win_bools))
        else:
            model.add(wins_var == fw)

        loss_bools: list[Any] = []
        for gid in remaining_home_gids:
            loss_bools.append(game_away_wins[gid])
        for gid in remaining_away_gids:
            loss_bools.append(game_home_wins[gid])

        if loss_bools:
            model.add(losses_var == fl + sum(loss_bools))
        else:
            model.add(losses_var == fl)

        tie_bools: list[Any] = []
        for gid in remaining_home_gids:
            tie_bools.append(game_ties[gid])
        for gid in remaining_away_gids:
            tie_bools.append(game_ties[gid])

        if tie_bools:
            model.add(ties_var == ft + sum(tie_bools))
        else:
            model.add(ties_var == ft)

        model.add(wins_var + losses_var + ties_var == total_season_games)
        team_record_vars[t] = (wins_var, losses_var, ties_var)

    return (model, game_outcome_vars, team_record_vars)


def solve_clinch(
    team: str,
    all_games: list[Game],
    cutoff_week: int,
    config: CPSolverConfig | None = None,
) -> CPSolverResult:
    """Determine clinch/elimination status for a team.

    Uses a pure constraint-based approach:
    - Clinch: proves it's INFEASIBLE for 7+ other teams to finish with
      wins >= target team's wins (accounting for shared game constraints).
    - Elimination: proves it's INFEASIBLE for the team to finish in a
      position where fewer than 7 others beat them.

    No solution enumeration, no callbacks. Single Solve() per check.

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
    from src.nfl_teams import get_team_division

    if not ORTOOLS_AVAILABLE:
        raise RuntimeError(
            "OR-Tools is not installed. Install with: pip install ortools>=9.9"
        )

    if config is None:
        config = CPSolverConfig()

    if team not in _VALID_TEAMS:
        return CPSolverResult(
            team=team, status=ClinchStatus.ALIVE,
            error=f"Unknown team: '{team}'. Valid teams: {sorted(_VALID_TEAMS)}",
        )

    if not isinstance(cutoff_week, int) or cutoff_week < 1 or cutoff_week > 18:
        return CPSolverResult(
            team=team, status=ClinchStatus.ALIVE,
            error=f"cutoff_week must be between 1 and 18, got: {cutoff_week}",
        )

    if (
        not isinstance(config.time_limit, int)
        or config.time_limit < 1
        or config.time_limit > 300
    ):
        return CPSolverResult(
            team=team, status=ClinchStatus.ALIVE,
            error=f"time_limit must be between 1 and 300 seconds, got: {config.time_limit}",
        )

    start_time = time.perf_counter()

    # --- Step 1: Partition games ---
    conference = get_team_conference(team)
    if not conference:
        return CPSolverResult(
            team=team, status=ClinchStatus.ALIVE,
            error=f"Could not determine conference for team: {team}",
        )

    contenders = identify_contenders(team, all_games, cutoff_week)
    all_contenders = [team] + [t for t in contenders if t != team]

    team_remaining_games, relevant_other_games = get_relevant_games(
        team, all_games, cutoff_week, contenders
    )
    remaining_games = team_remaining_games + relevant_other_games

    # --- Shortcut: zero remaining games → just check the bracket ---
    if len(remaining_games) == 0:
        # All games are fixed. Compute standings and check if team is in playoffs.
        standings = compute_standings(all_games)
        bracket = determine_playoff_bracket(standings, all_games=all_games)
        conf_seeds = bracket.afc_seeds if conference == "AFC" else bracket.nfc_seeds
        team_in_bracket = any(s.team == team for s in conf_seeds)
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        if team_in_bracket:
            return CPSolverResult(
                team=team, status=ClinchStatus.CLINCHED,
                clinched=True, eliminated=False, exhaustive=True,
                solve_time_ms=elapsed_ms, num_variables=0,
                record_groups_completed=0, record_groups_total=0,
            )
        else:
            return CPSolverResult(
                team=team, status=ClinchStatus.ELIMINATED,
                clinched=False, eliminated=True, exhaustive=True,
                solve_time_ms=elapsed_ms, num_variables=0,
                record_groups_completed=0, record_groups_total=0,
            )

    # --- Step 2: Compute fixed standings ---
    fixed_standings: dict[str, tuple[int, int, int]] = {}
    for t in all_contenders:
        wins, losses, ties = 0, 0, 0
        for game in all_games:
            if game.week > cutoff_week:
                continue
            if game.home_team != t and game.away_team != t:
                continue
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
                ties += 1
        fixed_standings[t] = (wins, losses, ties)

    fixed_wins, fixed_losses, fixed_ties = fixed_standings.get(team, (0, 0, 0))
    team_min_wins = fixed_wins
    team_max_wins = fixed_wins + len(team_remaining_games)

    # --- Step 3: Fast arithmetic pre-checks (Tier 1 & 2) ---
    conf_win_bounds: list[tuple[str, int, int]] = []
    for t in all_contenders:
        fw = fixed_standings.get(t, (0, 0, 0))[0]
        t_remaining = sum(
            1 for g in remaining_games
            if g.home_team == t or g.away_team == t
        )
        conf_win_bounds.append((t, fw, fw + t_remaining))

    # Tier 1a: Clinch by conference-wide wins dominance
    all_by_max = sorted(conf_win_bounds, key=lambda x: -x[2])
    if len(all_by_max) >= 8:
        eighth_max = all_by_max[7][2]
        if team_min_wins > eighth_max:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return CPSolverResult(
                team=team, status=ClinchStatus.CLINCHED,
                clinched=True, eliminated=False, exhaustive=True,
                solve_time_ms=elapsed_ms, num_variables=0,
                record_groups_completed=0, record_groups_total=0,
            )

    # Tier 1b: Elimination by conference-wide wins floor
    # Only applies if team ALSO can't win their division (division winners
    # make playoffs regardless of conference-wide wins ranking).
    all_by_min_desc = sorted(conf_win_bounds, key=lambda x: -x[1])
    if len(all_by_min_desc) >= 7:
        seventh_min = all_by_min_desc[6][1]
        if team_max_wins < seventh_min:
            # Check if team can still win their division
            # Look at ALL teams in the division (not just contenders)
            can_win_division = True
            team_div_info_elim = get_team_division(team)
            if team_div_info_elim:
                _, team_div_elim = team_div_info_elim
                for t in ALL_TEAMS:
                    if t == team or get_team_conference(t) != conference:
                        continue
                    t_div_info = get_team_division(t)
                    if not t_div_info or t_div_info[1] != team_div_elim:
                        continue
                    # Compute this rival's min wins (fixed wins only)
                    rival_wins = 0
                    for g in all_games:
                        if g.week > cutoff_week:
                            continue
                        if g.status != GameStatus.COMPLETED:
                            continue
                        if g.home_score is None or g.away_score is None:
                            continue
                        if g.home_team == t and g.home_score > g.away_score:
                            rival_wins += 1
                        elif g.away_team == t and g.away_score > g.home_score:
                            rival_wins += 1
                    # Rival's min wins vs team's max wins — must be STRICTLY more
                    # (at equal wins, tiebreakers could favor either team)
                    if rival_wins > team_max_wins:
                        can_win_division = False
                        break
            if not can_win_division:
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                return CPSolverResult(
                    team=team, status=ClinchStatus.ELIMINATED,
                    clinched=False, eliminated=True, exhaustive=True,
                    solve_time_ms=elapsed_ms, num_variables=0,
                    record_groups_completed=0, record_groups_total=0,
                )

    # Tier 2: Division clinch (min wins > all division rivals' max)
    team_div_info = get_team_division(team)
    if team_div_info:
        _, team_div = team_div_info
        div_rivals_max = [
            mx for t, mn, mx in conf_win_bounds
            if t != team and get_team_division(t) and get_team_division(t)[1] == team_div
        ]
        if div_rivals_max and team_min_wins > max(div_rivals_max):
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return CPSolverResult(
                team=team, status=ClinchStatus.CLINCHED,
                clinched=True, eliminated=False, exhaustive=True,
                solve_time_ms=elapsed_ms, num_variables=0,
                record_groups_completed=0, record_groups_total=0,
            )

    # --- Step 4: Constraint-based solver (Tier 3) ---
    # Model NFL playoff structure: 4 division winners + 3 wild cards = 7 spots.
    # A team makes playoffs if they win their division OR get a wild card.
    #
    # Clinch check: "Is it possible for the team to MISS playoffs?"
    #   Model "team misses" = team doesn't win division AND isn't top-3 wild card.
    #   If INFEASIBLE → clinched.
    #
    # Elimination check: "Is it possible for the team to MAKE playoffs?"
    #   Model "team makes it" = team wins division OR is top-3 wild card.
    #   If INFEASIBLE → eliminated.

    from src.nfl_teams import get_team_division, NFL_TEAMS

    # Group contenders by division
    div_teams: dict[str, list[str]] = {}
    for t in all_contenders:
        dinfo = get_team_division(t)
        if dinfo:
            _, d = dinfo
            if d not in div_teams:
                div_teams[d] = []
            div_teams[d].append(t)

    team_div = get_team_division(team)[1] if get_team_division(team) else None
    num_variables = 0

    # --- Precompute H2H outcomes for division tiebreaker awareness ---
    # For each pair of division rivals, determine if H2H is decided:
    # h2h_decided[(a, b)] = True means 'a' has won the H2H against 'b'
    # (a leads in wins among their matchups AND no future games remain)
    h2h_decided: dict[tuple[str, str], bool] = {}
    for div_name, teams_in_div_list in div_teams.items():
        for i, t_a in enumerate(teams_in_div_list):
            for t_b in teams_in_div_list[i + 1:]:
                wins_a = wins_b = 0
                future_h2h = 0
                for g in all_games:
                    if not ((g.home_team == t_a and g.away_team == t_b) or
                            (g.home_team == t_b and g.away_team == t_a)):
                        continue
                    if g.week > cutoff_week:
                        future_h2h += 1
                        continue
                    if g.status != GameStatus.COMPLETED:
                        continue
                    if g.home_score is None or g.away_score is None:
                        continue
                    if g.home_score > g.away_score:
                        if g.home_team == t_a:
                            wins_a += 1
                        else:
                            wins_b += 1
                    elif g.away_score > g.home_score:
                        if g.away_team == t_a:
                            wins_a += 1
                        else:
                            wins_b += 1
                # H2H is decided if one side leads AND no future games can flip it
                if future_h2h == 0 and wins_a != wins_b:
                    if wins_a > wins_b:
                        h2h_decided[(t_a, t_b)] = True  # a beats b
                        h2h_decided[(t_b, t_a)] = False  # b loses to a
                    else:
                        h2h_decided[(t_a, t_b)] = False
                        h2h_decided[(t_b, t_a)] = True

    # --- Step 4a: Clinch check ---
    # "Can the team miss the playoffs?"
    # Team misses if:
    #   (1) At least one division rival has wins >= team's wins (team doesn't win division by wins alone), AND
    #   (2) At least 3 non-division-winner teams from other divisions have wins >= team's wins
    #       (filling all 3 wild card spots above team)
    #
    # Simplified model: team misses if 7 other teams all have wins >= team's wins.
    # BUT we refine: team makes it if they win their division (no rival matches them).
    # So "team misses" requires: (a) a division rival ties/beats them, AND (b) they lose the wild card race.
    #
    # Conservative clinch: if it's INFEASIBLE for ANY division rival to reach team's
    # min wins AND INFEASIBLE for 3 non-division teams from other divisions to all
    # reach team's min wins → clinched.
    #
    # Simpler approach that works: "team misses" = at least one div rival has wins >= team
    # AND at least 6 other teams (from any division) have wins >= team.
    # (Because if 7 total teams beat/tie team AND one is from their division, team
    # neither wins division nor gets wild card.)

    clinch_model, clinch_gvars, clinch_tvars = _build_ranking_model(
        team=team, conference=conference, all_games=all_games,
        remaining_games=remaining_games, fixed_standings=fixed_standings,
        contenders=all_contenders,
    )
    num_variables = len(clinch_gvars)
    clinch_target_wins = clinch_tvars[team][0]

    # Create indicators: for each other team, does it match/beat target?
    clinch_beats: dict[str, Any] = {}
    for t in all_contenders:
        if t == team:
            continue
        t_wins = clinch_tvars[t][0]
        indicator = clinch_model.new_bool_var(f"beats_{t}")
        clinch_model.add(t_wins >= clinch_target_wins).only_enforce_if(indicator)
        clinch_model.add(t_wins <= clinch_target_wins - 1).only_enforce_if(indicator.negated())
        clinch_beats[t] = indicator

    # Constraint: at least one DIVISION rival matches/beats target
    if team_div and team_div in div_teams:
        div_rival_beats = [clinch_beats[t] for t in div_teams[team_div] if t != team and t in clinch_beats]
        if div_rival_beats:
            clinch_model.add(sum(div_rival_beats) >= 1)
        else:
            # No division rivals → team always wins division → clinched
            # (This shouldn't happen with 4 teams per division, but handle it)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return CPSolverResult(
                team=team, status=ClinchStatus.CLINCHED,
                clinched=True, eliminated=False, exhaustive=True,
                solve_time_ms=elapsed_ms, num_variables=num_variables,
                record_groups_completed=0, record_groups_total=0,
            )

    # Constraint: at least 7 total teams (including the div rival) match/beat target.
    # This means team finishes 8th or worse by wins in the conference.
    all_beats = list(clinch_beats.values())
    clinch_model.add(sum(all_beats) >= 7)

    clinch_solver = cp_model.CpSolver()
    clinch_solver.parameters.max_time_in_seconds = config.time_limit / 2
    clinch_status = clinch_solver.solve(clinch_model)

    if clinch_status == cp_model.INFEASIBLE:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return CPSolverResult(
            team=team, status=ClinchStatus.CLINCHED,
            clinched=True, eliminated=False, exhaustive=True,
            solve_time_ms=elapsed_ms, num_variables=num_variables,
            record_groups_completed=0, record_groups_total=0,
        )

    # --- Step 4b: Elimination check ---
    # "Can the team make the playoffs?"
    # NFL playoffs: 4 division winners (seeds 1-4) + 3 wild cards (seeds 5-7).
    # Team makes it if EITHER:
    #   (a) Team wins its division (best record in division, wins tiebreakers), OR
    #   (b) Team gets a wild card: among non-division-winners, team is in top 3 by wins.
    #
    # Model each division's winner, then count wild card competitors correctly.

    elim_model, elim_gvars, elim_tvars = _build_ranking_model(
        team=team, conference=conference, all_games=all_games,
        remaining_games=remaining_games, fixed_standings=fixed_standings,
        contenders=all_contenders,
    )
    elim_target_wins = elim_tvars[team][0]

    # --- Model division winners ---
    # For each division, create BoolVars indicating which team wins it.
    # Simplification: division winner = team with most wins in that division.
    # (Ignores tiebreakers at same wins — conservative for elimination)
    div_winner_vars: dict[str, Any] = {}  # team → BoolVar "is division winner"

    for div_name, teams_in_div in div_teams.items():
        # For each team in this division, create "is_winner" BoolVar
        winner_bools = []
        for t in teams_in_div:
            if t not in elim_tvars:
                continue
            is_winner = elim_model.new_bool_var(f"div_winner_{t}")
            div_winner_vars[t] = is_winner
            winner_bools.append(is_winner)

            # is_winner => this team beats every rival in the division.
            # If H2H is decided and rival leads, team needs STRICTLY more wins.
            # If H2H is undecided or team leads, team needs >= wins.
            for rival in teams_in_div:
                if rival == t or rival not in elim_tvars:
                    continue
                t_wins_var = elim_tvars[t][0]
                rival_wins_var = elim_tvars[rival][0]
                # Check if rival has won the H2H against t (decided)
                rival_leads_h2h = h2h_decided.get((rival, t), False)
                if rival_leads_h2h:
                    # Rival won H2H → t needs strictly more wins to win division
                    elim_model.add(t_wins_var >= rival_wins_var + 1).only_enforce_if(is_winner)
                else:
                    # H2H undecided or t leads → t needs >= wins
                    elim_model.add(t_wins_var >= rival_wins_var).only_enforce_if(is_winner)

        # Exactly one team wins each division
        if winner_bools:
            elim_model.add(sum(winner_bools) == 1)

    # --- BoolVar: target team wins its division ---
    target_wins_div = div_winner_vars.get(team)
    if target_wins_div is None:
        # Team not in any division? Shouldn't happen
        target_wins_div = elim_model.new_bool_var("wins_div_fallback")
        elim_model.add(target_wins_div == 0)

    # --- BoolVar: target team gets a wild card ---
    # Wild card: team is NOT a division winner AND is among the top 3
    # non-division-winners by wins in the conference.
    # "Top 3 non-winners" = at most 2 other non-winners have strictly more wins.
    #
    # For each other team: they block a wild card spot if they're NOT a division
    # winner AND have strictly more wins than target.
    wc_blockers: list[Any] = []
    for t in all_contenders:
        if t == team:
            continue
        t_wins = elim_tvars[t][0]
        t_is_winner = div_winner_vars.get(t)
        if t_is_winner is None:
            continue

        # blocker = (t is NOT div winner) AND (t has more wins than target)
        blocker = elim_model.new_bool_var(f"wc_blocks_{t}")
        has_more_wins = elim_model.new_bool_var(f"more_wins_{t}")
        elim_model.add(t_wins >= elim_target_wins + 1).only_enforce_if(has_more_wins)
        elim_model.add(t_wins <= elim_target_wins).only_enforce_if(has_more_wins.negated())

        # blocker = NOT(div_winner) AND has_more_wins
        # blocker => NOT div_winner
        elim_model.add(t_is_winner == 0).only_enforce_if(blocker)
        # blocker => has_more_wins
        elim_model.add(has_more_wins == 1).only_enforce_if(blocker)
        # NOT blocker => NOT(NOT div_winner AND has_more_wins)
        # i.e., NOT blocker => div_winner OR NOT has_more_wins
        elim_model.add(t_is_winner + (1 - has_more_wins) >= 1).only_enforce_if(blocker.negated())

        wc_blockers.append(blocker)

    # Target gets wild card if: NOT a div winner AND at most 2 blockers
    gets_wc = elim_model.new_bool_var("gets_wildcard")
    num_blockers = elim_model.new_int_var(0, 15, "num_wc_blockers")
    elim_model.add(num_blockers == sum(wc_blockers))
    # gets_wc => NOT target_wins_div (team is not a winner)
    elim_model.add(target_wins_div == 0).only_enforce_if(gets_wc)
    # gets_wc => num_blockers <= 2
    elim_model.add(num_blockers <= 2).only_enforce_if(gets_wc)

    # Team makes playoffs: wins division OR gets wild card
    elim_model.add(target_wins_div + gets_wc >= 1)

    elim_solver = cp_model.CpSolver()
    remaining_time = config.time_limit - (time.perf_counter() - start_time)
    elim_solver.parameters.max_time_in_seconds = max(remaining_time, 1.0)
    elim_status = elim_solver.solve(elim_model)

    if elim_status == cp_model.INFEASIBLE:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return CPSolverResult(
            team=team, status=ClinchStatus.ELIMINATED,
            clinched=False, eliminated=True, exhaustive=True,
            solve_time_ms=elapsed_ms, num_variables=num_variables,
            record_groups_completed=0, record_groups_total=0,
        )

    # --- Step 5: Determine status ---
    elapsed_ms = int((time.perf_counter() - start_time) * 1000)

    if clinch_status == cp_model.UNKNOWN or elim_status == cp_model.UNKNOWN:
        return CPSolverResult(
            team=team, status=ClinchStatus.INCONCLUSIVE,
            clinched=False, eliminated=False, exhaustive=False,
            solve_time_ms=elapsed_ms, num_variables=num_variables,
            error="Solver timed out",
            record_groups_completed=0, record_groups_total=0,
        )

    return CPSolverResult(
        team=team, status=ClinchStatus.ALIVE,
        clinched=False, eliminated=False, exhaustive=True,
        solve_time_ms=elapsed_ms, num_variables=num_variables,
        record_groups_completed=0, record_groups_total=0,
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
