"""NFL standings computation engine.

Computes team standings from game results and optional simulated outcomes,
including W-L-T records, win percentages, division/conference records,
games behind, and points for/against. Implements full NFL tiebreaker
procedures for both division and conference (wild card) ties.

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.13, 10.14
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum

from src.data_client import Game, GameStatus
from src.nfl_teams import NFL_TEAMS, get_team_conference, get_team_division


class Conference(Enum):
    """NFL conference."""

    AFC = "AFC"
    NFC = "NFC"


class Division(Enum):
    """NFL division."""

    EAST = "East"
    NORTH = "North"
    SOUTH = "South"
    WEST = "West"


@dataclass
class TeamStanding:
    """Complete standing record for a single NFL team.

    Attributes:
        team: Short team name (e.g., "Chiefs").
        conference: The team's conference (AFC or NFC).
        division: The team's division (East, North, South, West).
        wins: Total wins.
        losses: Total losses.
        ties: Total ties.
        win_percentage: Calculated as (W + 0.5*T) / (W+L+T), 0.0 if no games.
        division_record: W-L-T tuple for games within the team's division.
        conference_record: W-L-T tuple for games within the team's conference.
        points_for: Total points scored in completed (real) games, None if no real games.
        points_against: Total points allowed in completed (real) games, None if no real games.
        seed: Playoff seed (1-7) or None if not a playoff team.
        is_division_champion: Whether this team won its division.
        is_playoff_team: Whether this team qualifies for the playoffs.
        games_behind: Games behind the division leader.
    """

    team: str
    conference: Conference
    division: Division
    wins: int = 0
    losses: int = 0
    ties: int = 0
    win_percentage: float = 0.0
    division_record: tuple[int, int, int] = (0, 0, 0)
    conference_record: tuple[int, int, int] = (0, 0, 0)
    points_for: int | None = None
    points_against: int | None = None
    seed: int | None = None
    is_division_champion: bool = False
    is_playoff_team: bool = False
    games_behind: float = 0.0


@dataclass
class PlayoffBracket:
    """Playoff bracket with seeded teams for each conference.

    Attributes:
        afc_seeds: List of 7 TeamStanding objects for AFC, ordered by seed (1-7).
        nfc_seeds: List of 7 TeamStanding objects for NFC, ordered by seed (1-7).
    """

    afc_seeds: list[TeamStanding] = field(default_factory=list)
    nfc_seeds: list[TeamStanding] = field(default_factory=list)


def _calculate_win_percentage(wins: int, losses: int, ties: int) -> float:
    """Calculate win percentage using NFL formula.

    Formula: (W + 0.5 * T) / (W + L + T)
    Returns 0.0 if no games played (division by zero case).

    Args:
        wins: Number of wins.
        losses: Number of losses.
        ties: Number of ties.

    Returns:
        Win percentage as a float between 0.0 and 1.0.
    """
    total = wins + losses + ties
    if total == 0:
        return 0.0
    return (wins + 0.5 * ties) / total


def _calculate_games_behind(
    leader_wins: int, leader_losses: int, team_wins: int, team_losses: int
) -> float:
    """Calculate games behind the division leader.

    Formula: ((leader_W - team_W) + (team_L - leader_L)) / 2

    Args:
        leader_wins: Division leader's win count.
        leader_losses: Division leader's loss count.
        team_wins: This team's win count.
        team_losses: This team's loss count.

    Returns:
        Games behind as a float (can be 0.0 for the leader).
    """
    return ((leader_wins - team_wins) + (team_losses - leader_losses)) / 2


def compute_standings(
    games: list[Game],
    simulated_outcomes: list[tuple[str, str | None, bool]] | None = None,
) -> list[TeamStanding]:
    """Compute NFL standings from game results and optional simulated outcomes.

    Calculates W-L-T records, win percentages, division/conference records,
    points for/against, and games behind for all 32 NFL teams.

    Args:
        games: List of Game objects (completed games provide actual results and points).
        simulated_outcomes: Optional list of tuples (game_id, winning_team, is_tie)
            representing simulated game results. winning_team is the winner's name,
            or any team name if is_tie is True. For ties, winning_team can be either
            team involved. Simulated outcomes only contribute W/L/T — no point data.

    Returns:
        List of 32 TeamStanding objects, one for each NFL team.
    """
    # Initialize tracking structures for all 32 teams
    team_records: dict[str, dict[str, int]] = {}
    team_div_records: dict[str, dict[str, int]] = {}
    team_conf_records: dict[str, dict[str, int]] = {}
    team_points_for: dict[str, int] = {}
    team_points_against: dict[str, int] = {}
    team_has_real_games: dict[str, bool] = {}

    for conference_name, divisions in NFL_TEAMS.items():
        for division_name, teams in divisions.items():
            for team in teams:
                team_records[team] = {"wins": 0, "losses": 0, "ties": 0}
                team_div_records[team] = {"wins": 0, "losses": 0, "ties": 0}
                team_conf_records[team] = {"wins": 0, "losses": 0, "ties": 0}
                team_points_for[team] = 0
                team_points_against[team] = 0
                team_has_real_games[team] = False

    # Build a lookup from game_id to Game for simulated outcome processing
    game_lookup: dict[str, Game] = {g.game_id: g for g in games}

    # Build set of simulated game IDs to avoid double-counting
    simulated_game_ids: set[str] = set()
    if simulated_outcomes:
        simulated_game_ids = {game_id for game_id, _, _ in simulated_outcomes}

    # Process completed games (only those NOT being simulated)
    for game in games:
        if game.status != GameStatus.COMPLETED:
            continue

        # Skip games that will be handled by simulated_outcomes
        if game.game_id in simulated_game_ids:
            continue

        home = game.home_team
        away = game.away_team

        # Skip games involving unknown teams
        if home not in team_records or away not in team_records:
            continue

        # Determine outcome from scores
        if game.home_score is None or game.away_score is None:
            continue

        if game.home_score > game.away_score:
            winner, loser = home, away
            is_tie = False
        elif game.away_score > game.home_score:
            winner, loser = away, home
            is_tie = False
        else:
            winner, loser = home, away  # doesn't matter for ties
            is_tie = True

        # Update overall records
        if is_tie:
            team_records[home]["ties"] += 1
            team_records[away]["ties"] += 1
        else:
            team_records[winner]["wins"] += 1
            team_records[loser]["losses"] += 1

        # Update division and conference records
        _update_sub_records(
            home, away, is_tie, winner if not is_tie else None,
            team_div_records, team_conf_records,
        )

        # Update points (only from completed real games)
        if game.home_points is not None:
            team_points_for[home] += game.home_points
            team_points_against[away] += game.home_points
            team_has_real_games[home] = True
        if game.away_points is not None:
            team_points_for[away] += game.away_points
            team_points_against[home] += game.away_points
            team_has_real_games[away] = True

    # Process simulated outcomes
    if simulated_outcomes:
        for game_id, winning_team, is_tie in simulated_outcomes:
            game = game_lookup.get(game_id)
            if game is None:
                continue

            home = game.home_team
            away = game.away_team

            # Skip games involving unknown teams
            if home not in team_records or away not in team_records:
                continue

            if is_tie:
                team_records[home]["ties"] += 1
                team_records[away]["ties"] += 1
                _update_sub_records(
                    home, away, True, None,
                    team_div_records, team_conf_records,
                )
            else:
                # Determine winner and loser
                if winning_team == home:
                    winner, loser = home, away
                elif winning_team == away:
                    winner, loser = away, home
                else:
                    # winning_team doesn't match either team — skip
                    continue

                team_records[winner]["wins"] += 1
                team_records[loser]["losses"] += 1
                _update_sub_records(
                    home, away, False, winner,
                    team_div_records, team_conf_records,
                )

            # No point data for simulated outcomes

    # Build TeamStanding objects
    standings: list[TeamStanding] = []

    for conference_name, divisions in NFL_TEAMS.items():
        conf_enum = Conference(conference_name)
        for division_name, teams in divisions.items():
            div_enum = Division(division_name)
            for team in teams:
                rec = team_records[team]
                wins = rec["wins"]
                losses = rec["losses"]
                ties = rec["ties"]

                win_pct = _calculate_win_percentage(wins, losses, ties)

                div_rec = team_div_records[team]
                conf_rec = team_conf_records[team]

                pf: int | None = team_points_for[team] if team_has_real_games[team] else None
                pa: int | None = team_points_against[team] if team_has_real_games[team] else None

                standing = TeamStanding(
                    team=team,
                    conference=conf_enum,
                    division=div_enum,
                    wins=wins,
                    losses=losses,
                    ties=ties,
                    win_percentage=win_pct,
                    division_record=(div_rec["wins"], div_rec["losses"], div_rec["ties"]),
                    conference_record=(conf_rec["wins"], conf_rec["losses"], conf_rec["ties"]),
                    points_for=pf,
                    points_against=pa,
                    seed=None,
                    is_division_champion=False,
                    is_playoff_team=False,
                    games_behind=0.0,
                )
                standings.append(standing)

    # Calculate games_behind per division
    _compute_games_behind(standings)

    return standings


def _update_sub_records(
    home: str,
    away: str,
    is_tie: bool,
    winner: str | None,
    div_records: dict[str, dict[str, int]],
    conf_records: dict[str, dict[str, int]],
) -> None:
    """Update division and conference records for a game result.

    Args:
        home: Home team name.
        away: Away team name.
        is_tie: Whether the game was a tie.
        winner: Winner team name (None if tie).
        div_records: Division record tracking dict.
        conf_records: Conference record tracking dict.
    """
    home_info = get_team_division(home)
    away_info = get_team_division(away)

    if home_info is None or away_info is None:
        return

    home_conf, home_div = home_info
    away_conf, away_div = away_info

    # Check if same division
    same_division = (home_conf == away_conf and home_div == away_div)
    # Check if same conference
    same_conference = (home_conf == away_conf)

    if same_division:
        if is_tie:
            div_records[home]["ties"] += 1
            div_records[away]["ties"] += 1
        else:
            assert winner is not None
            loser = away if winner == home else home
            div_records[winner]["wins"] += 1
            div_records[loser]["losses"] += 1

    if same_conference:
        if is_tie:
            conf_records[home]["ties"] += 1
            conf_records[away]["ties"] += 1
        else:
            assert winner is not None
            loser = away if winner == home else home
            conf_records[winner]["wins"] += 1
            conf_records[loser]["losses"] += 1


@dataclass
class WildCardMatchup:
    """A Wild Card Round matchup between two seeded teams.

    Attributes:
        home_seed: Seed number of the home (higher-seeded) team.
        away_seed: Seed number of the away (lower-seeded) team.
        home_team: TeamStanding of the home team.
        away_team: TeamStanding of the away team.
    """

    home_seed: int
    away_seed: int
    home_team: TeamStanding
    away_team: TeamStanding


def _sort_teams_by_record(teams: list[TeamStanding]) -> list[TeamStanding]:
    """Sort teams by win_percentage descending, then alphabetically by name ascending.

    This is the fallback sort used when tiebreaker functions are not yet available.
    When full tiebreakers are implemented, this should be replaced with the
    conference tiebreaker procedure.

    Args:
        teams: List of TeamStanding objects to sort.

    Returns:
        New list sorted by win_percentage descending, then team name ascending.
    """
    return sorted(teams, key=lambda t: (-t.win_percentage, t.team))


def determine_playoff_bracket(standings: list[TeamStanding]) -> PlayoffBracket:
    """Determine the 7-team playoff bracket for each conference.

    Selects 4 division champions (best record per division) seeded 1-4 by overall
    record, and 3 wild card teams (best remaining conference records) seeded 5-7.
    Updates TeamStanding objects in place (sets seed, is_division_champion, is_playoff_team).

    The #1 seed in each conference receives a first-round bye.
    Wild Card Round pairings: 2v7, 3v6, 4v5 (higher seed hosts).

    Args:
        standings: List of 32 TeamStanding objects (output of compute_standings).

    Returns:
        PlayoffBracket with afc_seeds and nfc_seeds lists (7 teams each, ordered by seed).
    """
    bracket = PlayoffBracket()

    for conf in (Conference.AFC, Conference.NFC):
        # Get all teams in this conference
        conf_teams = [s for s in standings if s.conference == conf]

        # Step 1: Determine division champions (best record per division)
        division_champions: list[TeamStanding] = []
        remaining_teams: list[TeamStanding] = []

        for div in Division:
            div_teams = [t for t in conf_teams if t.division == div]
            if not div_teams:
                continue

            # Sort by win_percentage descending, alphabetical as tiebreaker
            sorted_div = _sort_teams_by_record(div_teams)
            champion = sorted_div[0]
            champion.is_division_champion = True
            division_champions.append(champion)
            remaining_teams.extend(sorted_div[1:])

        # Step 2: Seed division champions 1-4 by overall record
        # (with conference tiebreakers — using win_percentage + alphabetical as fallback)
        seeded_champions = _sort_teams_by_record(division_champions)

        # Step 3: Select 3 wild card teams from remaining conference teams
        sorted_remaining = _sort_teams_by_record(remaining_teams)
        wild_card_teams = sorted_remaining[:3]

        # Step 4: Assign seeds and mark playoff teams
        seeds: list[TeamStanding] = []
        for i, team in enumerate(seeded_champions, start=1):
            team.seed = i
            team.is_playoff_team = True
            seeds.append(team)

        for i, team in enumerate(wild_card_teams, start=5):
            team.seed = i
            team.is_playoff_team = True
            seeds.append(team)

        # Assign to bracket
        if conf == Conference.AFC:
            bracket.afc_seeds = seeds
        else:
            bracket.nfc_seeds = seeds

    return bracket


def get_wild_card_matchups(bracket: PlayoffBracket) -> dict[str, list[WildCardMatchup]]:
    """Construct Wild Card Round pairings from a playoff bracket.

    Pairings: 2v7, 3v6, 4v5 (higher seed hosts each game).
    The #1 seed receives a first-round bye and does not play.

    Args:
        bracket: PlayoffBracket with seeded teams for each conference.

    Returns:
        Dictionary with keys "AFC" and "NFC", each containing a list of 3
        WildCardMatchup objects.
    """
    matchups: dict[str, list[WildCardMatchup]] = {"AFC": [], "NFC": []}

    for conf_key, seeds in [("AFC", bracket.afc_seeds), ("NFC", bracket.nfc_seeds)]:
        if len(seeds) < 7:
            continue

        # Build seed lookup (seeds list is ordered 1-7)
        seed_map = {team.seed: team for team in seeds}

        # Wild Card pairings: 2v7, 3v6, 4v5
        pairings = [(2, 7), (3, 6), (4, 5)]
        for home_seed, away_seed in pairings:
            home_team = seed_map[home_seed]
            away_team = seed_map[away_seed]
            matchups[conf_key].append(
                WildCardMatchup(
                    home_seed=home_seed,
                    away_seed=away_seed,
                    home_team=home_team,
                    away_team=away_team,
                )
            )

    return matchups


def _compute_games_behind(standings: list[TeamStanding]) -> None:
    """Compute games_behind for each team relative to their division leader.

    Modifies standings in place.

    Args:
        standings: List of TeamStanding objects to update.
    """
    # Group by conference and division
    division_groups: dict[tuple[Conference, Division], list[TeamStanding]] = {}
    for standing in standings:
        key = (standing.conference, standing.division)
        if key not in division_groups:
            division_groups[key] = []
        division_groups[key].append(standing)

    # For each division, find the leader and compute games behind
    for _div_key, div_standings in division_groups.items():
        # Find the leader (highest win percentage)
        leader = max(div_standings, key=lambda s: s.win_percentage)

        for standing in div_standings:
            standing.games_behind = _calculate_games_behind(
                leader.wins, leader.losses, standing.wins, standing.losses
            )


# ---------------------------------------------------------------------------
# Tiebreaker Implementation
# ---------------------------------------------------------------------------


def _get_games_between(
    teams: list[str], all_games: list[Game], simulated_game_ids: set[str]
) -> list[Game]:
    """Return completed games played between the specified teams.

    Args:
        teams: List of team names to filter for.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.

    Returns:
        List of games where both home and away teams are in the teams list.
    """
    team_set = set(teams)
    return [
        g for g in all_games
        if g.home_team in team_set
        and g.away_team in team_set
        and (g.status == GameStatus.COMPLETED or g.game_id in simulated_game_ids)
    ]


def _get_record_in_games(
    team: str, games: list[Game], simulated_game_ids: set[str]
) -> tuple[int, int, int]:
    """Compute a team's W-L-T record in a subset of games.

    Args:
        team: Team name.
        games: Subset of games to compute record from.
        simulated_game_ids: Set of game IDs that were simulated.

    Returns:
        Tuple of (wins, losses, ties).
    """
    wins, losses, ties = 0, 0, 0
    for g in games:
        if g.home_team != team and g.away_team != team:
            continue
        if g.status != GameStatus.COMPLETED and g.game_id not in simulated_game_ids:
            continue
        if g.home_score is not None and g.away_score is not None:
            if g.home_score == g.away_score:
                ties += 1
            elif (g.home_team == team and g.home_score > g.away_score) or \
                 (g.away_team == team and g.away_score > g.home_score):
                wins += 1
            else:
                losses += 1
        elif g.game_id in simulated_game_ids:
            # Simulated game without scores — need to infer from context
            # This case shouldn't normally happen since simulated games
            # are tracked via simulated_outcomes, but handle gracefully
            ties += 1
    return (wins, losses, ties)


def _get_opponents(team: str, all_games: list[Game], simulated_game_ids: set[str]) -> list[str]:
    """Get all opponents a team has played against (completed or simulated).

    Args:
        team: Team name.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.

    Returns:
        List of opponent team names (may contain duplicates for multiple games).
    """
    opponents: list[str] = []
    for g in all_games:
        if g.status != GameStatus.COMPLETED and g.game_id not in simulated_game_ids:
            continue
        if g.home_team == team:
            opponents.append(g.away_team)
        elif g.away_team == team:
            opponents.append(g.home_team)
    return opponents


def _get_common_opponents(
    teams: list[str], all_games: list[Game], simulated_game_ids: set[str]
) -> set[str]:
    """Find opponents that all specified teams have played.

    Args:
        teams: List of team names.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.

    Returns:
        Set of team names that all specified teams have played against.
    """
    if not teams:
        return set()

    opponent_sets: list[set[str]] = []
    for team in teams:
        opps = set(_get_opponents(team, all_games, simulated_game_ids))
        # Remove the tied teams themselves from opponents
        opps -= set(teams)
        opponent_sets.append(opps)

    # Intersection of all opponent sets
    common = opponent_sets[0]
    for opp_set in opponent_sets[1:]:
        common = common & opp_set
    return common


def _get_games_against_opponents(
    team: str,
    opponents: set[str],
    all_games: list[Game],
    simulated_game_ids: set[str],
) -> list[Game]:
    """Get all games a team played against a specific set of opponents.

    Args:
        team: Team name.
        opponents: Set of opponent names to filter for.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.

    Returns:
        List of games involving the team and any of the specified opponents.
    """
    result: list[Game] = []
    for g in all_games:
        if g.status != GameStatus.COMPLETED and g.game_id not in simulated_game_ids:
            continue
        if g.home_team == team and g.away_team in opponents:
            result.append(g)
        elif g.away_team == team and g.home_team in opponents:
            result.append(g)
    return result


def _get_teams_beaten(
    team: str, all_games: list[Game], simulated_game_ids: set[str]
) -> list[str]:
    """Get all teams that a team has beaten (including duplicates for multiple wins).

    Args:
        team: Team name.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.

    Returns:
        List of team names beaten (may contain duplicates).
    """
    beaten: list[str] = []
    for g in all_games:
        if g.status != GameStatus.COMPLETED and g.game_id not in simulated_game_ids:
            continue
        if g.home_team == team and g.home_score is not None and g.away_score is not None:
            if g.home_score > g.away_score:
                beaten.append(g.away_team)
        elif g.away_team == team and g.home_score is not None and g.away_score is not None:
            if g.away_score > g.home_score:
                beaten.append(g.home_team)
    return beaten


def _compute_team_overall_record(
    team: str, all_games: list[Game], simulated_game_ids: set[str]
) -> tuple[int, int, int]:
    """Compute a team's overall W-L-T record from all played games.

    Args:
        team: Team name.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.

    Returns:
        Tuple of (wins, losses, ties).
    """
    wins, losses, ties = 0, 0, 0
    for g in all_games:
        if g.status != GameStatus.COMPLETED and g.game_id not in simulated_game_ids:
            continue
        if g.home_team != team and g.away_team != team:
            continue
        if g.home_score is not None and g.away_score is not None:
            if g.home_score == g.away_score:
                ties += 1
            elif (g.home_team == team and g.home_score > g.away_score) or \
                 (g.away_team == team and g.away_score > g.home_score):
                wins += 1
            else:
                losses += 1
    return (wins, losses, ties)


def _strength_of_victory(
    team: str, all_games: list[Game], simulated_game_ids: set[str]
) -> float:
    """Compute strength of victory: combined win% of all teams beaten.

    Args:
        team: Team name.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.

    Returns:
        Combined win percentage of all teams beaten, or 0.0 if no wins.
    """
    beaten = _get_teams_beaten(team, all_games, simulated_game_ids)
    if not beaten:
        return 0.0

    total_wins = 0
    total_losses = 0
    total_ties = 0
    for opp in set(beaten):
        w, l, t = _compute_team_overall_record(opp, all_games, simulated_game_ids)
        total_wins += w
        total_losses += l
        total_ties += t

    return _calculate_win_percentage(total_wins, total_losses, total_ties)


def _strength_of_schedule(
    team: str, all_games: list[Game], simulated_game_ids: set[str]
) -> float:
    """Compute strength of schedule: combined win% of all opponents.

    Args:
        team: Team name.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.

    Returns:
        Combined win percentage of all opponents, or 0.0 if no games played.
    """
    opponents = _get_opponents(team, all_games, simulated_game_ids)
    if not opponents:
        return 0.0

    total_wins = 0
    total_losses = 0
    total_ties = 0
    for opp in set(opponents):
        w, l, t = _compute_team_overall_record(opp, all_games, simulated_game_ids)
        total_wins += w
        total_losses += l
        total_ties += t

    return _calculate_win_percentage(total_wins, total_losses, total_ties)


def _has_simulated_games(game_ids: set[str], simulated_game_ids: set[str]) -> bool:
    """Check if any of the given game IDs are simulated.

    Args:
        game_ids: Set of game IDs to check.
        simulated_game_ids: Set of game IDs that were simulated.

    Returns:
        True if any game in game_ids is simulated.
    """
    return bool(game_ids & simulated_game_ids)


def _get_all_game_ids_for_team(
    team: str, all_games: list[Game], simulated_game_ids: set[str]
) -> set[str]:
    """Get all game IDs for games a team has played (completed or simulated).

    Args:
        team: Team name.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.

    Returns:
        Set of game IDs.
    """
    return {
        g.game_id for g in all_games
        if (g.home_team == team or g.away_team == team)
        and (g.status == GameStatus.COMPLETED or g.game_id in simulated_game_ids)
    }


def _net_points(
    team: str, games: list[Game], simulated_game_ids: set[str]
) -> int | None:
    """Compute net points (points for - points against) for a team in given games.

    Returns None if any game in the set is simulated (no point data available).

    Args:
        team: Team name.
        games: Games to compute net points from.
        simulated_game_ids: Set of game IDs that were simulated.

    Returns:
        Net points as integer, or None if point data unavailable.
    """
    game_ids = {g.game_id for g in games if g.home_team == team or g.away_team == team}
    if _has_simulated_games(game_ids, simulated_game_ids):
        return None

    net = 0
    for g in games:
        if g.home_team != team and g.away_team != team:
            continue
        if g.status != GameStatus.COMPLETED:
            continue
        if g.home_points is None or g.away_points is None:
            return None
        if g.home_team == team:
            net += g.home_points - g.away_points
        else:
            net += g.away_points - g.home_points
    return net


def _points_scored_and_allowed(
    team: str, games: list[Game], simulated_game_ids: set[str], conference_only: bool = False
) -> tuple[int, int] | None:
    """Compute total points scored and points allowed for a team.

    Returns None if any relevant game is simulated (no point data available).

    Args:
        team: Team name.
        games: Games to compute from.
        simulated_game_ids: Set of game IDs that were simulated.
        conference_only: If True, only count games within the team's conference.

    Returns:
        Tuple of (points_for, points_against) or None if data unavailable.
    """
    team_conf = get_team_conference(team)
    points_for = 0
    points_against = 0

    for g in games:
        if g.home_team != team and g.away_team != team:
            continue
        if g.status != GameStatus.COMPLETED and g.game_id not in simulated_game_ids:
            continue

        # Check if simulated
        if g.game_id in simulated_game_ids:
            return None

        if conference_only:
            opp = g.away_team if g.home_team == team else g.home_team
            opp_conf = get_team_conference(opp)
            if opp_conf != team_conf:
                continue

        if g.home_points is None or g.away_points is None:
            return None

        if g.home_team == team:
            points_for += g.home_points
            points_against += g.away_points
        else:
            points_for += g.away_points
            points_against += g.home_points

    return (points_for, points_against)


def _step_head_to_head(
    teams: list[str],
    all_games: list[Game],
    simulated_game_ids: set[str],
    require_all_played: bool = False,
) -> list[str] | None:
    """Tiebreaker step: head-to-head record among tied teams.

    For division ties, head-to-head is always applicable.
    For conference ties, head-to-head only applies if ALL tied teams
    have played each other (require_all_played=True).

    Args:
        teams: List of tied team names.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.
        require_all_played: If True, only apply if all teams played each other.

    Returns:
        Teams sorted by head-to-head win%, or None if tie not broken.
    """
    if len(teams) < 2:
        return teams

    h2h_games = _get_games_between(teams, all_games, simulated_game_ids)

    if require_all_played:
        # Check that every pair of teams has played at least one game
        for i, t1 in enumerate(teams):
            for t2 in teams[i + 1:]:
                pair_games = [
                    g for g in h2h_games
                    if (g.home_team == t1 and g.away_team == t2)
                    or (g.home_team == t2 and g.away_team == t1)
                ]
                if not pair_games:
                    return None  # Not all teams played each other

    if not h2h_games:
        return None

    # Compute win% for each team in head-to-head games
    records: dict[str, tuple[int, int, int]] = {}
    for team in teams:
        records[team] = _get_record_in_games(team, h2h_games, simulated_game_ids)

    win_pcts: dict[str, float] = {}
    for team, (w, l, t) in records.items():
        win_pcts[team] = _calculate_win_percentage(w, l, t)

    # Check if there's differentiation
    pct_values = list(win_pcts.values())
    if len(set(pct_values)) == 1:
        return None  # All tied in head-to-head

    # Sort by win% descending
    sorted_teams = sorted(teams, key=lambda t: win_pcts[t], reverse=True)
    return sorted_teams


def _step_division_record(
    teams: list[str],
    all_games: list[Game],
    simulated_game_ids: set[str],
) -> list[str] | None:
    """Tiebreaker step: record within the division.

    Args:
        teams: List of tied team names.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.

    Returns:
        Teams sorted by division win%, or None if tie not broken.
    """
    # Get division games for each team
    win_pcts: dict[str, float] = {}
    for team in teams:
        team_info = get_team_division(team)
        if team_info is None:
            return None
        conf, div = team_info
        # Get all division opponents
        div_teams = NFL_TEAMS.get(conf, {}).get(div, [])
        div_opponents = set(div_teams) - {team}

        div_games = _get_games_against_opponents(
            team, div_opponents, all_games, simulated_game_ids
        )
        w, l, t = _get_record_in_games(team, div_games, simulated_game_ids)
        win_pcts[team] = _calculate_win_percentage(w, l, t)

    pct_values = list(win_pcts.values())
    if len(set(pct_values)) == 1:
        return None

    sorted_teams = sorted(teams, key=lambda t: win_pcts[t], reverse=True)
    return sorted_teams


def _step_common_games(
    teams: list[str],
    all_games: list[Game],
    simulated_game_ids: set[str],
    min_common: int = 0,
) -> list[str] | None:
    """Tiebreaker step: record in common games.

    Args:
        teams: List of tied team names.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.
        min_common: Minimum number of common opponents required (4 for conference).

    Returns:
        Teams sorted by common games win%, or None if tie not broken.
    """
    common_opps = _get_common_opponents(teams, all_games, simulated_game_ids)

    if len(common_opps) < min_common:
        return None

    if not common_opps:
        return None

    win_pcts: dict[str, float] = {}
    for team in teams:
        common_games = _get_games_against_opponents(
            team, common_opps, all_games, simulated_game_ids
        )
        w, l, t = _get_record_in_games(team, common_games, simulated_game_ids)
        win_pcts[team] = _calculate_win_percentage(w, l, t)

    pct_values = list(win_pcts.values())
    if len(set(pct_values)) == 1:
        return None

    sorted_teams = sorted(teams, key=lambda t: win_pcts[t], reverse=True)
    return sorted_teams


def _step_conference_record(
    teams: list[str],
    all_games: list[Game],
    simulated_game_ids: set[str],
) -> list[str] | None:
    """Tiebreaker step: record within the conference.

    Args:
        teams: List of tied team names.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.

    Returns:
        Teams sorted by conference win%, or None if tie not broken.
    """
    win_pcts: dict[str, float] = {}
    for team in teams:
        team_conf = get_team_conference(team)
        if team_conf is None:
            return None
        # Get all conference opponents
        conf_teams: set[str] = set()
        for div_teams in NFL_TEAMS.get(team_conf, {}).values():
            conf_teams.update(div_teams)
        conf_opponents = conf_teams - {team}

        conf_games = _get_games_against_opponents(
            team, conf_opponents, all_games, simulated_game_ids
        )
        w, l, t = _get_record_in_games(team, conf_games, simulated_game_ids)
        win_pcts[team] = _calculate_win_percentage(w, l, t)

    pct_values = list(win_pcts.values())
    if len(set(pct_values)) == 1:
        return None

    sorted_teams = sorted(teams, key=lambda t: win_pcts[t], reverse=True)
    return sorted_teams


def _step_strength_of_victory(
    teams: list[str],
    all_games: list[Game],
    simulated_game_ids: set[str],
) -> list[str] | None:
    """Tiebreaker step: strength of victory (combined win% of teams beaten).

    Args:
        teams: List of tied team names.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.

    Returns:
        Teams sorted by SOV, or None if tie not broken.
    """
    sovs: dict[str, float] = {}
    for team in teams:
        sovs[team] = _strength_of_victory(team, all_games, simulated_game_ids)

    sov_values = list(sovs.values())
    if len(set(sov_values)) == 1:
        return None

    sorted_teams = sorted(teams, key=lambda t: sovs[t], reverse=True)
    return sorted_teams


def _step_strength_of_schedule(
    teams: list[str],
    all_games: list[Game],
    simulated_game_ids: set[str],
) -> list[str] | None:
    """Tiebreaker step: strength of schedule (combined win% of all opponents).

    Args:
        teams: List of tied team names.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.

    Returns:
        Teams sorted by SOS, or None if tie not broken.
    """
    soss: dict[str, float] = {}
    for team in teams:
        soss[team] = _strength_of_schedule(team, all_games, simulated_game_ids)

    sos_values = list(soss.values())
    if len(set(sos_values)) == 1:
        return None

    sorted_teams = sorted(teams, key=lambda t: soss[t], reverse=True)
    return sorted_teams


def _step_point_differential(
    teams: list[str],
    all_games: list[Game],
    simulated_game_ids: set[str],
    conference_only: bool = False,
) -> list[str] | None:
    """Tiebreaker step: combined ranking in points scored and points allowed.

    Skipped entirely if any relevant games are simulated (no point data).

    Args:
        teams: List of tied team names.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.
        conference_only: If True, only use conference games.

    Returns:
        Teams sorted by point differential, or None if tie not broken or skipped.
    """
    differentials: dict[str, int] = {}
    for team in teams:
        result = _points_scored_and_allowed(
            team, all_games, simulated_game_ids, conference_only=conference_only
        )
        if result is None:
            return None  # Skip — simulated games involved
        pf, pa = result
        differentials[team] = pf - pa

    diff_values = list(differentials.values())
    if len(set(diff_values)) == 1:
        return None

    sorted_teams = sorted(teams, key=lambda t: differentials[t], reverse=True)
    return sorted_teams


def _step_net_points_common_games(
    teams: list[str],
    all_games: list[Game],
    simulated_game_ids: set[str],
) -> list[str] | None:
    """Tiebreaker step: net points in common games.

    Skipped entirely if any common games are simulated (no point data).

    Args:
        teams: List of tied team names.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.

    Returns:
        Teams sorted by net points in common games, or None if tie not broken or skipped.
    """
    common_opps = _get_common_opponents(teams, all_games, simulated_game_ids)
    if not common_opps:
        return None

    net_pts: dict[str, int] = {}
    for team in teams:
        common_games = _get_games_against_opponents(
            team, common_opps, all_games, simulated_game_ids
        )
        result = _net_points(team, common_games, simulated_game_ids)
        if result is None:
            return None  # Skip — simulated games involved
        net_pts[team] = result

    net_values = list(net_pts.values())
    if len(set(net_values)) == 1:
        return None

    sorted_teams = sorted(teams, key=lambda t: net_pts[t], reverse=True)
    return sorted_teams


def _step_net_points_all_games(
    teams: list[str],
    all_games: list[Game],
    simulated_game_ids: set[str],
) -> list[str] | None:
    """Tiebreaker step: net points in all games.

    Skipped entirely if any games are simulated (no point data).

    Args:
        teams: List of tied team names.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.

    Returns:
        Teams sorted by net points in all games, or None if tie not broken or skipped.
    """
    net_pts: dict[str, int] = {}
    for team in teams:
        team_games = [
            g for g in all_games
            if (g.home_team == team or g.away_team == team)
            and (g.status == GameStatus.COMPLETED or g.game_id in simulated_game_ids)
        ]
        result = _net_points(team, team_games, simulated_game_ids)
        if result is None:
            return None  # Skip — simulated games involved
        net_pts[team] = result

    net_values = list(net_pts.values())
    if len(set(net_values)) == 1:
        return None

    sorted_teams = sorted(teams, key=lambda t: net_pts[t], reverse=True)
    return sorted_teams


def _step_coin_toss(teams: list[str]) -> list[str]:
    """Tiebreaker step: coin toss (random selection) as final fallback.

    Uses random.random() to produce a random ordering.

    Args:
        teams: List of tied team names.

    Returns:
        Teams in random order.
    """
    shuffled = list(teams)
    random.shuffle(shuffled)
    return shuffled


def _apply_tiebreaker_steps(
    teams: list[str],
    all_games: list[Game],
    simulated_game_ids: set[str],
    context: str,
) -> list[str]:
    """Apply tiebreaker steps in order for the given context.

    This applies the steps once (no multi-team restart logic).

    Args:
        teams: List of tied team names.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.
        context: Either 'division' or 'conference'.

    Returns:
        Teams sorted by tiebreaker result.
    """
    if len(teams) <= 1:
        return list(teams)

    if context == "division":
        steps = _get_division_steps()
    else:
        steps = _get_conference_steps()

    for step_fn in steps:
        result = step_fn(teams, all_games, simulated_game_ids)
        if result is not None:
            return result

    # Final fallback: coin toss
    return _step_coin_toss(teams)


def _get_division_steps():
    """Return the ordered list of division tiebreaker step functions.

    Division tiebreaker order:
    1. Head-to-head record
    2. Division record
    3. Common games record
    4. Conference record
    5. Strength of victory
    6. Strength of schedule
    7. Point differential (conference games) — skip if simulated
    8. Point differential (all games) — skip if simulated
    9. Net points in common games — skip if simulated
    10. Net points in all games — skip if simulated
    11. Coin toss (handled as fallback)

    Returns:
        List of step functions with signature (teams, all_games, sim_ids) -> list | None.
    """
    def step_h2h(teams, all_games, sim_ids):
        return _step_head_to_head(teams, all_games, sim_ids, require_all_played=False)

    def step_div(teams, all_games, sim_ids):
        return _step_division_record(teams, all_games, sim_ids)

    def step_common(teams, all_games, sim_ids):
        return _step_common_games(teams, all_games, sim_ids, min_common=0)

    def step_conf(teams, all_games, sim_ids):
        return _step_conference_record(teams, all_games, sim_ids)

    def step_sov(teams, all_games, sim_ids):
        return _step_strength_of_victory(teams, all_games, sim_ids)

    def step_sos(teams, all_games, sim_ids):
        return _step_strength_of_schedule(teams, all_games, sim_ids)

    def step_pts_conf(teams, all_games, sim_ids):
        return _step_point_differential(teams, all_games, sim_ids, conference_only=True)

    def step_pts_all(teams, all_games, sim_ids):
        return _step_point_differential(teams, all_games, sim_ids, conference_only=False)

    def step_net_common(teams, all_games, sim_ids):
        return _step_net_points_common_games(teams, all_games, sim_ids)

    def step_net_all(teams, all_games, sim_ids):
        return _step_net_points_all_games(teams, all_games, sim_ids)

    return [
        step_h2h, step_div, step_common, step_conf,
        step_sov, step_sos, step_pts_conf, step_pts_all,
        step_net_common, step_net_all,
    ]


def _get_conference_steps():
    """Return the ordered list of conference tiebreaker step functions.

    Conference (wild card) tiebreaker order:
    1. Head-to-head record (only if all tied teams played each other)
    2. Conference record
    3. Common games record (minimum 4 common opponents)
    4. Strength of victory
    5. Strength of schedule
    6. Point differential (conference games) — skip if simulated
    7. Point differential (all games) — skip if simulated
    8. Net points in common games — skip if simulated
    9. Net points in all games — skip if simulated
    10. Coin toss (handled as fallback)

    Returns:
        List of step functions with signature (teams, all_games, sim_ids) -> list | None.
    """
    def step_h2h(teams, all_games, sim_ids):
        return _step_head_to_head(teams, all_games, sim_ids, require_all_played=True)

    def step_conf(teams, all_games, sim_ids):
        return _step_conference_record(teams, all_games, sim_ids)

    def step_common(teams, all_games, sim_ids):
        return _step_common_games(teams, all_games, sim_ids, min_common=4)

    def step_sov(teams, all_games, sim_ids):
        return _step_strength_of_victory(teams, all_games, sim_ids)

    def step_sos(teams, all_games, sim_ids):
        return _step_strength_of_schedule(teams, all_games, sim_ids)

    def step_pts_conf(teams, all_games, sim_ids):
        return _step_point_differential(teams, all_games, sim_ids, conference_only=True)

    def step_pts_all(teams, all_games, sim_ids):
        return _step_point_differential(teams, all_games, sim_ids, conference_only=False)

    def step_net_common(teams, all_games, sim_ids):
        return _step_net_points_common_games(teams, all_games, sim_ids)

    def step_net_all(teams, all_games, sim_ids):
        return _step_net_points_all_games(teams, all_games, sim_ids)

    return [
        step_h2h, step_conf, step_common,
        step_sov, step_sos, step_pts_conf, step_pts_all,
        step_net_common, step_net_all,
    ]


def break_tie(
    tied_teams: list[str],
    all_games: list[Game],
    simulated_game_ids: set[str],
    context: str = "division",
) -> list[str]:
    """Break a tie between teams using NFL tiebreaker procedures.

    Implements multi-team tie handling: applies tiebreaker steps collectively.
    If a step eliminates one or more teams from the group (i.e., produces a
    clear best or worst team), the procedure restarts from step 1 for the
    remaining tied teams.

    Args:
        tied_teams: List of team names that are tied in win percentage.
        all_games: All games in the season (completed and simulated).
        simulated_game_ids: Set of game IDs that were simulated (no point data).
        context: Either 'division' or 'conference' to determine which
            tiebreaker procedure to apply.

    Returns:
        Teams in tiebreaker order (best first).
    """
    if len(tied_teams) <= 1:
        return list(tied_teams)

    if len(tied_teams) == 2:
        # Two-team tie: apply steps directly, no restart needed
        return _apply_tiebreaker_steps(tied_teams, all_games, simulated_game_ids, context)

    # Multi-team tie (3+): apply collectively with restart logic
    return _break_multi_team_tie(tied_teams, all_games, simulated_game_ids, context)


def _break_multi_team_tie(
    tied_teams: list[str],
    all_games: list[Game],
    simulated_game_ids: set[str],
    context: str,
) -> list[str]:
    """Break a multi-team tie with restart logic.

    When 3+ teams are tied, apply tiebreaker steps collectively.
    If a step produces differentiation (not all teams have the same value),
    check if one team is clearly separated. If so, place that team and
    restart from step 1 for the remaining teams.

    Args:
        tied_teams: List of 3+ tied team names.
        all_games: All games in the season.
        simulated_game_ids: Set of game IDs that were simulated.
        context: Either 'division' or 'conference'.

    Returns:
        Teams in tiebreaker order (best first).
    """
    remaining = list(tied_teams)
    result: list[str] = []

    while len(remaining) > 1:
        if context == "division":
            steps = _get_division_steps()
        else:
            steps = _get_conference_steps()

        resolved_this_round = False

        for step_fn in steps:
            step_result = step_fn(remaining, all_games, simulated_game_ids)
            if step_result is None:
                continue

            # Step produced an ordering — check if top team is separated
            # The step returns all teams sorted. If the best team is clearly
            # ahead (different value from #2), we can extract them.
            # We need to re-check by seeing if the step differentiates.
            # Since the step returned non-None, there IS differentiation.

            # Extract the best team (first in sorted order)
            best_team = step_result[0]
            result.append(best_team)
            remaining.remove(best_team)
            resolved_this_round = True
            break  # Restart from step 1 with remaining teams

        if not resolved_this_round:
            # No step could break the tie — use coin toss for all remaining
            coin_result = _step_coin_toss(remaining)
            result.extend(coin_result)
            remaining = []

    # Add the last remaining team
    if remaining:
        result.extend(remaining)

    return result
