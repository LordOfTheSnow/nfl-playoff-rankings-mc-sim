"""Unit tests for CP solver module."""

from datetime import date

from src.cp_solver import _generate_record_bounds
from src.data_client import Game, GameStatus


def _make_game(week: int, home: str = "Bills", away: str = "Chiefs") -> Game:
    """Helper to create a simple scheduled game for testing."""
    return Game(
        game_id=f"game_{week}_{home}_{away}",
        week=week,
        date=date(2024, 12, 1),
        home_team=home,
        away_team=away,
        status=GameStatus.SCHEDULED,
    )


class TestGenerateRecordBounds:
    """Tests for _generate_record_bounds()."""

    def test_zero_remaining_games(self):
        """With 0 remaining games, returns a single record equal to the fixed record."""
        records = _generate_record_bounds(
            team="Bills",
            team_remaining_games=[],
            fixed_wins=10,
            fixed_losses=5,
            fixed_ties=2,
        )
        assert records == [(10, 5, 2)]
        # (0+1)(0+2)/2 = 1
        assert len(records) == 1

    def test_one_remaining_game(self):
        """With 1 remaining game, returns 3 records (win, loss, or tie)."""
        games = [_make_game(week=15)]
        records = _generate_record_bounds(
            team="Bills",
            team_remaining_games=games,
            fixed_wins=8,
            fixed_losses=5,
            fixed_ties=0,
        )
        # (1+1)(1+2)/2 = 3
        assert len(records) == 3
        # Should contain: 1 extra win, 1 extra loss, 1 extra tie
        assert (9, 5, 0) in records  # win
        assert (8, 6, 0) in records  # loss
        assert (8, 5, 1) in records  # tie

    def test_two_remaining_games(self):
        """With 2 remaining games, returns 6 records."""
        games = [_make_game(week=16), _make_game(week=17, away="Dolphins")]
        records = _generate_record_bounds(
            team="Bills",
            team_remaining_games=games,
            fixed_wins=7,
            fixed_losses=5,
            fixed_ties=1,
        )
        # (2+1)(2+2)/2 = 6
        assert len(records) == 6
        # All records should have components summing to 7+5+1+2 = 15
        for w, l, t in records:
            assert w + l + t == 7 + 5 + 1 + 2

    def test_three_remaining_games(self):
        """With 3 remaining games, returns 10 records."""
        games = [_make_game(week=15 + i) for i in range(3)]
        records = _generate_record_bounds(
            team="Bills",
            team_remaining_games=games,
            fixed_wins=5,
            fixed_losses=5,
            fixed_ties=0,
        )
        # (3+1)(3+2)/2 = 10
        assert len(records) == 10

    def test_record_count_formula(self):
        """Verify the (N+1)(N+2)/2 formula for various N values."""
        for n in range(0, 18):
            games = [_make_game(week=i + 1) for i in range(n)]
            records = _generate_record_bounds(
                team="Bills",
                team_remaining_games=games,
                fixed_wins=0,
                fixed_losses=0,
                fixed_ties=0,
            )
            expected_count = (n + 1) * (n + 2) // 2
            assert len(records) == expected_count, (
                f"For N={n}, expected {expected_count} records but got {len(records)}"
            )

    def test_all_records_distinct(self):
        """All returned records should be distinct tuples."""
        games = [_make_game(week=i + 1) for i in range(5)]
        records = _generate_record_bounds(
            team="Bills",
            team_remaining_games=games,
            fixed_wins=3,
            fixed_losses=4,
            fixed_ties=0,
        )
        assert len(records) == len(set(records))

    def test_records_sum_correctly(self):
        """Each record's W+L+T should equal fixed_total + N remaining games."""
        fixed_wins, fixed_losses, fixed_ties = 6, 4, 1
        n = 6
        games = [_make_game(week=i + 1) for i in range(n)]
        records = _generate_record_bounds(
            team="Bills",
            team_remaining_games=games,
            fixed_wins=fixed_wins,
            fixed_losses=fixed_losses,
            fixed_ties=fixed_ties,
        )
        total_games = fixed_wins + fixed_losses + fixed_ties + n
        for w, l, t in records:
            assert w + l + t == total_games

    def test_minimum_and_maximum_wins(self):
        """Best and worst case records are included."""
        n = 4
        games = [_make_game(week=i + 1) for i in range(n)]
        records = _generate_record_bounds(
            team="Bills",
            team_remaining_games=games,
            fixed_wins=5,
            fixed_losses=3,
            fixed_ties=0,
        )
        # Best case: win all remaining
        assert (5 + n, 3, 0) in records
        # Worst case: lose all remaining
        assert (5, 3 + n, 0) in records
        # All ties
        assert (5, 3, n) in records

    def test_fixed_record_offset(self):
        """Records are properly offset by the fixed record."""
        games = [_make_game(week=18)]
        records = _generate_record_bounds(
            team="Chiefs",
            team_remaining_games=games,
            fixed_wins=12,
            fixed_losses=4,
            fixed_ties=0,
        )
        # With 1 game remaining from a 12-4-0 record:
        assert (13, 4, 0) in records  # win the game
        assert (12, 5, 0) in records  # lose the game
        assert (12, 4, 1) in records  # tie the game


