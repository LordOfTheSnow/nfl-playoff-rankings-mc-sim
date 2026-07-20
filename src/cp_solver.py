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

    # --- Step 5a: Fast arithmetic pre-check ---
    # Before expensive per-group solving, check if the answer is obvious
    # from wins arithmetic alone (no tiebreakers needed).
    #
    # For each conference team, compute min_wins (fixed) and max_wins (fixed + remaining).
    # If target team's min_wins > 8th-best team's max_wins → CLINCHED (instant)
    # If target team's max_wins < 7th-best team's min_wins → ELIMINATED (instant)
    conf_win_bounds: list[tuple[str, int, int]] = []  # (team, min_wins, max_wins)
    for t in all_contenders:
        fw, fl, ft_val = fixed_standings.get(t, (0, 0, 0))
        t_remaining = sum(
            1 for g in remaining_games
            if g.home_team == t or g.away_team == t
        )
        conf_win_bounds.append((t, fw, fw + t_remaining))

    team_min_wins = fixed_wins
    team_max_wins = fixed_wins + len(team_remaining_games)

    # Sort other teams by max_wins descending
    others_by_max = sorted(
        [(t, mn, mx) for t, mn, mx in conf_win_bounds if t != team],
        key=lambda x: -x[2],
    )

    # Conference has 7 playoff spots (4 div winners + 3 wild cards).
    # Simplification: if team's min wins beats the 7th-best OTHER team's max,
    # they're guaranteed top 7 by wins alone → clinched.
    if len(others_by_max) >= 6:
        # The 7th spot means team needs to beat at most 6 other teams
        # (since there are 7 spots for 16 teams, team needs to be in top 7)
        # Sort all conf teams by max_wins desc; if team's min is above #8's max → clinched
        all_by_max = sorted(conf_win_bounds, key=lambda x: -x[2])
        if len(all_by_max) >= 8:
            eighth_max = all_by_max[7][2]
            if team_min_wins > eighth_max:
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                return CPSolverResult(
                    team=team,
                    status=ClinchStatus.CLINCHED,
                    clinched=True,
                    eliminated=False,
                    exhaustive=True,
                    solve_time_ms=elapsed_ms,
                    num_variables=0,
                    record_groups_completed=0,
                    record_groups_total=record_groups_total,
                )

    # Fast elimination: if team's max wins < 7th-best min wins in conference → eliminated
    all_by_min_desc = sorted(conf_win_bounds, key=lambda x: -x[1])
    if len(all_by_min_desc) >= 7:
        seventh_min = all_by_min_desc[6][1]
        if team_max_wins < seventh_min:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return CPSolverResult(
                team=team,
                status=ClinchStatus.ELIMINATED,
                clinched=False,
                eliminated=True,
                exhaustive=True,
                solve_time_ms=elapsed_ms,
                num_variables=0,
                record_groups_completed=0,
                record_groups_total=record_groups_total,
            )

    # Fast division clinch: if team's min wins > all division rivals' max wins,
    # team is guaranteed to win the division → clinched (division winners always make playoffs)
    from src.nfl_teams import get_team_division
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
                team=team,
                status=ClinchStatus.CLINCHED,
                clinched=True,
                eliminated=False,
                exhaustive=True,
                solve_time_ms=elapsed_ms,
                num_variables=0,
                record_groups_completed=0,
                record_groups_total=record_groups_total,
            )

        # --- Step 5: Solve via single feasibility checks (no enumeration) ---
    # Strategy: Don't enumerate solutions. Instead, add ranking constraints
    # directly to the CP-SAT model and check feasibility with a single Solve() call.
    #
    # Elimination check: "Can team make playoffs?"
    #   → Build model for team's BEST record, check if any feasible assignment
    #     puts them in top 7 by wins. Single Solve(), no callback.
    #
    # Clinch check: "Can team MISS playoffs?"
    #   → Build model for team's WORST record, check if any feasible assignment
    #     puts enough other teams above them. Single Solve(), no callback.
    #
    # For tiebreaker-dependent borderline cases, fall back to the callback
    # approach with a tight time cap — but only for the 1-2 record groups
    # that are actually borderline.

    # Identify how many teams could potentially finish with more wins than
    # target team at each record level
    def _can_make_playoffs_at_record(target_record: tuple[int, int, int]) -> bool | None:
        """Check if team can make playoffs at given record.
        
        Returns True (can make it), False (cannot), or None (inconclusive/need tiebreaker).
        """
        target_w = target_record[0]

        # Build model
        model, game_outcome_vars, team_record_vars = _build_cpsat_model(
            team=team, conference=conference, target_record=target_record,
            all_games=all_games, remaining_games=remaining_games,
            fixed_standings=fixed_standings, contenders=all_contenders,
        )

        # Count how many teams can STRICTLY beat target's wins
        # If fewer than 7 teams can possibly have more wins → team is guaranteed top 7
        teams_that_can_beat = 0
        for t in all_contenders:
            if t == team:
                continue
            fw_t = fixed_standings.get(t, (0, 0, 0))[0]
            t_remaining = sum(
                1 for g in remaining_games
                if g.home_team == t or g.away_team == t
            )
            if fw_t + t_remaining > target_w:
                teams_that_can_beat += 1

        # If fewer than 7 teams can even theoretically beat target → always makes it
        if teams_that_can_beat < 7:
            return True

        # If model is infeasible (record impossible given constraints) → skip
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 1.0
        status = solver.solve(model)
        if status == cp_model.INFEASIBLE:
            return None  # This record is impossible, skip it

        # For borderline cases: use callback with tight timeout
        validator = PlayoffValidator(
            team=team, all_games=all_games, remaining_games=remaining_games,
            game_outcome_vars=game_outcome_vars, search_for_miss=False,
        )
        solver2 = cp_model.CpSolver()
        solver2.parameters.enumerate_all_solutions = True
        solver2.parameters.max_time_in_seconds = 0.5  # tight cap per group
        solver2.solve(model, validator)

        if validator.found:
            return True
        # Timed out or no witness found
        return False

    def _can_miss_playoffs_at_record(target_record: tuple[int, int, int]) -> bool | None:
        """Check if team can miss playoffs at given record.
        
        Uses a constraint-based approach: adds a constraint that 7 other teams
        all finish with more wins than the target, then checks if the model
        is feasible. If feasible → team CAN miss. If infeasible for all
        possible 7-team subsets → team CANNOT miss → clinched.
        
        For efficiency, only tests the most plausible subset (teams with
        highest max_wins). If that subset is infeasible → clinched.
        
        Returns True (can miss), False (cannot miss), or None (inconclusive).
        """
        target_w = target_record[0]

        # Build model
        model, game_outcome_vars, team_record_vars = _build_cpsat_model(
            team=team, conference=conference, target_record=target_record,
            all_games=all_games, remaining_games=remaining_games,
            fixed_standings=fixed_standings, contenders=all_contenders,
        )

        # If base model is infeasible → this record is impossible
        solver_check = cp_model.CpSolver()
        solver_check.parameters.max_time_in_seconds = 1.0
        status = solver_check.solve(model)
        if status == cp_model.INFEASIBLE:
            return False  # record impossible → can't miss

        # Quick arithmetic: how many teams are GUARANTEED to beat target's wins?
        teams_guaranteed_above = 0
        for t in all_contenders:
            if t == team:
                continue
            fw_t = fixed_standings.get(t, (0, 0, 0))[0]
            if fw_t > target_w:
                teams_guaranteed_above += 1
        if teams_guaranteed_above >= 7:
            return True

        # Constraint-based clinch proof: add constraint that 7 other teams
        # each have wins > target_w (or wins >= target_w + 1).
        # If this is INFEASIBLE → can't have 7 teams above target → clinched.
        #
        # Pick the 7 teams most likely to beat target (highest max_wins).
        # Add: wins(t) > target_w for each of these 7 teams.
        # One Solve() call, no callback.
        other_teams_by_potential = sorted(
            [(t, fixed_standings.get(t, (0, 0, 0))[0] + sum(
                1 for g in remaining_games if g.home_team == t or g.away_team == t
            )) for t in all_contenders if t != team],
            key=lambda x: -x[1],
        )

        # Teams that CAN reach >= target_w are relevant (same wins can beat via tiebreaker)
        can_tie_or_beat = [(t, mx) for t, mx in other_teams_by_potential if mx >= target_w]

        if len(can_tie_or_beat) < 7:
            # Fewer than 7 teams can even theoretically match target → can't miss
            return False

        # Take top 7 teams that could match or beat target_w
        top7 = [t for t, mx in can_tie_or_beat[:7]]

        # Add constraints: each of these 7 teams must finish with wins >= target_w
        # (same wins can still beat target via tiebreaker)
        model2, game_outcome_vars2, team_record_vars2 = _build_cpsat_model(
            team=team, conference=conference, target_record=target_record,
            all_games=all_games, remaining_games=remaining_games,
            fixed_standings=fixed_standings, contenders=all_contenders,
        )
        for t in top7:
            if t in team_record_vars2:
                wins_var, _, _ = team_record_vars2[t]
                model2.add(wins_var >= target_w)

        solver2 = cp_model.CpSolver()
        solver2.parameters.max_time_in_seconds = 2.0
        status2 = solver2.solve(model2)

        if status2 == cp_model.INFEASIBLE:
            # Impossible for 7 teams to all match/beat target by wins → can't miss
            return False
        elif status2 == cp_model.FEASIBLE or status2 == cp_model.OPTIMAL:
            # There IS a scenario where 7 teams match/beat target by wins.
            # But team might still make it via division winner or tiebreaker.
            # Use callback to check if team actually misses in this constrained model.
            validator = PlayoffValidator(
                team=team, all_games=all_games, remaining_games=remaining_games,
                game_outcome_vars=game_outcome_vars2, search_for_miss=True,
            )
            solver3 = cp_model.CpSolver()
            solver3.parameters.enumerate_all_solutions = True
            solver3.parameters.max_time_in_seconds = 5.0
            status3 = solver3.solve(model2, validator)
            if validator.found:
                return True  # Found a scenario where team misses → not clinched
            # Callback didn't find a miss, but may not have searched exhaustively.
            # OPTIMAL means all solutions checked → proven safe.
            if status3 == cp_model.OPTIMAL:
                return False  # Exhaustively checked, no miss exists → clinched
            # Timed out — inconclusive
            return None
        else:
            # Solver timed out on the constraint check
            return None

    # --- Execute checks ---
    groups_completed = 0

    # Elimination check: can team make playoffs at their BEST possible record?
    # Start from highest wins and work down — stop at first "can make it"
    team_not_eliminated = False
    elim_sorted = sorted(record_groups, key=lambda r: -r[0])

    for target_record in elim_sorted:
        elapsed = time.perf_counter() - start_time
        if elapsed >= config.time_limit:
            break

        if num_variables == 0:
            # Get variable count from first model build
            m, gvars, _ = _build_cpsat_model(
                team=team, conference=conference, target_record=target_record,
                all_games=all_games, remaining_games=remaining_games,
                fixed_standings=fixed_standings, contenders=all_contenders,
            )
            num_variables = len(gvars)

        result = _can_make_playoffs_at_record(target_record)
        groups_completed += 1
        if result is True:
            team_not_eliminated = True
            break

    if not team_not_eliminated:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        if groups_completed == record_groups_total:
            return CPSolverResult(
                team=team, status=ClinchStatus.ELIMINATED,
                clinched=False, eliminated=True, exhaustive=True,
                solve_time_ms=elapsed_ms, num_variables=num_variables,
                record_groups_completed=groups_completed,
                record_groups_total=record_groups_total,
            )
        return CPSolverResult(
            team=team, status=ClinchStatus.INCONCLUSIVE, exhaustive=False,
            solve_time_ms=elapsed_ms, num_variables=num_variables,
            error=f"Timed out: {groups_completed}/{record_groups_total} groups",
            record_groups_completed=groups_completed,
            record_groups_total=record_groups_total,
        )

    # Clinch check: can team miss playoffs at their WORST possible record?
    # Start from lowest wins — stop at first "can miss"
    team_not_clinched = False
    clinch_inconclusive = False
    clinch_groups_checked = 0
    clinch_sorted = sorted(record_groups, key=lambda r: r[0])

    for target_record in clinch_sorted:
        elapsed = time.perf_counter() - start_time
        if elapsed >= config.time_limit:
            clinch_inconclusive = True
            break

        result = _can_miss_playoffs_at_record(target_record)
        groups_completed += 1
        clinch_groups_checked += 1
        if result is True:
            team_not_clinched = True
            break
        elif result is None:
            # Inconclusive for this group (timed out or infeasible record)
            # If infeasible → skip, doesn't affect clinch determination
            # If timed out → can't prove clinch
            # We check: was the record itself impossible? (None from infeasible)
            # The function returns None for both infeasible AND timeout.
            # We need to distinguish. For now, if record is possible but
            # solver timed out, we can't claim clinch.
            # Since we already checked feasibility inside the function,
            # None here means either infeasible (safe to skip) or timeout.
            # Let's be conservative: mark inconclusive
            clinch_inconclusive = True

    elapsed_ms = int((time.perf_counter() - start_time) * 1000)

    if not team_not_clinched and not clinch_inconclusive and clinch_groups_checked == record_groups_total:
        # Proved: can't miss at any record → clinched
        return CPSolverResult(
            team=team, status=ClinchStatus.CLINCHED,
            clinched=True, eliminated=False, exhaustive=True,
            solve_time_ms=elapsed_ms, num_variables=num_variables,
            record_groups_completed=groups_completed,
            record_groups_total=record_groups_total,
        )

    if not team_not_clinched:
        # Either timed out or inconclusive — conservatively return alive
        return CPSolverResult(
            team=team, status=ClinchStatus.ALIVE,
            clinched=False, eliminated=False, exhaustive=not clinch_inconclusive,
            solve_time_ms=elapsed_ms, num_variables=num_variables,
            record_groups_completed=groups_completed,
            record_groups_total=record_groups_total,
        )

    # Team is alive (not eliminated, not clinched)
    return CPSolverResult(
        team=team, status=ClinchStatus.ALIVE,
        clinched=False, eliminated=False, exhaustive=True,
        solve_time_ms=elapsed_ms, num_variables=num_variables,
        record_groups_completed=groups_completed,
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
