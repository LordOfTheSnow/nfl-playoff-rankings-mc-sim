"""Hypothesis strategies for generating W-L-T records and team strength ratings."""

from hypothesis import strategies as st

from src.nfl_teams import ALL_TEAMS


# Maximum games in an NFL regular season
MAX_GAMES = 17


@st.composite
def wlt_record(draw: st.DrawFn, max_total: int = MAX_GAMES) -> tuple[int, int, int]:
    """Generate a valid W-L-T record where wins + losses + ties <= max_total.

    Returns:
        Tuple of (wins, losses, ties) with non-negative integers summing to <= max_total.
    """
    total_games = draw(st.integers(min_value=0, max_value=max_total))
    wins = draw(st.integers(min_value=0, max_value=total_games))
    remaining = total_games - wins
    ties = draw(st.integers(min_value=0, max_value=remaining))
    losses = remaining - ties
    return (wins, losses, ties)


@st.composite
def team_strength_rating(draw: st.DrawFn) -> float:
    """Generate a valid team strength rating.

    Team strength ratings are positive floats centered around 1.0.
    Typical range is approximately 0.3 to 2.5.
    """
    return draw(st.floats(min_value=0.1, max_value=3.0, allow_nan=False, allow_infinity=False))


@st.composite
def team_strength_ratings(
    draw: st.DrawFn,
    teams: list[str] | None = None,
    min_teams: int = 2,
    max_teams: int = 32,
) -> dict[str, float]:
    """Generate a dictionary of team strength ratings.

    Args:
        teams: Specific team names to use. If None, randomly selects from ALL_TEAMS.
        min_teams: Minimum number of teams (used when teams is None).
        max_teams: Maximum number of teams (used when teams is None).

    Returns:
        Dictionary mapping team name to strength rating (positive float around 1.0).
    """
    if teams is not None:
        team_list = teams
    else:
        num_teams = draw(st.integers(min_value=min_teams, max_value=min(max_teams, len(ALL_TEAMS))))
        team_list = draw(
            st.lists(
                st.sampled_from(ALL_TEAMS),
                min_size=num_teams,
                max_size=num_teams,
                unique=True,
            )
        )

    ratings = {}
    for team in team_list:
        ratings[team] = draw(team_strength_rating())

    return ratings


@st.composite
def normalized_team_strength_ratings(
    draw: st.DrawFn,
    teams: list[str] | None = None,
) -> dict[str, float]:
    """Generate team strength ratings normalized so the average is 1.0.

    This matches the output format of the TeamStrengthCalculator.

    Args:
        teams: Specific team names to use. If None, uses all 32 NFL teams.

    Returns:
        Dictionary mapping team name to normalized strength rating.
    """
    if teams is None:
        teams = ALL_TEAMS

    raw_ratings = draw(team_strength_ratings(teams=teams))

    # Normalize so average is 1.0
    if not raw_ratings:
        return raw_ratings

    avg = sum(raw_ratings.values()) / len(raw_ratings)
    if avg == 0:
        return {team: 1.0 for team in raw_ratings}

    return {team: rating / avg for team, rating in raw_ratings.items()}


@st.composite
def win_percentage(draw: st.DrawFn) -> float:
    """Generate a valid win percentage (0.000 to 1.000)."""
    return draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))


@st.composite
def division_standings(
    draw: st.DrawFn,
    teams: list[str] | None = None,
) -> list[tuple[str, int, int, int]]:
    """Generate standings for a 4-team division.

    Args:
        teams: List of 4 team names. If None, picks 4 random teams.

    Returns:
        List of (team, wins, losses, ties) tuples for 4 teams.
    """
    if teams is None:
        team_list = draw(
            st.lists(st.sampled_from(ALL_TEAMS), min_size=4, max_size=4, unique=True)
        )
    else:
        team_list = teams

    standings = []
    for team in team_list:
        w, l, t = draw(wlt_record())
        standings.append((team, w, l, t))

    return standings
