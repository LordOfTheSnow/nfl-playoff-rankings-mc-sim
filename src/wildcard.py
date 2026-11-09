"""Wild Card Round data assembly: per-conference, seed-ordered team data for
either Actual standings (real results through a cutoff week) or Simulated
(most-likely) seeding from a Monte Carlo run.

Composes standings.py (rank_conference reuses the real tiebreaker engine for
seeds 8-16, the same way determine_playoff_bracket does for seeds 1-7) and
team_strength.py rather than reimplementing any ranking logic. The two
genuinely new pieces of domain logic are:

- last5_and_streak: no other part of the codebase derives a team's recent
  game-by-game form (_handle_get_statistics computes season-wide longest
  streaks across the league, not a single team's current one).
- assign_modal_seeds: Simulated mode needs one internally-consistent 7-team
  bracket (no duplicate seeds, one division winner per division) out of each
  team's independent per-seed probability distribution; nothing else in the
  app collapses a seeding matrix down to a single bracket.

See design_handoff_wildcard/README.md for the full screen spec this feeds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.data_client import Game, GameStatus
from src.standings import Conference, TeamStanding, rank_conference

_CONFERENCES = ("AFC", "NFC")
_DIVISION_WINNER_SEEDS = (1, 2, 3, 4)
_WILD_CARD_SEEDS = (5, 6, 7)


@dataclass
class StreakInfo:
    """A team's current consecutive-result run, ending at its most recent
    completed game."""

    result: str  # "W" | "L" | "T"
    length: int


def _team_game_log(team: str, games: list[Game]) -> list[str]:
    """Ordered oldest->newest "W"/"L"/"T" results for a team's completed games."""
    results: list[str] = []
    for g in sorted((g for g in games if g.week), key=lambda g: g.week):
        if g.status != GameStatus.COMPLETED:
            continue
        if g.home_team != team and g.away_team != team:
            continue
        if g.home_score is None or g.away_score is None:
            continue
        if g.home_score == g.away_score:
            results.append("T")
        elif (g.home_team == team) == (g.home_score > g.away_score):
            results.append("W")
        else:
            results.append("L")
    return results


def last5_and_streak(team: str, games: list[Game]) -> tuple[list[str], StreakInfo | None]:
    """A team's last-5 game log (oldest->newest, up to 5 entries) and its
    current streak (the trailing same-result run, not limited to last5).

    Returns ([], None) for a team with no completed games yet.
    """
    log = _team_game_log(team, games)
    if not log:
        return [], None

    last5 = log[-5:]
    streak_result = log[-1]
    streak_len = 0
    for r in reversed(log):
        if r != streak_result:
            break
        streak_len += 1
    return last5, StreakInfo(result=streak_result, length=streak_len)


def _playoff_probability(team_result: dict[str, Any]) -> float:
    return float(team_result.get("playoff_probability", 0) or 0)


def _division_title_probability(team_result: dict[str, Any]) -> float:
    """A team's chance of winning its division: only division winners can
    hold seeds 1-4, so this is the sum of its seed 1-4 probabilities."""
    seed_probs = team_result.get("seed_probabilities") or {}
    return sum(float(seed_probs.get(str(s), 0) or 0) for s in _DIVISION_WINNER_SEEDS)


def _claim_modal_seeds(
    teams: list[dict[str, Any]],
    seeds: tuple[int, ...],
    assigned: dict[str, int],
) -> None:
    """Teams, highest playoff_probability first, each claim the seed out of
    `seeds` their own seed_probabilities ranks highest among those unclaimed.
    """
    taken: set[int] = set()
    for t in sorted(teams, key=lambda t: -_playoff_probability(t)):
        seed_probs = t.get("seed_probabilities") or {}
        candidates = sorted(seeds, key=lambda s: -float(seed_probs.get(str(s), 0) or 0))
        for seed in candidates:
            if seed not in taken:
                taken.add(seed)
                assigned[t["team"]] = seed
                break


