"""Unit tests for GET /api/cp-clinch/{team} endpoint."""

import json
from datetime import date
from http.server import HTTPServer
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from src.cache import Cache
from src.cp_solver import ClinchStatus, CPSolverConfig, CPSolverResult
from src.data_client import Game, GameStatus
from src.nfl_teams import ALL_TEAMS
from src.server import NFLRequestHandler, NFLSimulatorServer


def _make_completed_game(
    game_id: str, week: int, home: str, away: str,
    home_score: int, away_score: int,
) -> Game:
    """Helper to create a completed game."""
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


def _make_scheduled_game(game_id: str, week: int, home: str, away: str) -> Game:
    """Helper to create a scheduled game."""
    return Game(
        game_id=game_id,
        week=week,
        date=date(2025, 1, 5),
        home_team=home,
        away_team=away,
        status=GameStatus.SCHEDULED,
    )


class MockHTTPRequest:
    """Mock HTTP request for testing handler methods directly."""

    def __init__(self, method: str, path: str, server: NFLSimulatorServer):
        self.method = method
        self.path = path
        self.server = server
        self.headers = {"Content-Length": "0"}
        self.rfile = BytesIO(b"")
        self.wfile = BytesIO()
        self._response_code = None
        self._response_headers = {}
        self._response_body = b""

    def makefile(self, *args, **kwargs):
        return BytesIO(b"")


class FakeHandler(NFLRequestHandler):
    """A handler subclass that captures responses without real sockets."""

    def __init__(self, path: str, server: NFLSimulatorServer):
        self.path = path
        self.server = server
        self.headers = {"Content-Length": "0"}
        self.rfile = BytesIO(b"")
        self.wfile = BytesIO()
        self._sent_code = None
        self._sent_headers = []
        self._sent_body = b""

    def send_response(self, code, message=None):
        self._sent_code = code

    def send_header(self, keyword, value):
        self._sent_headers.append((keyword, value))

    def end_headers(self):
        pass

    def log_message(self, format, *args):
        pass

    def get_response_json(self) -> dict:
        """Parse the written response body as JSON."""
        return json.loads(self.wfile.getvalue().decode("utf-8"))


@pytest.fixture
def server_with_cache():
    """Create a server with an in-memory cache for testing."""
    server = NFLSimulatorServer(
        port=0,
        season_year=2024,
        db_path=":memory:",
    )
    yield server
    server.cache.close()


@pytest.fixture
def server_with_games(server_with_cache):
    """Create a server with cached game data."""
    server = server_with_cache
    # Create a mix of completed and scheduled games
    games = [
        _make_completed_game("g1", 1, "Bills", "Jets", 24, 10),
        _make_completed_game("g2", 1, "Dolphins", "Patriots", 20, 17),
        _make_completed_game("g3", 2, "Bills", "Dolphins", 31, 24),
        _make_completed_game("g4", 2, "Jets", "Patriots", 14, 13),
        _make_scheduled_game("g5", 3, "Bills", "Patriots"),
        _make_scheduled_game("g6", 3, "Dolphins", "Jets"),
    ]
    server.cache.store_games(games, 2024)
    return server


def _make_handler(path: str, server: NFLSimulatorServer) -> FakeHandler:
    """Create a FakeHandler configured for the given path and server."""
    handler = FakeHandler(path, server)
    return handler