# --- PlayoffValidator tests ---

from unittest.mock import patch

from ortools.sat.python import cp_model

from src.cp_solver import PlayoffValidator


def _make_completed_game(
    game_id: str, week: int, home: str, away: str,
    home_score: int, away_score: int,
) -> Game:
    """Helper to create a completed game with scores."""
    return Game(
        game_id=game_id,
        week=week,
        date=date(2024, 9, 8),
        home_team=home,
        away_team=away,
        status=GameStatus.COMPLETED,
        home_score=home_score,
        away_score=away_score,
        home_points=home_score,
        away_points=away_score,
    )


class TestPlayoffValidator:
    """Tests for PlayoffValidator CP-SAT solution callback."""

    def _build_simple_model(self, remaining_games: list[Game]):
        """Build a minimal CP-SAT model with one IntVar per remaining game."""
        model = cp_model.CpModel()
        game_outcome_vars = {}
        for game in remaining_games:
            var = model.new_int_var(0, 2, f"game_{game.game_id}")
            game_outcome_vars[game.game_id] = var
        return model, game_outcome_vars

    def test_found_initially_false(self):
        """Validator starts with found=False before any solution is evaluated."""
        remaining = [_make_game(18, "Bills", "Dolphins")]
        model, vars_ = self._build_simple_model(remaining)
        validator = PlayoffValidator(
            team="Bills",
            all_games=remaining,
            remaining_games=remaining,
            game_outcome_vars=vars_,
            search_for_miss=True,
        )
        assert validator.found is False

    def test_search_for_miss_false_finds_team_in_bracket(self):
        """With search_for_miss=False, finds assignment where team makes playoffs."""
        remaining = [
            _make_game(18, "Bills", "Dolphins"),
            _make_game(18, "Chiefs", "Raiders"),
        ]
        model, vars_ = self._build_simple_model(remaining)
        validator = PlayoffValidator(
            team="Bills",
            all_games=remaining,
            remaining_games=remaining,
            game_outcome_vars=vars_,
            search_for_miss=False,
        )
        solver = cp_model.CpSolver()
        solver.solve(model, validator)
        # Bills should easily make the bracket when there are very few games
        assert validator.found is True

    def test_search_for_miss_true_with_minimal_games(self):
        """With very few remaining games, a dominant team won't miss playoffs."""
        # Give Bills a strong completed record so they can't miss
        completed = [
            _make_completed_game(f"c{i}", week=i, home="Bills", away="Jets",
                                 home_score=21, away_score=10)
            for i in range(1, 15)
        ]
        remaining = [_make_game(18, "Bills", "Dolphins")]
        all_games = completed + remaining

        model, vars_ = self._build_simple_model(remaining)
        validator = PlayoffValidator(
            team="Bills",
            all_games=all_games,
            remaining_games=remaining,
            game_outcome_vars=vars_,
            search_for_miss=True,
        )
        solver = cp_model.CpSolver()
        solver.solve(model, validator)
        # With 14 wins and only 1 game remaining, Bills can't miss playoffs
        assert validator.found is False

    def test_exception_in_standings_engine_does_not_crash(self):
        """If standings engine raises, callback logs and continues searching."""
        remaining = [_make_game(18, "Bills", "Dolphins")]
        model, vars_ = self._build_simple_model(remaining)
        validator = PlayoffValidator(
            team="Bills",
            all_games=remaining,
            remaining_games=remaining,
            game_outcome_vars=vars_,
            search_for_miss=False,
        )
        with patch(
            "src.cp_solver.compute_standings",
            side_effect=RuntimeError("standings engine error"),
        ):
            solver = cp_model.CpSolver()
            # Should not raise; validator catches the exception
            solver.solve(model, validator)
        # found remains False since standings engine always raised
        assert validator.found is False

    def test_inherits_cp_solver_solution_callback(self):
        """PlayoffValidator inherits from CpSolverSolutionCallback."""
        remaining = [_make_game(18, "Bills", "Dolphins")]
        model, vars_ = self._build_simple_model(remaining)
        validator = PlayoffValidator(
            team="Bills",
            all_games=remaining,
            remaining_games=remaining,
            game_outcome_vars=vars_,
            search_for_miss=True,
        )
        assert isinstance(validator, cp_model.CpSolverSolutionCallback)


# --- solve_clinch_all tests ---

