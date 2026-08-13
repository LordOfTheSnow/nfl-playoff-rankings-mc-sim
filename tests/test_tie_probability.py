"""Tests for empirical tie-probability estimation.

Covers the persisted prior-seasons pool (Cache.store_tie_stats/get_tie_stats,
simulator.compute_prior_seasons_tie_pool) and the per-request combination
with the current season's cutoff-truncated data (simulator.resolve_tie_probability).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.cache import Cache
from src.data_client import FetchResult, Game, GameStatus
from src.simulator import (
    DEFAULT_TIE_PROBABILITY,
    MIN_SEASONS_FOR_TIE_ESTIMATE,
    compute_prior_seasons_tie_pool,
    resolve_tie_probability,
)


def _make_game(
    game_id: str,
    week: int,
    status: GameStatus = GameStatus.COMPLETED,
    home_score: int | None = 20,
    away_score: int | None = 17,
) -> Game:
    """Create a Game for testing (defaults to a completed, non-tied game)."""
    return Game(
        game_id=game_id,
        week=week,
        date=date(2025, 9, 7),
        home_team="Chiefs",
        away_team="Bills",
        status=status,
        home_score=home_score,
        away_score=away_score,
    )


def _make_season_games(
    year_tag: str, num_games: int = 210, num_ties: int = 0
) -> list[Game]:
    """Build a synthetic full season's worth of completed games.

    num_games must be >= 200 to clear compute_prior_seasons_tie_pool's
    "fully-finished season" sanity threshold. The first num_ties games are
    ties; the rest are ordinary non-tied completed games.
    """
    games = []
    for i in range(num_games):
        is_tie = i < num_ties
        games.append(
            _make_game(
                f"{year_tag}-{i}",
                week=(i % 18) + 1,
                home_score=17,
                away_score=17 if is_tie else 10,
            )
        )
    return games


@pytest.fixture
def cache() -> Cache:
    return Cache(db_path=":memory:")


# ---------------------------------------------------------------------------
# Cache persistence
# ---------------------------------------------------------------------------


class TestTieStatsPersistence:
    def test_get_returns_none_when_never_computed(self, cache: Cache) -> None:
        assert cache.get_tie_stats() is None

    def test_store_then_get_round_trips(self, cache: Cache) -> None:
        cache.store_tie_stats(games=1000, ties=5, season_count=4, excluded_season=2025)
        stats = cache.get_tie_stats()
        assert stats is not None
        assert stats["games"] == 1000
        assert stats["ties"] == 5
        assert stats["season_count"] == 4
        assert stats["excluded_season"] == 2025
        assert stats["computed_at"]

    def test_store_overwrites_singleton_row(self, cache: Cache) -> None:
        cache.store_tie_stats(games=1000, ties=5, season_count=4, excluded_season=2025)
        cache.store_tie_stats(games=2000, ties=9, season_count=5, excluded_season=2026)
        stats = cache.get_tie_stats()
        assert stats is not None
        assert stats["games"] == 2000
        assert stats["excluded_season"] == 2026


# ---------------------------------------------------------------------------
# compute_prior_seasons_tie_pool
# ---------------------------------------------------------------------------


class TestComputePriorSeasonsTiePool:
    def test_no_seasons_cached(self, cache: Cache) -> None:
        games, ties, season_count = compute_prior_seasons_tie_pool(cache, exclude_season=2025)
        assert (games, ties, season_count) == (0, 0, 0)

    def test_excludes_active_season(self, cache: Cache) -> None:
        cache.store_games(_make_season_games("2025", num_games=210, num_ties=2), 2025)
        games, ties, season_count = compute_prior_seasons_tie_pool(cache, exclude_season=2025)
        assert season_count == 0
        assert games == 0

    def test_excludes_incomplete_season(self, cache: Cache) -> None:
        season_games = _make_season_games("2024", num_games=210, num_ties=1)
        # Mark a couple of games as still scheduled — season isn't finished
        season_games[0] = _make_game("2024-sched-1", week=18, status=GameStatus.SCHEDULED, home_score=None, away_score=None)
        cache.store_games(season_games, 2024)
        games, ties, season_count = compute_prior_seasons_tie_pool(cache, exclude_season=2025)
        assert season_count == 0

    def test_includes_season_with_a_postponed_game(self, cache: Cache) -> None:
        # A permanently unresolved (postponed/cancelled) game — e.g. the 2022
        # Week 17 Bills @ Bengals game, suspended and never resumed — should
        # count the season as over, not "still pending". It contributes no
        # game/tie count of its own (no score), but shouldn't block the rest
        # of that season's real completed games from being pooled.
        season_games = _make_season_games("2022", num_games=210, num_ties=1)
        # Overwrite a non-tied game (index 0 is the tie from num_ties=1 above)
        season_games[5] = _make_game(
            "2022-postponed-1", week=17, status=GameStatus.POSTPONED,
            home_score=None, away_score=None,
        )
        cache.store_games(season_games, 2022)
        games, ties, season_count = compute_prior_seasons_tie_pool(cache, exclude_season=2025)
        assert season_count == 1
        assert games == 209  # 210 games minus the 1 postponed (no score)
        assert ties == 1

    def test_excludes_too_small_a_season(self, cache: Cache) -> None:
        # All completed, but under the 200-game "fully finished" sanity floor
        cache.store_games(_make_season_games("2024", num_games=50, num_ties=1), 2024)
        games, ties, season_count = compute_prior_seasons_tie_pool(cache, exclude_season=2025)
        assert season_count == 0

    def test_pools_across_multiple_complete_seasons(self, cache: Cache) -> None:
        cache.store_games(_make_season_games("2022", num_games=210, num_ties=1), 2022)
        cache.store_games(_make_season_games("2023", num_games=220, num_ties=2), 2023)
        # Active season — excluded even though it's also complete
        cache.store_games(_make_season_games("2024", num_games=210, num_ties=5), 2024)

        games, ties, season_count = compute_prior_seasons_tie_pool(cache, exclude_season=2024)

        assert season_count == 2
        assert games == 210 + 220
        assert ties == 1 + 2


# ---------------------------------------------------------------------------
# resolve_tie_probability
# ---------------------------------------------------------------------------


class TestResolveTieProbability:
    def test_falls_back_to_default_when_no_prior_pool(self) -> None:
        result = resolve_tie_probability(None, all_games=[], cutoff_week=10)
        assert result == DEFAULT_TIE_PROBABILITY

    def test_falls_back_to_default_when_too_few_seasons(self) -> None:
        assert MIN_SEASONS_FOR_TIE_ESTIMATE == 2
        prior_pool = (1000, 5, 1)  # only 1 complete prior season
        result = resolve_tie_probability(prior_pool, all_games=[], cutoff_week=10)
        assert result == DEFAULT_TIE_PROBABILITY

    def test_falls_back_to_default_when_pool_has_zero_games(self) -> None:
        prior_pool = (0, 0, 2)
        result = resolve_tie_probability(prior_pool, all_games=[], cutoff_week=10)
        assert result == DEFAULT_TIE_PROBABILITY

    def test_combines_prior_pool_with_current_season_up_to_cutoff(self) -> None:
        prior_pool = (1000, 5, 2)  # 2 complete prior seasons, 0.5% tie rate
        current_season_games = [
            _make_game("g1", week=1, home_score=10, away_score=10),  # tie, in range
            _make_game("g2", week=5, home_score=20, away_score=17),  # win, in range
            _make_game("g3", week=16, home_score=14, away_score=14),  # tie, OUT of range (cutoff=10)
        ]
        result = resolve_tie_probability(prior_pool, current_season_games, cutoff_week=10)
        # pool: 1000 games/5 ties + current season through week 10: 2 games/1 tie
        assert result == pytest.approx((5 + 1) / (1000 + 2))

    def test_does_not_leak_games_beyond_cutoff_week(self) -> None:
        prior_pool = (1000, 0, 2)
        current_season_games = [
            _make_game("g1", week=17, home_score=10, away_score=10),  # tie, beyond cutoff
            _make_game("g2", week=18, home_score=20, away_score=17),  # beyond cutoff
        ]
        result = resolve_tie_probability(prior_pool, current_season_games, cutoff_week=10)
        # No games within cutoff — result should be exactly the prior pool's rate (0)
        assert result == 0.0

    def test_ignores_non_completed_games_in_current_season(self) -> None:
        prior_pool = (1000, 5, 2)
        current_season_games = [
            _make_game("g1", week=1, status=GameStatus.SCHEDULED, home_score=None, away_score=None),
        ]
        result = resolve_tie_probability(prior_pool, current_season_games, cutoff_week=10)
        assert result == pytest.approx(5 / 1000)


# ---------------------------------------------------------------------------
# HTTP-layer wiring: GET /api/status, POST /api/simulate,
# POST /api/clinching-scenarios, POST /api/fetch-data, POST /api/set-season
#
# The pure functions above are covered in isolation; these verify the server
# handlers actually thread tie_probability through correctly end to end —
# validation, the explicit-override vs. resolved-default split, and that the
# persisted pool gets refreshed on the two events that can change it.
# ---------------------------------------------------------------------------


def _make_server_handler(mock_cache: MagicMock, season_year: int = 2025) -> MagicMock:
    """Create a mock NFLRequestHandler bound to the real tie-probability-
    related handler methods, mirroring test_server_timing.py's _make_handler.

    Callers must set mock_cache.get_tie_stats.return_value themselves (None
    for "no persisted pool", or a stats dict) — it isn't defaulted here, so
    a value set before calling this can't get silently clobbered.
    """
    from src.server import NFLRequestHandler

    handler = MagicMock(spec=NFLRequestHandler)
    handler.server = MagicMock()
    handler.server.cache = mock_cache
    handler.server.season_year = season_year
    handler.server.version = "0.0.0-test"

    for name in (
        "_handle_get_status",
        "_handle_post_simulate",
        "_handle_post_clinching_scenarios",
        "_handle_post_fetch_data",
        "_handle_post_set_season",
        "_resolve_prior_ties_pool",
        "_refresh_tie_stats",
        "_serialize_clinching_result",
    ):
        setattr(handler, name, getattr(NFLRequestHandler, name).__get__(handler, NFLRequestHandler))

    return handler


class TestStatusEndpointDefaultTieProbability:
    def test_falls_back_to_hardcoded_default_with_no_persisted_pool(self) -> None:
        mock_cache = MagicMock()
        mock_cache.get_cache_status.return_value = {}
        mock_cache.get_games.return_value = [
            Game(game_id="g1", week=1, date=date(2025, 9, 7), home_team="Chiefs",
                 away_team="Bills", status=GameStatus.COMPLETED, home_score=20, away_score=17),
        ]
        mock_cache.get_tie_stats.return_value = None
        handler = _make_server_handler(mock_cache)
        handler._send_json_response = MagicMock()

        handler._handle_get_status()

        body = handler._send_json_response.call_args.args[1]
        assert body["default_tie_probability"] == DEFAULT_TIE_PROBABILITY

    def test_reports_estimate_from_persisted_pool(self) -> None:
        mock_cache = MagicMock()
        mock_cache.get_cache_status.return_value = {}
        mock_cache.get_games.return_value = [
            Game(game_id="g1", week=1, date=date(2025, 9, 7), home_team="Chiefs",
                 away_team="Bills", status=GameStatus.COMPLETED, home_score=20, away_score=17),
        ]
        # Pool current for this season (excluded_season matches season_year)
        mock_cache.get_tie_stats.return_value = {
            "games": 1000, "ties": 5, "season_count": 2, "excluded_season": 2025,
        }
        handler = _make_server_handler(mock_cache, season_year=2025)
        handler._send_json_response = MagicMock()

        handler._handle_get_status()

        body = handler._send_json_response.call_args.args[1]
        # No current-season completed games within the auto-detected cutoff
        # (the one game above is week 1, cutoff auto-detects to it) — either
        # way this should differ from the hardcoded default, proving the
        # persisted pool was actually used rather than ignored.
        assert body["default_tie_probability"] != DEFAULT_TIE_PROBABILITY


class TestSimulateEndpointTieProbabilityWiring:
    def _games(self) -> list[Game]:
        return [
            Game(game_id="g1", week=1, date=date(2025, 9, 7), home_team="Chiefs",
                 away_team="Bills", status=GameStatus.COMPLETED, home_score=20, away_score=17),
        ]

    def test_rejects_out_of_range_tie_probability(self) -> None:
        mock_cache = MagicMock()
        mock_cache.get_games.return_value = self._games()
        handler = _make_server_handler(mock_cache)
        handler._parse_json_body = MagicMock(return_value={"tie_probability": 1.5})
        handler._send_error_response = MagicMock()

        with patch("src.server.Simulator") as mock_simulator_cls:
            handler._handle_post_simulate()

        handler._send_error_response.assert_called_once()
        assert handler._send_error_response.call_args.args[0] == 400
        mock_simulator_cls.assert_not_called()

    def test_explicit_tie_probability_passed_through_to_config(self) -> None:
        mock_cache = MagicMock()
        mock_cache.get_games.return_value = self._games()
        handler = _make_server_handler(mock_cache)
        handler._parse_json_body = MagicMock(return_value={"tie_probability": 0.02})
        handler._send_json_response = MagicMock()

        mock_simulator = MagicMock()
        with patch("src.server.Simulator", return_value=mock_simulator) as mock_simulator_cls, \
             patch("src.server._serialize_simulation_result", return_value={}):
            handler._handle_post_simulate()

        config = mock_simulator_cls.call_args.args[0]
        assert config.tie_probability == 0.02

    def test_omitted_tie_probability_resolves_empirical_estimate(self) -> None:
        mock_cache = MagicMock()
        mock_cache.get_games.return_value = self._games()
        mock_cache.get_tie_stats.return_value = {
            "games": 1000, "ties": 5, "season_count": 2, "excluded_season": 2025,
        }
        handler = _make_server_handler(mock_cache, season_year=2025)
        handler._parse_json_body = MagicMock(return_value={})
        handler._send_json_response = MagicMock()

        mock_simulator = MagicMock()
        with patch("src.server.Simulator", return_value=mock_simulator) as mock_simulator_cls, \
             patch("src.server._serialize_simulation_result", return_value={}):
            handler._handle_post_simulate()

        config = mock_simulator_cls.call_args.args[0]
        # Pool rate is 5/1000; no current-season games beyond week 1 to add —
        # the auto-detected cutoff is week 1, which is exactly this game.
        expected = resolve_tie_probability((1000, 5, 2), self._games(), 1)
        assert config.tie_probability == pytest.approx(expected)
        assert config.tie_probability != DEFAULT_TIE_PROBABILITY


class TestClinchingScenariosEndpointTieProbabilityWiring:
    def _games(self) -> list[Game]:
        return [
            Game(game_id=f"g{w}", week=w, date=date(2025, 9, 7), home_team="Chiefs",
                 away_team="Bills", status=GameStatus.COMPLETED, home_score=20, away_score=17)
            for w in range(1, 16)
        ]

    def test_explicit_tie_probability_passed_through(self) -> None:
        mock_cache = MagicMock()
        mock_cache.get_games.return_value = self._games()
        handler = _make_server_handler(mock_cache)
        handler._parse_json_body = MagicMock(return_value={
            "team": "Chiefs", "cutoff_week": 15, "tie_probability": 0.01,
        })
        handler._send_json_response = MagicMock()

        fake_result = MagicMock(error=None, total_evals=100, method="enumeration")
        with patch("src.clinching.compute_clinching_scenarios", return_value=fake_result) as mock_compute:
            handler._handle_post_clinching_scenarios()

        assert mock_compute.call_args.kwargs["tie_probability"] == 0.01

    def test_omitted_tie_probability_resolves_empirical_estimate(self) -> None:
        mock_cache = MagicMock()
        mock_cache.get_games.return_value = self._games()
        mock_cache.get_tie_stats.return_value = {
            "games": 1000, "ties": 5, "season_count": 2, "excluded_season": 2025,
        }
        handler = _make_server_handler(mock_cache, season_year=2025)
        handler._parse_json_body = MagicMock(return_value={
            "team": "Chiefs", "cutoff_week": 15,
        })
        handler._send_json_response = MagicMock()

        fake_result = MagicMock(error=None, total_evals=100, method="enumeration")
        with patch("src.clinching.compute_clinching_scenarios", return_value=fake_result) as mock_compute:
            handler._handle_post_clinching_scenarios()

        expected = resolve_tie_probability((1000, 5, 2), self._games(), 15)
        assert mock_compute.call_args.kwargs["tie_probability"] == pytest.approx(expected)


class TestTiePoolRefreshedOnDataChangingEvents:
    def test_fetch_data_refreshes_tie_stats(self) -> None:
        mock_cache = MagicMock()
        handler = _make_server_handler(mock_cache)
        handler.server.data_client.fetch_season_schedule.return_value = FetchResult(
            games=[], warnings=[], errors=[],
        )
        handler._send_json_response = MagicMock()
        handler._compute_weekly_strengths = MagicMock()
        handler._refresh_tie_stats = MagicMock()

        handler._handle_post_fetch_data()

        handler._refresh_tie_stats.assert_called_once_with(handler.server)

    def test_set_season_refreshes_tie_stats(self) -> None:
        mock_cache = MagicMock()
        handler = _make_server_handler(mock_cache)
        handler._parse_json_body = MagicMock(return_value={"season": 2026})
        handler._send_json_response = MagicMock()
        handler._refresh_tie_stats = MagicMock()

        handler._handle_post_set_season()

        assert handler.server.season_year == 2026
        handler._refresh_tie_stats.assert_called_once_with(handler.server)