class TestCPClinchEndpointValidation:
    """Test input validation for GET /api/cp-clinch/{team}."""

    def test_invalid_team_returns_400(self, server_with_games):
        """Invalid team name returns 400 with valid teams list."""
        handler = _make_handler("/api/cp-clinch/InvalidTeam", server_with_games)
        handler._handle_get_cp_clinch("/api/cp-clinch/InvalidTeam")
        assert handler._sent_code == 400
        body = handler.get_response_json()
        assert body["error"] == "Invalid team"
        assert "valid_teams" in body
        assert isinstance(body["valid_teams"], list)
        assert len(body["valid_teams"]) == 32

    def test_invalid_cutoff_week_not_integer_returns_400(self, server_with_games):
        """Non-integer cutoff_week returns 400."""
        handler = _make_handler(
            "/api/cp-clinch/Bills?cutoff_week=abc", server_with_games
        )
        handler._handle_get_cp_clinch("/api/cp-clinch/Bills?cutoff_week=abc")
        assert handler._sent_code == 400
        body = handler.get_response_json()
        assert "cutoff_week" in body["error"].lower() or "cutoff_week" in body.get("details", "").lower()

    def test_cutoff_week_below_range_returns_400(self, server_with_games):
        """cutoff_week < 1 returns 400."""
        handler = _make_handler(
            "/api/cp-clinch/Bills?cutoff_week=0", server_with_games
        )
        handler._handle_get_cp_clinch("/api/cp-clinch/Bills?cutoff_week=0")
        assert handler._sent_code == 400

    def test_cutoff_week_above_range_returns_400(self, server_with_games):
        """cutoff_week > 18 returns 400."""
        handler = _make_handler(
            "/api/cp-clinch/Bills?cutoff_week=19", server_with_games
        )
        handler._handle_get_cp_clinch("/api/cp-clinch/Bills?cutoff_week=19")
        assert handler._sent_code == 400

    def test_invalid_time_limit_not_integer_returns_400(self, server_with_games):
        """Non-integer time_limit returns 400."""
        handler = _make_handler(
            "/api/cp-clinch/Bills?time_limit=xyz", server_with_games
        )
        handler._handle_get_cp_clinch("/api/cp-clinch/Bills?time_limit=xyz")
        assert handler._sent_code == 400
        body = handler.get_response_json()
        assert "time_limit" in body["error"].lower() or "time_limit" in body.get("details", "").lower()

    def test_time_limit_below_range_returns_400(self, server_with_games):
        """time_limit < 1 returns 400."""
        handler = _make_handler(
            "/api/cp-clinch/Bills?time_limit=0", server_with_games
        )
        handler._handle_get_cp_clinch("/api/cp-clinch/Bills?time_limit=0")
        assert handler._sent_code == 400

    def test_time_limit_above_range_returns_400(self, server_with_games):
        """time_limit > 300 returns 400."""
        handler = _make_handler(
            "/api/cp-clinch/Bills?time_limit=301", server_with_games
        )
        handler._handle_get_cp_clinch("/api/cp-clinch/Bills?time_limit=301")
        assert handler._sent_code == 400

    def test_valid_cutoff_week_boundary_1(self, server_with_games):
        """cutoff_week=1 is valid (boundary)."""
        with patch("src.server.solve_clinch") as mock_solve:
            mock_solve.return_value = CPSolverResult(team="Bills")
            handler = _make_handler(
                "/api/cp-clinch/Bills?cutoff_week=1", server_with_games
            )
            handler._handle_get_cp_clinch("/api/cp-clinch/Bills?cutoff_week=1")
            assert handler._sent_code == 200

    def test_valid_cutoff_week_boundary_18(self, server_with_games):
        """cutoff_week=18 is valid (boundary)."""
        with patch("src.server.solve_clinch") as mock_solve:
            mock_solve.return_value = CPSolverResult(team="Bills")
            handler = _make_handler(
                "/api/cp-clinch/Bills?cutoff_week=18", server_with_games
            )
            handler._handle_get_cp_clinch("/api/cp-clinch/Bills?cutoff_week=18")
            assert handler._sent_code == 200

    def test_valid_time_limit_boundary_1(self, server_with_games):
        """time_limit=1 is valid (boundary)."""
        with patch("src.server.solve_clinch") as mock_solve:
            mock_solve.return_value = CPSolverResult(team="Bills")
            handler = _make_handler(
                "/api/cp-clinch/Bills?cutoff_week=2&time_limit=1", server_with_games
            )
            handler._handle_get_cp_clinch("/api/cp-clinch/Bills?cutoff_week=2&time_limit=1")
            assert handler._sent_code == 200

    def test_valid_time_limit_boundary_300(self, server_with_games):
        """time_limit=300 is valid (boundary)."""
        with patch("src.server.solve_clinch") as mock_solve:
            mock_solve.return_value = CPSolverResult(team="Bills")
            handler = _make_handler(
                "/api/cp-clinch/Bills?cutoff_week=2&time_limit=300", server_with_games
            )
            handler._handle_get_cp_clinch("/api/cp-clinch/Bills?cutoff_week=2&time_limit=300")
            assert handler._sent_code == 200