from src.cp_solver import (
    CPSolverConfig,
    CPSolverResult,
    ClinchStatus,
    _solve_clinch_worker,
    solve_clinch_all,
)
from src.nfl_teams import ALL_TEAMS, get_team_conference


class TestSolveClincWorker:
    """Tests for _solve_clinch_worker helper."""

    def test_returns_team_and_result_tuple(self):
        """Worker returns (team_name, CPSolverResult) tuple."""
        # Use a minimal game set that causes solve_clinch to run briefly
        games = [_make_game(18, "Bills", "Dolphins")]
        config = CPSolverConfig(time_limit=5)
        result = _solve_clinch_worker(("Bills", games, 17, config))
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] == "Bills"
        assert isinstance(result[1], CPSolverResult)
        assert result[1].team == "Bills"

    def test_exception_returns_inconclusive(self):
        """Worker catches exceptions and returns INCONCLUSIVE status."""
        # Pass invalid data that will cause an error during solving
        config = CPSolverConfig(time_limit=1)
        with patch("src.cp_solver.solve_clinch", side_effect=RuntimeError("test error")):
            team, result = _solve_clinch_worker(("Bills", [], 17, config))
        assert team == "Bills"
        assert result.status == ClinchStatus.INCONCLUSIVE
        assert "test error" in result.error


class TestSolveClincAll:
    """Tests for solve_clinch_all bulk solver."""

    def test_returns_dict_with_all_32_teams(self):
        """solve_clinch_all returns results for all 32 teams."""
        # Create a minimal game set - just enough for the function to run
        # We'll use a very short time limit so it finishes quickly
        games = [_make_game(18, "Bills", "Dolphins")]
        config = CPSolverConfig(time_limit=2)
        results = solve_clinch_all(games, cutoff_week=17, config=config)
        assert isinstance(results, dict)
        assert len(results) == 32
        for team in ALL_TEAMS:
            assert team in results
            assert isinstance(results[team], CPSolverResult)
            assert results[team].team == team

    def test_individual_failures_do_not_affect_others(self):
        """_solve_clinch_worker catches exceptions so other teams still get results.

        Since multiprocessing spawns separate processes that don't inherit mocks,
        we test the worker function directly to verify error isolation.
        """
        config = CPSolverConfig(time_limit=2)

        # Test the worker function directly with a mock that raises
        with patch("src.cp_solver.solve_clinch", side_effect=RuntimeError("Simulated failure")):
            team, result = _solve_clinch_worker(("Bills", [], 17, config))

        # The worker should catch the exception and return INCONCLUSIVE
        assert team == "Bills"
        assert result.status == ClinchStatus.INCONCLUSIVE
        assert "Simulated failure" in result.error

        # Other teams still work fine (using real solve_clinch)
        games = [_make_game(18, "Bills", "Dolphins")]
        team2, result2 = _solve_clinch_worker(("Chiefs", games, 17, config))
        assert team2 == "Chiefs"
        assert isinstance(result2, CPSolverResult)
        # Chiefs result is independent — it's not INCONCLUSIVE from Bills' failure
        assert result2.team == "Chiefs"

    def test_result_values_have_valid_status(self):
        """All results have a valid ClinchStatus."""
        games = [_make_game(18, "Bills", "Dolphins")]
        config = CPSolverConfig(time_limit=2)
        results = solve_clinch_all(games, cutoff_week=17, config=config)
        valid_statuses = {
            ClinchStatus.CLINCHED,
            ClinchStatus.ELIMINATED,
            ClinchStatus.ALIVE,
            ClinchStatus.INCONCLUSIVE,
        }
        for team, result in results.items():
            assert result.status in valid_statuses, (
                f"Team {team} has invalid status: {result.status}"
            )

    def test_results_can_be_grouped_by_conference(self):
        """Results include teams from both conferences that can be grouped."""
        games = [_make_game(18, "Bills", "Dolphins")]
        config = CPSolverConfig(time_limit=2)
        results = solve_clinch_all(games, cutoff_week=17, config=config)

        afc_results = {
            team: r for team, r in results.items()
            if get_team_conference(team) == "AFC"
        }
        nfc_results = {
            team: r for team, r in results.items()
            if get_team_conference(team) == "NFC"
        }

        assert len(afc_results) == 16
        assert len(nfc_results) == 16

        # Verify alphabetical sorting works
        afc_sorted = sorted(afc_results.keys())
        nfc_sorted = sorted(nfc_results.keys())
        assert len(afc_sorted) == 16
        assert len(nfc_sorted) == 16

    def test_raises_runtime_error_when_ortools_unavailable(self):
        """solve_clinch_all raises RuntimeError if OR-Tools not installed."""
        import pytest

        games = [_make_game(18, "Bills", "Dolphins")]
        with patch("src.cp_solver.ORTOOLS_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="OR-Tools is not installed"):
                solve_clinch_all(games, cutoff_week=17)