def assign_modal_seeds(team_results: list[dict[str, Any]], conference: str) -> dict[str, int]:
    """Greedy modal-seed assignment for one conference's Simulated bracket.

    Mirrors the NFL's bracket structure: each division's most likely winner
    claims one of seeds 1-4, then the 3 remaining teams with the highest
    playoff_probability claim seeds 5-7. A likely division winner therefore
    makes the bracket even if its playoff_probability ranks below 7th in the
    conference.

    Args:
        team_results: The simulation result's full team_results list (all
            32 teams, as produced by _serialize_simulation_result).
        conference: "AFC" or "NFC".

    Returns:
        {team_name: seed} for exactly the 7 teams assigned a seed.
    """
    conf_teams = [t for t in team_results if t.get("conference") == conference]

    divisions: dict[Any, list[dict[str, Any]]] = {}
    for t in conf_teams:
        divisions.setdefault(t.get("division"), []).append(t)

    winners = [
        max(teams, key=lambda t: (_division_title_probability(t), _playoff_probability(t)))
        for teams in divisions.values()
    ]
    winner_names = {t["team"] for t in winners}
    wild_cards = sorted(
        (t for t in conf_teams if t["team"] not in winner_names),
        key=lambda t: -_playoff_probability(t),
    )[:len(_WILD_CARD_SEEDS)]

    assigned: dict[str, int] = {}
    _claim_modal_seeds(winners, _DIVISION_WINNER_SEEDS, assigned)
    _claim_modal_seeds(wild_cards, _WILD_CARD_SEEDS, assigned)
    return assigned


def _streak_dict(streak: StreakInfo | None) -> dict[str, Any] | None:
    if streak is None:
        return None
    return {"result": streak.result, "length": streak.length}


def build_actual_conference(
    standings: list[TeamStanding],
    conference: Conference,
    games: list[Game],
    team_strengths: dict[str, float],
    eliminated: dict[str, bool],
) -> list[dict[str, Any]]:
    """Full 1-16 Actual-mode team list for one conference, ranked by
    rank_conference (the same tiebreaker engine the playoff bracket uses).
    """
    ordering = rank_conference(standings, conference, all_games=games)
    result: list[dict[str, Any]] = []
    for i, ts in enumerate(ordering, start=1):
        last5, streak = last5_and_streak(ts.team, games)
        result.append({
            "seed": i,
            "team": ts.team,
            "conference": conference.value,
            "division": ts.division.value,
            "record": f"{ts.wins}-{ts.losses}-{ts.ties}",
            "strength": round(team_strengths.get(ts.team, 1.0), 3),
            "last5": last5,
            "streak": _streak_dict(streak),
            "eliminated": eliminated.get(ts.team, False),
        })
    return result


def build_simulated_conference(
    team_results: list[dict[str, Any]],
    conference: str,
    games: list[Game],
) -> list[dict[str, Any]]:
    """Full 1-16 Simulated-mode team list for one conference: the 7 modal
    seeds from assign_modal_seeds, then everyone else ordered by their own
    playoff_probability descending.
    """
    modal_seeds = assign_modal_seeds(team_results, conference)
    conf_teams = [t for t in team_results if t.get("conference") == conference]

    def _sort_key(t: dict[str, Any]) -> tuple[int, float]:
        seed = modal_seeds.get(t["team"])
        rank = seed if seed is not None else 99
        return (rank, -float(t.get("playoff_probability", 0) or 0))

    ordered = sorted(conf_teams, key=_sort_key)

    result: list[dict[str, Any]] = []
    next_seed = 8
    for t in ordered:
        seed = modal_seeds.get(t["team"])
        if seed is None:
            seed = next_seed
            next_seed += 1
        last5, streak = last5_and_streak(t["team"], games)
        result.append({
            "seed": seed,
            "team": t["team"],
            "conference": conference,
            "division": t.get("division"),
            "record": t.get("record", "0-0-0"),
            "strength": round(float(t.get("strength_rating", 1.0) or 1.0), 3),
            "last5": last5,
            "streak": _streak_dict(streak),
            "playoff_pct": float(t.get("playoff_probability", 0.0) or 0.0),
        })
    return result