class TestCPClinchEndpointORToolsCheck:
    """Test OR-Tools availability check."""

    def test_ortools_unavailable_returns_503(self, server_with_games):
        """When OR-Tools is not available, return 503."""
        with patch("src.server.ORTOOLS_AVAILABLE", False):
            handler = _make_handler("/api/cp-clinch/Bills", server_with_games)
            handler._handle_get_cp_clinch("/api/cp-clinch/Bills")
            assert handler._sent_code == 503
            body = handler.get_response_json()
            assert "OR-Tools" in body["error"]
            assert "pip install ortools" in body["error"]


class TestCPClinchEndpointDataCheck:
    """Test game data existence check."""

    def test_no_game_data_returns_409(self, server_with_cache):
        """When no games are cached, return 409."""
        handler = _make_handler("/api/cp-clinch/Bills", server_with_cache)
        handler._handle_get_cp_clinch("/api/cp-clinch/Bills")
        assert handler._sent_code == 409
        body = handler.get_response_json()
        assert "No game data" in body["error"]
        assert "POST /api/fetch-data" in body["error"]


class TestCPClinchEndpointAutoDetectCutoff:
    """Test auto-detection of cutoff_week."""

    def test_auto_detect_latest_completed_week(self, server_with_games):
        """Without cutoff_week param, auto-detects latest completed week."""
        with patch("src.server.solve_clinch") as mock_solve:
            mock_solve.return_value = CPSolverResult(team="Bills")
            handler = _make_handler("/api/cp-clinch/Bills", server_with_games)
            handler._handle_get_cp_clinch("/api/cp-clinch/Bills")
            assert handler._sent_code == 200
            # The server_with_games fixture has weeks 1,2 completed and week 3 scheduled
            # So cutoff_week should be auto-detected as 2
            assert mock_solve.called
            call_args = mock_solve.call_args
            # cutoff_week is the 3rd positional arg
            assert call_args[0][2] == 2


class TestCPClinchEndpointCaching:
    """Test cache integration."""

    def test_cache_hit_returns_cached_result(self, server_with_games):
        """When cached result exists, return it without running solver."""
        # Store a result in cache
        cached_result = CPSolverResult(
            team="Bills",
            status=ClinchStatus.CLINCHED,
            clinched=True,
            eliminated=False,
            exhaustive=True,
            solve_time_ms=1500,
            num_variables=48,
            minimum_seed=2,
        )
        server_with_games.cache.store_cp_result("Bills", 2, 2024, cached_result)

        with patch("src.server.solve_clinch") as mock_solve:
            handler = _make_handler(
                "/api/cp-clinch/Bills?cutoff_week=2", server_with_games
            )
            handler._handle_get_cp_clinch("/api/cp-clinch/Bills?cutoff_week=2")
            assert handler._sent_code == 200
            # Solver should NOT have been called
            mock_solve.assert_not_called()
            body = handler.get_response_json()
            assert body["team"] == "Bills"
            assert body["status"] == "clinched"
            assert body["clinched"] is True

    def test_cache_miss_runs_solver_and_stores(self, server_with_games):
        """When no cached result, runs solver and stores the result."""
        solver_result = CPSolverResult(
            team="Bills",
            status=ClinchStatus.ALIVE,
            clinched=False,
            eliminated=False,
            exhaustive=True,
            solve_time_ms=500,
            num_variables=30,
            magic_number=3,
        )

        with patch("src.server.solve_clinch", return_value=solver_result) as mock_solve:
            handler = _make_handler(
                "/api/cp-clinch/Bills?cutoff_week=2", server_with_games
            )
            handler._handle_get_cp_clinch("/api/cp-clinch/Bills?cutoff_week=2")
            assert handler._sent_code == 200
            mock_solve.assert_called_once()

        # Verify result was cached
        cached = server_with_games.cache.get_cp_result("Bills", 2, 2024)
        assert cached is not None
        assert cached.team == "Bills"
        assert cached.status == ClinchStatus.ALIVE


