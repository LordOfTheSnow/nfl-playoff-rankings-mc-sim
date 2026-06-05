"""Hypothesis strategies for generating valid Game objects."""

from datetime import date

from hypothesis import strategies as st

from src.data_client import Game, GameStatus
from src.nfl_teams import ALL_TEAMS


# Strategy for generating a valid NFL team name
team_name = st.sampled_from(ALL_TEAMS)

# Strategy for generating two distinct teams (home and away)
team_pair = st.tuples(team_name, team_name).filter(lambda t: t[0] != t[1])

# Strategy for generating a valid week number (1-18)
week_number = st.integers(min_value=1, max_value=18)

# Strategy for generating a valid game date within a plausible NFL season
game_date = st.dates(
    min_value=date(2020, 9, 1),
    max_value=date(2030, 2, 28),
)

# Strategy for generating a valid game ID
game_id = st.text(
    alphabet=st.characters(categories=("Nd", "Lu")),
    min_size=6,
    max_size=12,
)

# Strategy for generating a valid score (0-70 is a reasonable NFL range)
score = st.integers(min_value=0, max_value=70)

# Strategy for generating a valid quarter (1-5, where 5 = overtime)
quarter = st.sampled_from(["1", "2", "3", "4", "OT"])

# Strategy for generating a valid game clock string
clock = st.builds(
    lambda m, s: f"{m}:{s:02d}",
    st.integers(min_value=0, max_value=15),
    st.integers(min_value=0, max_value=59),
)

# Strategy for generating any GameStatus
game_status = st.sampled_from(list(GameStatus))


@st.composite
def completed_game(draw: st.DrawFn) -> Game:
    """Generate a completed Game with valid scores."""
    home, away = draw(team_pair)
    return Game(
        game_id=draw(game_id),
        week=draw(week_number),
        date=draw(game_date),
        home_team=home,
        away_team=away,
        status=GameStatus.COMPLETED,
        home_score=draw(score),
        away_score=draw(score),
        home_points=draw(score),
        away_points=draw(score),
        quarter=None,
        clock=None,
    )


@st.composite
def scheduled_game(draw: st.DrawFn) -> Game:
    """Generate a scheduled Game with no scores."""
    home, away = draw(team_pair)
    return Game(
        game_id=draw(game_id),
        week=draw(week_number),
        date=draw(game_date),
        home_team=home,
        away_team=away,
        status=GameStatus.SCHEDULED,
        home_score=None,
        away_score=None,
        home_points=None,
        away_points=None,
        quarter=None,
        clock=None,
    )


@st.composite
def in_progress_game(draw: st.DrawFn) -> Game:
    """Generate an in-progress Game with current scores and game clock."""
    home, away = draw(team_pair)
    return Game(
        game_id=draw(game_id),
        week=draw(week_number),
        date=draw(game_date),
        home_team=home,
        away_team=away,
        status=GameStatus.IN_PROGRESS,
        home_score=draw(score),
        away_score=draw(score),
        home_points=draw(score),
        away_points=draw(score),
        quarter=draw(quarter),
        clock=draw(clock),
    )


@st.composite
def postponed_game(draw: st.DrawFn) -> Game:
    """Generate a postponed Game."""
    home, away = draw(team_pair)
    return Game(
        game_id=draw(game_id),
        week=draw(week_number),
        date=draw(game_date),
        home_team=home,
        away_team=away,
        status=GameStatus.POSTPONED,
        home_score=None,
        away_score=None,
        home_points=None,
        away_points=None,
        quarter=None,
        clock=None,
    )


@st.composite
def cancelled_game(draw: st.DrawFn) -> Game:
    """Generate a cancelled Game."""
    home, away = draw(team_pair)
    return Game(
        game_id=draw(game_id),
        week=draw(week_number),
        date=draw(game_date),
        home_team=home,
        away_team=away,
        status=GameStatus.CANCELLED,
        home_score=None,
        away_score=None,
        home_points=None,
        away_points=None,
        quarter=None,
        clock=None,
    )


@st.composite
def game_strategy(draw: st.DrawFn, status: GameStatus | None = None) -> Game:
    """Generate a Game with any status, or a specific status if provided.

    Args:
        status: If provided, generate a game with this specific status.
                If None, randomly choose a status.
    """
    if status is not None:
        chosen_status = status
    else:
        chosen_status = draw(game_status)

    strategy_map = {
        GameStatus.COMPLETED: completed_game(),
        GameStatus.SCHEDULED: scheduled_game(),
        GameStatus.IN_PROGRESS: in_progress_game(),
        GameStatus.POSTPONED: postponed_game(),
        GameStatus.CANCELLED: cancelled_game(),
    }
    return draw(strategy_map[chosen_status])


# Strategy for generating a list of games with mixed statuses
game_list = st.lists(game_strategy(), min_size=0, max_size=50)

# Strategy for generating a non-empty list of completed games
completed_game_list = st.lists(completed_game(), min_size=1, max_size=50)
