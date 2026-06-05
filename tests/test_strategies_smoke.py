"""Smoke tests to verify Hypothesis strategies generate valid data."""

from hypothesis import given, settings

from src.data_client import Game, GameStatus
from src.nfl_teams import ALL_TEAMS
from tests.strategies import (
    completed_game,
    espn_event,
    espn_scoreboard_response,
    game_strategy,
    in_progress_game,
    normalized_team_strength_ratings,
    scheduled_game,
    team_strength_ratings,
    wlt_record,
)


@given(game=game_strategy())
@settings(max_examples=50)
def test_game_strategy_produces_valid_games(game: Game) -> None:
    """Game strategy produces valid Game objects with correct field types."""
    assert isinstance(game, Game)
    assert game.home_team in ALL_TEAMS
    assert game.away_team in ALL_TEAMS
    assert game.home_team != game.away_team
    assert isinstance(game.status, GameStatus)
    assert 1 <= game.week <= 18
    assert len(game.game_id) >= 6


@given(game=completed_game())
@settings(max_examples=50)
def test_completed_game_has_scores(game: Game) -> None:
    """Completed games always have scores set."""
    assert game.status == GameStatus.COMPLETED
    assert game.home_score is not None
    assert game.away_score is not None
    assert game.home_points is not None
    assert game.away_points is not None
    assert game.quarter is None
    assert game.clock is None


@given(game=scheduled_game())
@settings(max_examples=50)
def test_scheduled_game_has_no_scores(game: Game) -> None:
    """Scheduled games have no scores."""
    assert game.status == GameStatus.SCHEDULED
    assert game.home_score is None
    assert game.away_score is None
    assert game.quarter is None
    assert game.clock is None


@given(game=in_progress_game())
@settings(max_examples=50)
def test_in_progress_game_has_live_data(game: Game) -> None:
    """In-progress games have scores, quarter, and clock."""
    assert game.status == GameStatus.IN_PROGRESS
    assert game.home_score is not None
    assert game.away_score is not None
    assert game.quarter is not None
    assert game.clock is not None


@given(response=espn_scoreboard_response())
@settings(max_examples=20)
def test_espn_response_has_required_structure(response: dict) -> None:
    """ESPN scoreboard response has the expected nested structure."""
    assert "events" in response
    assert isinstance(response["events"], list)
    assert len(response["events"]) >= 1

    for event in response["events"]:
        assert "id" in event
        assert "date" in event
        assert "week" in event
        assert "number" in event["week"]
        assert "status" in event
        assert "type" in event["status"]
        assert "name" in event["status"]["type"]
        assert "competitions" in event
        assert len(event["competitions"]) >= 1
        competitors = event["competitions"][0]["competitors"]
        assert len(competitors) == 2
        for comp in competitors:
            assert "homeAway" in comp
            assert "team" in comp
            assert "displayName" in comp["team"]
            assert "score" in comp


@given(event=espn_event(status_name="STATUS_IN_PROGRESS"))
@settings(max_examples=20)
def test_espn_in_progress_event_has_clock(event: dict) -> None:
    """In-progress ESPN events have period and displayClock."""
    assert event["status"]["type"]["name"] == "STATUS_IN_PROGRESS"
    assert "period" in event["status"]
    assert "displayClock" in event["status"]
    assert event["status"]["period"] >= 1


@given(record=wlt_record())
@settings(max_examples=100)
def test_wlt_record_valid(record: tuple[int, int, int]) -> None:
    """W-L-T records have non-negative values summing to <= 17."""
    wins, losses, ties = record
    assert wins >= 0
    assert losses >= 0
    assert ties >= 0
    assert wins + losses + ties <= 17


@given(ratings=team_strength_ratings())
@settings(max_examples=30)
def test_team_strength_ratings_valid(ratings: dict[str, float]) -> None:
    """Team strength ratings are positive floats for valid teams."""
    assert len(ratings) >= 2
    for team, rating in ratings.items():
        assert team in ALL_TEAMS
        assert rating > 0
        assert rating <= 3.0


@given(ratings=normalized_team_strength_ratings())
@settings(max_examples=20)
def test_normalized_ratings_average_near_one(ratings: dict[str, float]) -> None:
    """Normalized team strength ratings average approximately 1.0."""
    assert len(ratings) == 32
    avg = sum(ratings.values()) / len(ratings)
    assert abs(avg - 1.0) < 0.001