class TestCPClinchEndpointResponse:
    """Test response serialization."""

    def test_response_contains_all_required_fields(self, server_with_games):
        """Response JSON has all required fields from the spec."""
        solver_result = CPSolverResult(
            team="Bills",
            status=ClinchStatus.CLINCHED,
            clinched=True,
            eliminated=False,
            exhaustive=True,
            solve_time_ms=1234,
            num_variables=48,
            minimum_seed=2,
            magic_number=None,
            error=None,
        )

        with patch("src.server.solve_clinch", return_value=solver_result):
            handler = _make_handler(
                "/api/cp-clinch/Bills?cutoff_week=2", server_with_games
            )
            handler._handle_get_cp_clinch("/api/cp-clinch/Bills?cutoff_week=2")
            assert handler._sent_code == 200
            body = handler.get_response_json()

        assert body["team"] == "Bills"
        assert body["status"] == "clinched"
        assert body["clinched"] is True
        assert body["eliminated"] is False
        assert body["exhaustive"] is True
        assert body["solve_time_ms"] == 1234
        assert body["num_variables"] == 48
        assert body["minimum_seed"] == 2
        assert body["magic_number"] is None
        assert body["error"] is None

    def test_response_alive_with_magic_number(self, server_with_games):
        """Alive teams include magic_number in response."""
        solver_result = CPSolverResult(
            team="Chiefs",
            status=ClinchStatus.ALIVE,
            clinched=False,
            eliminated=False,
            exhaustive=True,
            solve_time_ms=800,
            num_variables=52,
            magic_number=4,
        )

        with patch("src.server.solve_clinch", return_value=solver_result):
            handler = _make_handler(
                "/api/cp-clinch/Chiefs?cutoff_week=2", server_with_games
            )
            handler._handle_get_cp_clinch("/api/cp-clinch/Chiefs?cutoff_week=2")
            assert handler._sent_code == 200
            body = handler.get_response_json()

        assert body["status"] == "alive"
        assert body["magic_number"] == 4
        assert body["clinched"] is False
        assert body["eliminated"] is False

    def test_response_inconclusive_with_error(self, server_with_games):
        """Inconclusive status includes error message."""
        solver_result = CPSolverResult(
            team="Bills",
            status=ClinchStatus.INCONCLUSIVE,
            exhaustive=False,
            solve_time_ms=30000,
            num_variables=100,
            error="Timed out after 30s: 5/12 record groups completed",
        )

        with patch("src.server.solve_clinch", return_value=solver_result):
            handler = _make_handler(
                "/api/cp-clinch/Bills?cutoff_week=2", server_with_games
            )
            handler._handle_get_cp_clinch("/api/cp-clinch/Bills?cutoff_week=2")
            assert handler._sent_code == 200
            body = handler.get_response_json()

        assert body["status"] == "inconclusive"
        assert body["exhaustive"] is False
        assert "Timed out" in body["error"]


