"""Tests for adaptive ms_per_eval estimation using cache-based timing data.

These tests verify that get_ms_per_eval() uses cached historical timing data
when available, falls back to module-level globals, and that estimate_clinching()
passes the cache parameter through correctly.

Requirements: 4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

from src.cache import Cache
from src.clinching import get_ms_per_eval, estimate_clinching


def test_get_ms_per_eval_with_cache_data() -> None:
    """When cache has timing records, return arithmetic mean of ms_per_eval values.

    Validates: Requirements 4.1, 5.2
    """
    cache = Cache(":memory:")

    # Store some timing records with known ms_per_eval values
    cache.store_solver_timing(ms_per_eval=2.0, method="enumeration", relevant_games_count=8, total_evals=6561)
    cache.store_solver_timing(ms_per_eval=4.0, method="sampling", relevant_games_count=12, total_evals=810000)
    cache.store_solver_timing(ms_per_eval=3.0, method="enumeration", relevant_games_count=9, total_evals=19683)

    result = get_ms_per_eval(cache=cache)

    # Arithmetic mean of [2.0, 4.0, 3.0] = 3.0
    assert result == 3.0


def test_get_ms_per_eval_empty_cache_falls_back_to_global() -> None:
    """When cache exists but has no timing records, fall back to module-level global.

    Validates: Requirements 4.2, 5.3
    """
    cache = Cache(":memory:")

    # Set the module-level global to a known value
    with patch("src.clinching._benchmark_ms_per_eval", 7.5):
        result = get_ms_per_eval(cache=cache)

    assert result == 7.5


def test_get_ms_per_eval_cache_none_uses_global() -> None:
    """When cache is None, use existing benchmark behavior (module-level global).

    Validates: Requirements 5.3
    """
    with patch("src.clinching._benchmark_ms_per_eval", 5.0):
        result = get_ms_per_eval(cache=None)

    assert result == 5.0


def test_get_ms_per_eval_no_cache_no_global_returns_default() -> None:
    """When cache is None and no global benchmark exists, return 2.0 ms default.

    Validates: Requirements 4.3
    """
    with patch("src.clinching._benchmark_ms_per_eval", None):
        result = get_ms_per_eval(cache=None)

    assert result == 2.0


def test_estimate_clinching_passes_cache_through() -> None:
    """Verify estimate_clinching passes cache parameter to get_ms_per_eval.

    Validates: Requirements 5.4
    """
    cache = Cache(":memory:")

    with patch("src.clinching.get_ms_per_eval") as mock_get_ms:
        mock_get_ms.return_value = 3.0
        # Use a valid team and cutoff_week >= 14 so it reaches the estimation logic
        # We need mock games to avoid actual computation
        mock_game = MagicMock()
        mock_game.week = 15
        mock_game.home_team = "BUF"
        mock_game.away_team = "MIA"
        mock_game.game_id = "2024_15_BUF_MIA"
        mock_game.status = MagicMock()

        with patch("src.clinching.identify_contenders", return_value=["BUF", "MIA"]):
            with patch("src.clinching.get_relevant_games", return_value=([], [])):
                with patch("src.clinching.get_team_conference", return_value="AFC"):
                    result = estimate_clinching(
                        team="BUF",
                        all_games=[mock_game],
                        cutoff_week=15,
                        cache=cache,
                    )

        # Verify get_ms_per_eval was called with cache parameter
        mock_get_ms.assert_called_once()
        call_kwargs = mock_get_ms.call_args
        assert call_kwargs[1].get("cache") is cache or (
            len(call_kwargs[0]) >= 2 and call_kwargs[0][1] is cache
        )
