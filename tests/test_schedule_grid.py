# Feature: nfl-schedule-grid, Property 5: Backend grid transformation structural guarantees
"""Property-based tests for _build_schedule_grid backend function.

Validates: Requirements 6.1, 6.3, 6.4, 6.5, 6.6
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from src.data_client import Game, GameStatus
from src.nfl_teams import ALL_TEAMS
from src.server import _build_schedule_grid
from tests.strategies.games import game_strategy


# Strategy for generating a game list of 0–272 games with random statuses
schedule_game_list = st.lists(game_strategy(), min_size=0, max_size=272)


class TestBuildScheduleGridStructuralGuarantees:
    """Property 5: Backend grid transformation structural guarantees.

    **Validates: Requirements 6.1, 6.3, 6.4, 6.5, 6.6**
    """

    @given(games=schedule_game_list)
    @settings(max_examples=100)
    def test_exactly_32_entries_with_18_week_slots(self, games: list[Game]) -> None:
        """Grid always has exactly 32 team entries, each with exactly 18 week slots."""
        result = _build_schedule_grid(games, ALL_TEAMS)

        assert len(result) == 32, f"Expected 32 entries, got {len(result)}"
        for entry in result:
            assert len(entry["weeks"]) == 18, (
                f"Team {entry['team']} has {len(entry['weeks'])} weeks, expected 18"
            )

    @given(games=schedule_game_list)
    @settings(max_examples=100)
    def test_non_null_slots_have_correct_field_types(self, games: list[Game]) -> None:
        """Non-null slots have opponent (string), home (boolean), and valid status."""
        result = _build_schedule_grid(games, ALL_TEAMS)
        valid_statuses = {"scheduled", "in-progress", "completed"}

        for entry in result:
            for week_idx, slot in enumerate(entry["weeks"]):
                if slot is not None:
                    assert isinstance(slot["opponent"], str), (
                        f"Team {entry['team']} week {week_idx + 1}: "
                        f"opponent should be str, got {type(slot['opponent'])}"
                    )
                    assert isinstance(slot["home"], bool), (
                        f"Team {entry['team']} week {week_idx + 1}: "
                        f"home should be bool, got {type(slot['home'])}"
                    )
                    assert slot["status"] in valid_statuses, (
                        f"Team {entry['team']} week {week_idx + 1}: "
                        f"status '{slot['status']}' not in {valid_statuses}"
                    )

    @given(games=schedule_game_list)
    @settings(max_examples=100)
    def test_completed_in_progress_games_with_scores_have_integer_scores(
        self, games: list[Game]
    ) -> None:
        """Completed/in-progress games with source scores include integer team_score and opponent_score."""
        result = _build_schedule_grid(games, ALL_TEAMS)

        # Build a lookup of games by (team, week) to check source scores
        home_games: dict[tuple[str, int], Game] = {}
        away_games: dict[tuple[str, int], Game] = {}
        for game in games:
            if game.status not in (GameStatus.POSTPONED, GameStatus.CANCELLED):
                if 1 <= game.week <= 18:
                    home_games[(game.home_team, game.week)] = game
                    away_games[(game.away_team, game.week)] = game

        for entry in result:
            team_name = entry["team"]
            for week_idx, slot in enumerate(entry["weeks"]):
                if slot is None:
                    continue
                if slot["status"] not in ("completed", "in-progress"):
                    continue

                # Find the source game to check if scores existed
                week_num = week_idx + 1
                source_game = home_games.get((team_name, week_num)) or away_games.get(
                    (team_name, week_num)
                )
                if source_game is None:
                    continue

                # Determine expected scores from perspective of this team
                if team_name == source_game.home_team:
                    src_team_score = source_game.home_score
                    src_opp_score = source_game.away_score
                else:
                    src_team_score = source_game.away_score
                    src_opp_score = source_game.home_score

                # If source game has scores, slot must have integer scores
                if src_team_score is not None:
                    assert isinstance(slot["team_score"], int), (
                        f"Team {team_name} week {week_num}: "
                        f"team_score should be int, got {type(slot['team_score'])}"
                    )
                if src_opp_score is not None:
                    assert isinstance(slot["opponent_score"], int), (
                        f"Team {team_name} week {week_num}: "
                        f"opponent_score should be int, got {type(slot['opponent_score'])}"
                    )

    @given(games=schedule_game_list)
    @settings(max_examples=100)
    def test_weeks_with_no_game_are_null(self, games: list[Game]) -> None:
        """Weeks where a team has no game are represented as null (None)."""
        result = _build_schedule_grid(games, ALL_TEAMS)

        # Build set of (team, week) pairs that should have a game entry
        # (non-postponed, non-cancelled games with valid weeks)
        active_slots: set[tuple[str, int]] = set()
        for game in games:
            if game.status in (GameStatus.POSTPONED, GameStatus.CANCELLED):
                continue
            if game.week < 1 or game.week > 18:
                continue
            active_slots.add((game.home_team, game.week))
            active_slots.add((game.away_team, game.week))

        for entry in result:
            team_name = entry["team"]
            for week_idx, slot in enumerate(entry["weeks"]):
                week_num = week_idx + 1
                if (team_name, week_num) not in active_slots:
                    assert slot is None, (
                        f"Team {team_name} week {week_num}: "
                        f"expected null for bye week, got {slot}"
                    )