class TestFetchDataInvalidatesCPCache:
    """Test that POST /api/fetch-data invalidates cached CP solver results."""

    def test_fetch_data_invalidates_cp_cache(self, server_with_games):
        """After a successful fetch, cached CP solver results are removed."""
        # Pre-populate the CP cache with a result
        cached_result = CPSolverResult(
            team="Bills",
            status=ClinchStatus.CLINCHED,
            clinched=True,
            eliminated=False,
            exhaustive=True,
            solve_time_ms=1500,
            num_variables=48,
            minimum_seed=2,
        )
        server_with_games.cache.store_cp_result("Bills", 2, 2024, cached_result)

        # Verify it's cached
        assert server_with_games.cache.get_cp_result("Bills", 2, 2024) is not None

        # Simulate a successful fetch-data call
        from src.data_client import FetchResult

        mock_fetch_result = FetchResult(
            games=[_make_completed_game("g10", 3, "Bills", "Patriots", 27, 14)],
            errors=[],
            warnings=[],
        )

        handler = FakeHandler("/api/fetch-data", server_with_games)
        handler.headers = {"Content-Length": "0"}
        handler.rfile = BytesIO(b"")

        with patch.object(
            server_with_games.data_client,
            "fetch_season_schedule",
            return_value=mock_fetch_result,
        ):
            with patch.object(handler, "_compute_weekly_strengths"):
                handler._handle_post_fetch_data()

        assert handler._sent_code == 200

        # The CP cache should now be empty for this season
        assert server_with_games.cache.get_cp_result("Bills", 2, 2024) is None

    def test_fetch_data_only_invalidates_active_season(self, server_with_games):
        """Fetch invalidates CP cache for the active season only, not other seasons."""
        # Cache results for two different seasons
        result_2024 = CPSolverResult(
            team="Bills", status=ClinchStatus.ALIVE, solve_time_ms=100, num_variables=30,
        )
        result_2023 = CPSolverResult(
            team="Bills", status=ClinchStatus.CLINCHED, clinched=True,
            solve_time_ms=200, num_variables=40,
        )
        server_with_games.cache.store_cp_result("Bills", 2, 2024, result_2024)
        server_with_games.cache.store_cp_result("Bills", 2, 2023, result_2023)

        # Simulate a successful fetch (server season is 2024)
        from src.data_client import FetchResult

        mock_fetch_result = FetchResult(
            games=[_make_completed_game("g10", 3, "Bills", "Patriots", 27, 14)],
            errors=[],
            warnings=[],
        )

        handler = FakeHandler("/api/fetch-data", server_with_games)
        handler.headers = {"Content-Length": "0"}
        handler.rfile = BytesIO(b"")

        with patch.object(
            server_with_games.data_client,
            "fetch_season_schedule",
            return_value=mock_fetch_result,
        ):
            with patch.object(handler, "_compute_weekly_strengths"):
                handler._handle_post_fetch_data()

        assert handler._sent_code == 200

        # 2024 cache should be invalidated
        assert server_with_games.cache.get_cp_result("Bills", 2, 2024) is None
        # 2023 cache should still be intact
        cached_2023 = server_with_games.cache.get_cp_result("Bills", 2, 2023)
        assert cached_2023 is not None
        assert cached_2023.status == ClinchStatus.CLINCHED

    def test_fetch_data_error_does_not_invalidate_cache(self, server_with_games):
        """When fetch fails (ESPN errors), CP cache is NOT invalidated."""
        # Pre-populate the CP cache
        cached_result = CPSolverResult(
            team="Chiefs", status=ClinchStatus.ALIVE, solve_time_ms=500, num_variables=35,
        )
        server_with_games.cache.store_cp_result("Chiefs", 2, 2024, cached_result)

        # Simulate a failed fetch (ESPN API error)
        from src.data_client import FetchResult

        mock_fetch_result = FetchResult(
            games=[],
            errors=["ESPN API returned 503"],
            warnings=[],
        )

        handler = FakeHandler("/api/fetch-data", server_with_games)
        handler.headers = {"Content-Length": "0"}
        handler.rfile = BytesIO(b"")

        with patch.object(
            server_with_games.data_client,
            "fetch_season_schedule",
            return_value=mock_fetch_result,
        ):
            handler._handle_post_fetch_data()

        # Response should be error (502)
        assert handler._sent_code == 502

        # CP cache should still be intact since fetch failed
        assert server_with_games.cache.get_cp_result("Chiefs", 2, 2024) is not None



class TestCPClinchAllEndpointValidation:
    """Test input validation for GET /api/cp-clinch-all."""

    def test_invalid_cutoff_week_not_integer_returns_400(self, server_with_games):
        """Non-integer cutoff_week returns 400."""
        handler = _make_handler(
            "/api/cp-clinch-all?cutoff_week=abc", server_with_games
        )
        handler._handle_get_cp_clinch_all("/api/cp-clinch-all?cutoff_week=abc")
        assert handler._sent_code == 400
        body = handler.get_response_json()
        assert "cutoff_week" in body["error"].lower() or "cutoff_week" in body.get("details", "").lower()

    def test_cutoff_week_below_range_returns_400(self, server_with_games):
        """cutoff_week < 1 returns 400."""
        handler = _make_handler(
            "/api/cp-clinch-all?cutoff_week=0", server_with_games
        )
        handler._handle_get_cp_clinch_all("/api/cp-clinch-all?cutoff_week=0")
        assert handler._sent_code == 400

    def test_cutoff_week_above_range_returns_400(self, server_with_games):
        """cutoff_week > 18 returns 400."""
        handler = _make_handler(
            "/api/cp-clinch-all?cutoff_week=19", server_with_games
        )
        handler._handle_get_cp_clinch_all("/api/cp-clinch-all?cutoff_week=19")
        assert handler._sent_code == 400

    def test_invalid_time_limit_not_integer_returns_400(self, server_with_games):
        """Non-integer time_limit returns 400."""
        handler = _make_handler(
            "/api/cp-clinch-all?time_limit=xyz", server_with_games
        )
        handler._handle_get_cp_clinch_all("/api/cp-clinch-all?time_limit=xyz")
        assert handler._sent_code == 400
        body = handler.get_response_json()
        assert "time_limit" in body["error"].lower() or "time_limit" in body.get("details", "").lower()

    def test_time_limit_below_range_returns_400(self, server_with_games):
        """time_limit < 1 returns 400."""
        handler = _make_handler(
            "/api/cp-clinch-all?time_limit=0", server_with_games
        )
        handler._handle_get_cp_clinch_all("/api/cp-clinch-all?time_limit=0")
        assert handler._sent_code == 400

    def test_time_limit_above_range_returns_400(self, server_with_games):
        """time_limit > 300 returns 400."""
        handler = _make_handler(
            "/api/cp-clinch-all?time_limit=301", server_with_games
        )
        handler._handle_get_cp_clinch_all("/api/cp-clinch-all?time_limit=301")
        assert handler._sent_code == 400


class TestCPClinchAllEndpointORToolsCheck:
    """Test OR-Tools availability check for bulk endpoint."""

    def test_ortools_unavailable_returns_503(self, server_with_games):
        """When OR-Tools is not available, return 503."""
        with patch("src.server.ORTOOLS_AVAILABLE", False):
            handler = _make_handler("/api/cp-clinch-all", server_with_games)
            handler._handle_get_cp_clinch_all("/api/cp-clinch-all")
            assert handler._sent_code == 503
            body = handler.get_response_json()
            assert "OR-Tools" in body["error"]


class TestCPClinchAllEndpointDataCheck:
    """Test game data existence check for bulk endpoint."""

    def test_no_game_data_returns_409(self, server_with_cache):
        """When no games are cached, return 409."""
        handler = _make_handler("/api/cp-clinch-all", server_with_cache)
        handler._handle_get_cp_clinch_all("/api/cp-clinch-all")
        assert handler._sent_code == 409
        body = handler.get_response_json()
        assert "No game data" in body["error"]


class TestCPClinchAllEndpointResponse:
    """Test response format for GET /api/cp-clinch-all."""

    def test_response_grouped_by_conference(self, server_with_games):
        """Response groups results by AFC and NFC."""
        # Create mock results for all 32 teams
        mock_results = {}
        for team in ALL_TEAMS:
            mock_results[team] = CPSolverResult(
                team=team,
                status=ClinchStatus.ALIVE,
                solve_time_ms=100,
                num_variables=48,
            )

        with patch("src.server.solve_clinch", side_effect=lambda t, g, c, cfg=None: mock_results[t]):
            handler = _make_handler(
                "/api/cp-clinch-all?cutoff_week=2", server_with_games
            )
            handler._handle_get_cp_clinch_all("/api/cp-clinch-all?cutoff_week=2")
            assert handler._sent_code == 200
            body = handler.get_response_json()

        assert "conferences" in body
        assert "AFC" in body["conferences"]
        assert "NFC" in body["conferences"]
        assert len(body["conferences"]["AFC"]) == 16
        assert len(body["conferences"]["NFC"]) == 16

    def test_response_contains_cutoff_week_and_season(self, server_with_games):
        """Response includes cutoff_week and season fields."""
        mock_results = {
            team: CPSolverResult(team=team, status=ClinchStatus.ALIVE)
            for team in ALL_TEAMS
        }

        with patch("src.server.solve_clinch", side_effect=lambda t, g, c, cfg=None: mock_results[t]):
            handler = _make_handler(
                "/api/cp-clinch-all?cutoff_week=15", server_with_games
            )
            handler._handle_get_cp_clinch_all("/api/cp-clinch-all?cutoff_week=15")
            assert handler._sent_code == 200
            body = handler.get_response_json()

        assert body["cutoff_week"] == 15
        assert body["season"] == 2024

    def test_teams_sorted_alphabetically_within_conference(self, server_with_games):
        """Teams within each conference are sorted alphabetically."""
        mock_results = {
            team: CPSolverResult(team=team, status=ClinchStatus.ALIVE)
            for team in ALL_TEAMS
        }

        with patch("src.server.solve_clinch", side_effect=lambda t, g, c, cfg=None: mock_results[t]):
            handler = _make_handler(
                "/api/cp-clinch-all?cutoff_week=2", server_with_games
            )
            handler._handle_get_cp_clinch_all("/api/cp-clinch-all?cutoff_week=2")
            assert handler._sent_code == 200
            body = handler.get_response_json()

        afc_teams = [entry["team"] for entry in body["conferences"]["AFC"]]
        nfc_teams = [entry["team"] for entry in body["conferences"]["NFC"]]
        assert afc_teams == sorted(afc_teams)
        assert nfc_teams == sorted(nfc_teams)

    def test_team_entry_contains_required_fields(self, server_with_games):
        """Each team entry has status, solve_time_ms, num_variables, minimum_seed, magic_number."""
        # Pre-populate cache for all teams
        for team in ALL_TEAMS:
            result = CPSolverResult(
                team=team,
                status=ClinchStatus.CLINCHED,
                clinched=True,
                solve_time_ms=1234,
                num_variables=48,
                minimum_seed=2,
                magic_number=None,
            )
            server_with_games.cache.store_cp_result(team, 2, 2024, result)

        handler = _make_handler(
            "/api/cp-clinch-all?cutoff_week=2", server_with_games
        )
        handler._handle_get_cp_clinch_all("/api/cp-clinch-all?cutoff_week=2")
        assert handler._sent_code == 200
        body = handler.get_response_json()

        # Check first AFC team entry
        entry = body["conferences"]["AFC"][0]
        assert "team" in entry
        assert "status" in entry
        assert "solve_time_ms" in entry
        assert "num_variables" in entry
        assert "minimum_seed" in entry
        assert "magic_number" in entry
        assert entry["status"] == "clinched"
        assert entry["solve_time_ms"] == 1234
        assert entry["num_variables"] == 48
        assert entry["minimum_seed"] == 2

    def test_partial_results_on_team_failure(self, server_with_games):
        """If individual teams fail/timeout, partial results still returned."""
        mock_results = {}
        for team in ALL_TEAMS:
            if team == "Bills":
                # Simulate a timeout for Bills
                mock_results[team] = CPSolverResult(
                    team=team,
                    status=ClinchStatus.INCONCLUSIVE,
                    solve_time_ms=30000,
                    num_variables=100,
                    error="Timed out after 30s",
                )
            else:
                mock_results[team] = CPSolverResult(
                    team=team,
                    status=ClinchStatus.ALIVE,
                    solve_time_ms=500,
                    num_variables=48,
                )

        with patch("src.server.solve_clinch", side_effect=lambda t, g, c, cfg=None: mock_results[t]):
            handler = _make_handler(
                "/api/cp-clinch-all?cutoff_week=2", server_with_games
            )
            handler._handle_get_cp_clinch_all("/api/cp-clinch-all?cutoff_week=2")
            assert handler._sent_code == 200
            body = handler.get_response_json()

        # All 32 teams should still be present
        total_teams = len(body["conferences"]["AFC"]) + len(body["conferences"]["NFC"])
        assert total_teams == 32

        # Bills should show as inconclusive
        bills_entry = next(
            e for e in body["conferences"]["AFC"] if e["team"] == "Bills"
        )
        assert bills_entry["status"] == "inconclusive"

    def test_auto_detect_cutoff_week(self, server_with_games):
        """Without cutoff_week param, auto-detects latest completed week."""
        mock_results = {
            team: CPSolverResult(team=team, status=ClinchStatus.ALIVE)
            for team in ALL_TEAMS
        }

        with patch("src.server.solve_clinch", side_effect=lambda t, g, c, cfg=None: mock_results[t]) as mock_solve:
            handler = _make_handler("/api/cp-clinch-all", server_with_games)
            handler._handle_get_cp_clinch_all("/api/cp-clinch-all")
            assert handler._sent_code == 200
            body = handler.get_response_json()

        # server_with_games has weeks 1,2 completed and week 3 scheduled
        # cutoff_week should be auto-detected as 2
        assert body["cutoff_week"] == 2
        # solve_clinch should have been called with cutoff_week=2
        assert mock_solve.called
        call_args = mock_solve.call_args
        assert call_args[0][2] == 2  # third positional arg is cutoff_week


class TestCPClinchAllRouteDispatch:
    """Test that /api/cp-clinch-all route dispatches correctly."""

    def test_route_dispatches_to_clinch_all_handler(self, server_with_games):
        """GET /api/cp-clinch-all dispatches to the bulk handler."""
        mock_results = {
            team: CPSolverResult(team=team, status=ClinchStatus.ALIVE)
            for team in ALL_TEAMS
        }

        with patch("src.server.solve_clinch", side_effect=lambda t, g, c, cfg=None: mock_results[t]):
            handler = _make_handler("/api/cp-clinch-all", server_with_games)
            handler.do_GET()
            assert handler._sent_code == 200
            body = handler.get_response_json()
            assert "conferences" in body

    def test_route_does_not_match_single_team_endpoint(self, server_with_games):
        """GET /api/cp-clinch/Bills still routes to single-team handler."""
        with patch("src.server.solve_clinch") as mock_solve:
            mock_solve.return_value = CPSolverResult(team="Bills")
            handler = _make_handler("/api/cp-clinch/Bills?cutoff_week=2", server_with_games)
            handler.do_GET()
            assert handler._sent_code == 200
            body = handler.get_response_json()
            # Single-team response has "team" field at top level
            assert body["team"] == "Bills"
            # Should NOT have "conferences" key
            assert "conferences" not in body
